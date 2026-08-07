"""The relay: client → upstream → client, byte-identical, with usage captured.

Load-bearing invariants:

* **Streaming is non-negotiable.** Real clients (Claude Code, every SDK's
  `.stream()`) speak SSE. The relay forwards each upstream chunk the moment it
  arrives — no buffering, no re-chunking of content, no re-serialization. A proxy
  that collects the stream and replays it at the end technically "works" and
  ruins the product.
* **Capture without altering.** Usage is parsed from a *tap* on the byte stream:
  chunks are forwarded first, then scanned. The tap only JSON-parses SSE `data:`
  lines that contain a field it needs, so the common delta line costs one
  substring check.
* **Auth is the client's, if it has one.** `x-api-key` / `Authorization` are
  forwarded untouched; the `.env` key is injected only when the client sent
  neither. That is what makes "one env var, zero code changes" true for tools
  that already manage their own credentials.
* **Hop-by-hop headers must not be forwarded.** Passing `content-length` from a
  request whose body we may have rewritten, or `content-encoding` from a body
  httpx has already decoded, produces truncated or garbled responses. Both
  directions are filtered.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from amort.config import Settings, get_settings
from amort.ledger.events import StepEvent, emit
from amort.proxy.interceptors import (
    Provider,
    ProxyRequest,
    ProxyResponse,
    safe_after_response,
    safe_before_request,
)

logger = logging.getLogger("amort.proxy")

# Hop-by-hop headers (RFC 9110 §7.6.1) plus the two that describe a body we
# re-frame: `content-length` (body may differ) and `content-encoding` (httpx
# already decoded it for us).
_HOP_BY_HOP = frozenset(
    {
        "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
        "te", "trailer", "transfer-encoding", "upgrade",
    }
)
_DROP_FROM_REQUEST = _HOP_BY_HOP | {"host", "content-length", "accept-encoding"}
_DROP_FROM_RESPONSE = _HOP_BY_HOP | {"content-length", "content-encoding"}

# No read timeout: a thinking-heavy turn can legitimately stream for minutes.
TIMEOUT = httpx.Timeout(connect=15.0, read=None, write=60.0, pool=15.0)


def build_client() -> httpx.AsyncClient:
    """One long-lived client for the process; connection reuse matters here."""
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )


def upstream_base(provider: Provider, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return (
        s.amort_upstream_anthropic if provider == "anthropic" else s.amort_upstream_openai
    ).rstrip("/")


# ─────────────────────────────────────────────────────────────────────────────
# Headers
# ─────────────────────────────────────────────────────────────────────────────


def prepare_headers(
    incoming: dict[str, str], provider: Provider, settings: Settings | None = None
) -> dict[str, str]:
    """Forward the client's headers; inject a key only if it sent none."""
    s = settings or get_settings()
    headers = {k: v for k, v in incoming.items() if k.lower() not in _DROP_FROM_REQUEST}

    lower = {k.lower() for k in headers}
    has_auth = "x-api-key" in lower or "authorization" in lower
    if not has_auth:
        if provider == "anthropic" and s.anthropic_api_key:
            headers["x-api-key"] = s.anthropic_api_key
        elif provider == "openai" and s.openai_api_key:
            headers["Authorization"] = f"Bearer {s.openai_api_key}"

    if provider == "anthropic" and "anthropic-version" not in lower:
        # Anthropic rejects the request without it; SDKs always send one, raw
        # curl users often don't. Adding it is the difference between "works"
        # and "400 for no visible reason".
        headers["anthropic-version"] = "2023-06-01"
    return headers


def response_headers(upstream: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in upstream.items() if k.lower() not in _DROP_FROM_RESPONSE}


# ─────────────────────────────────────────────────────────────────────────────
# Usage capture
# ─────────────────────────────────────────────────────────────────────────────


class UsageTap:
    """Extracts usage/model/tool_use from an SSE stream without altering it.

    Fed chunks *after* they are forwarded. Keeps a line buffer because a JSON
    object can straddle a chunk boundary, and only parses `data:` lines whose
    text contains a marker it cares about — the per-token delta lines, which are
    the overwhelming majority, cost one `in` check each.
    """

    _MARKERS = ('"usage"', '"model"', '"tool_use"', '"tool_calls"', '"finish_reason"')

    def __init__(self, provider: Provider) -> None:
        self.provider = provider
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.model: str | None = None
        self.tool_uses: list[str] = []
        self.stop_reason: str | None = None
        self.event_count = 0
        self._buf = b""

    def feed(self, chunk: bytes) -> None:
        self._buf += chunk
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            self._line(line)
        if len(self._buf) > 1_000_000:  # pathological single line; don't grow forever
            self._buf = b""

    def close(self) -> None:
        if self._buf:
            self._line(self._buf)
            self._buf = b""

    def _line(self, raw: bytes) -> None:
        line = raw.strip()
        if not line.startswith(b"data:"):
            return
        self.event_count += 1
        payload = line[5:].strip()
        if payload in (b"[DONE]", b""):
            return
        text = payload.decode("utf-8", "replace")
        if not any(m in text for m in self._MARKERS):
            return
        try:
            self._absorb(json.loads(text))
        except (json.JSONDecodeError, TypeError):
            return

    def _absorb(self, obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        if self.provider == "anthropic":
            self._absorb_anthropic(obj)
        else:
            self._absorb_openai(obj)

    def _absorb_anthropic(self, obj: dict[str, Any]) -> None:
        etype = obj.get("type")
        if etype == "message_start":
            message = obj.get("message") or {}
            self.model = message.get("model") or self.model
            self._usage(message.get("usage") or {})
        elif etype == "message_delta":
            self._usage(obj.get("usage") or {})
            self.stop_reason = (obj.get("delta") or {}).get("stop_reason") or self.stop_reason
        elif etype == "content_block_start":
            block = obj.get("content_block") or {}
            if block.get("type") in ("tool_use", "server_tool_use"):
                self.tool_uses.append(str(block.get("name", "")))

    def _absorb_openai(self, obj: dict[str, Any]) -> None:
        self.model = obj.get("model") or self.model
        if usage := obj.get("usage"):
            # Only present when the caller sets stream_options.include_usage.
            self.input_tokens = int(usage.get("prompt_tokens", self.input_tokens) or 0)
            self.output_tokens = int(usage.get("completion_tokens", self.output_tokens) or 0)
            details = usage.get("prompt_tokens_details") or {}
            self.cache_read_tokens = int(details.get("cached_tokens", 0) or 0)
        for choice in obj.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            if reason := choice.get("finish_reason"):
                self.stop_reason = reason
            for call in (choice.get("delta") or {}).get("tool_calls") or []:
                name = (call.get("function") or {}).get("name")
                if name:
                    self.tool_uses.append(str(name))

    def _usage(self, usage: dict[str, Any]) -> None:
        """Anthropic reports the three input buckets separately; keep them apart."""
        if (v := usage.get("input_tokens")) is not None:
            self.input_tokens = int(v)
        if (v := usage.get("output_tokens")) is not None:
            self.output_tokens = int(v)
        if (v := usage.get("cache_read_input_tokens")) is not None:
            self.cache_read_tokens = int(v)
        if (v := usage.get("cache_creation_input_tokens")) is not None:
            self.cache_write_tokens = int(v)


def usage_from_json(provider: Provider, body: dict[str, Any]) -> UsageTap:
    """Same extraction for a non-streaming JSON body."""
    tap = UsageTap(provider)
    tap.model = body.get("model")
    if provider == "anthropic":
        tap._usage(body.get("usage") or {})  # noqa: SLF001 — same module
        for block in body.get("content") or []:
            if isinstance(block, dict) and block.get("type") in ("tool_use", "server_tool_use"):
                tap.tool_uses.append(str(block.get("name", "")))
        tap.stop_reason = body.get("stop_reason")
    else:
        usage = body.get("usage") or {}
        tap.input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        tap.output_tokens = int(usage.get("completion_tokens", 0) or 0)
        tap.cache_read_tokens = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
        for choice in body.get("choices") or []:
            tap.stop_reason = choice.get("finish_reason") or tap.stop_reason
            for call in (choice.get("message") or {}).get("tool_calls") or []:
                name = (call.get("function") or {}).get("name")
                if name:
                    tap.tool_uses.append(str(name))
    return tap


# ─────────────────────────────────────────────────────────────────────────────
# The relay
# ─────────────────────────────────────────────────────────────────────────────


async def relay(
    request: Request,
    *,
    provider: Provider,
    client: httpx.AsyncClient,
    settings: Settings | None = None,
    run_id: str | None = None,
) -> Response:
    """Proxy one request upstream and return the response (streaming or not)."""
    s = settings or get_settings()
    raw_body = await request.body()

    parsed: dict[str, Any] | None = None
    if raw_body:
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            parsed = None  # not JSON (or malformed) — relay it verbatim anyway

    wants_stream = bool(parsed.get("stream")) if isinstance(parsed, dict) else False

    # Claude Code stamps every request in a session with `x-claude-code-session-id`
    # (and subagent requests with `x-claude-code-agent-id`). Using it as the run_id
    # groups a whole session's calls into one run for free — the alternative is
    # parsing request bodies to guess which calls belong together.
    session_id = request.headers.get("x-claude-code-session-id")
    proxy_req = safe_before_request(
        ProxyRequest(
            provider=provider,
            path=request.url.path,
            method=request.method,
            headers=dict(request.headers),
            raw_body=raw_body,
            body=parsed,
            stream=wants_stream,
            meta={
                "run_id": run_id or session_id or f"proxy_{int(time.time() * 1000):x}",
                "client": "claude-code" if session_id else "sdk",
                "agent_id": request.headers.get("x-claude-code-agent-id"),
                "parent_agent_id": request.headers.get("x-claude-code-parent-agent-id"),
            },
        )
    )

    # A hook that edited `body` wins over the bytes it was parsed from; otherwise
    # the original bytes are forwarded untouched (byte-identical passthrough).
    outbound = (
        json.dumps(proxy_req.body).encode()
        if proxy_req.body is not None and proxy_req.body is not parsed
        else proxy_req.raw_body
    )

    url = f"{upstream_base(provider, s)}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    headers = prepare_headers(proxy_req.headers, provider, s)

    if proxy_req.meta.get("layer1") and proxy_req.body is not None:
        # Layer 1 armed this request (non-streaming by construction): run the
        # proxy-side discovery loop instead of the single-shot path below.
        return await _lighten_relay(
            proxy_req, client=client, url=url, headers=headers, provider=provider
        )

    started = time.perf_counter()

    upstream = client.build_request(
        proxy_req.method, url, headers=headers, content=outbound
    )
    try:
        response = await client.send(upstream, stream=True)
    except httpx.HTTPError as exc:
        logger.warning("upstream request failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"amortize: upstream {upstream_base(provider, s)} unreachable: {exc}",
                },
            },
        )

    is_sse = "text/event-stream" in response.headers.get("content-type", "")
    if is_sse or wants_stream:
        return _streaming_response(response, proxy_req, started, provider)
    return await _buffered_response(response, proxy_req, started, provider)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — the proxy-side discovery loop (synthetic tools never reach the client)
# ─────────────────────────────────────────────────────────────────────────────

_LIGHTEN_MAX_CALLS = 6


async def _upstream_json(
    client: httpx.AsyncClient, method: str, url: str, headers: dict[str, str], content: bytes
) -> httpx.Response:
    """One buffered upstream call — the hoisted single-shot pattern, loop-sized."""
    upstream = client.build_request(method, url, headers=headers, content=content)
    response = await client.send(upstream, stream=True)
    await response.aread()
    await response.aclose()
    return response


async def _lighten_relay(
    req: ProxyRequest,
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    provider: Provider,
) -> Response:
    """Run the discovery loop; on cap / non-200 / any exception, one clean
    re-send of the ORIGINAL raw body (full catalogue). Never fail the request."""
    try:
        return await _lighten_loop(req, client=client, url=url, headers=headers, provider=provider)
    except Exception as exc:  # noqa: BLE001 — degrade to pass-through, never 500
        logger.warning(
            "layer1 loop abandoned (%s: %s) — re-sending the original request", type(exc).__name__, exc
        )
        stash = req.meta.get("layer1") or {}
        stash["internal"] = False
        stash["fallback"] = True

    started = time.perf_counter()
    upstream = client.build_request(req.method, url, headers=headers, content=req.raw_body)
    try:
        response = await client.send(upstream, stream=True)
    except httpx.HTTPError as exc:
        logger.warning("upstream request failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {"type": "api_error", "message": f"amortize: upstream unreachable: {exc}"},
            },
        )
    return await _buffered_response(response, req, started, provider)


async def _lighten_loop(
    req: ProxyRequest,
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    provider: Provider,
) -> Response:
    from amort.proxy import lighten

    stash: dict[str, Any] = req.meta["layer1"]
    catalog: list[dict[str, Any]] = stash.get("catalog") or []
    body: dict[str, Any] = req.body or {}
    active = {
        str((t.get("function") or {}).get("name", ""))
        for t in body.get("tools") or []
        if isinstance(t, dict)
    }
    total_prompt = total_completion = 0

    for _ in range(_LIGHTEN_MAX_CALLS):
        # Honest counter: what this iteration actually carries, stub text included.
        stash["schema_tokens_after"] = len(json.dumps(body.get("tools") or [])) // 4
        started = time.perf_counter()
        response = await _upstream_json(client, req.method, url, headers, json.dumps(body).encode())
        if response.status_code != 200:
            raise RuntimeError(f"upstream {response.status_code} mid-loop")
        parsed = json.loads(response.content)
        tap = usage_from_json(provider, parsed)
        total_prompt += tap.input_tokens
        total_completion += tap.output_tokens

        message = ((parsed.get("choices") or [{}])[0].get("message")) or {}
        calls = message.get("tool_calls") or []
        synthetic = [
            c
            for c in calls
            if ((c.get("function") or {}).get("name")) in lighten.SYNTHETIC_TOOL_NAMES
        ]

        stash["internal"] = bool(synthetic)
        _finish(req, tap, response.status_code, dict(response.headers), started, streamed=False)

        if not synthetic:
            # Final. Usage honesty: the client's recorder must see the true
            # total across every iteration. content-length is already stripped,
            # so the size change is safe.
            usage = parsed.setdefault("usage", {})
            usage["prompt_tokens"] = total_prompt
            usage["completion_tokens"] = total_completion
            usage["total_tokens"] = total_prompt + total_completion
            return Response(
                content=json.dumps(parsed).encode(),
                status_code=response.status_code,
                headers=response_headers(response.headers),
                media_type=response.headers.get("content-type"),
            )

        # Splice an assistant message carrying ONLY the synthetic calls into the
        # outbound copy. Real tool_calls in the same choice are dropped from the
        # splice — the model re-issues them next iteration, once it has what it
        # asked for — and so is any assistant content (interleaved reasoning text
        # would be re-billed on every subsequent iteration). The client never
        # sees any of this.
        body.setdefault("messages", []).append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": c.get("id"),
                        "type": "function",
                        "function": {
                            "name": c["function"]["name"],
                            "arguments": c["function"].get("arguments") or "{}",
                        },
                    }
                    for c in synthetic
                ],
            }
        )
        for call in synthetic:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            if name == lighten.SEARCH_TOOL_NAME:
                hits = lighten.resolve_search_tools(catalog, str(args.get("query", "")))
                fresh = [t for t in hits if t["function"]["name"] not in active]
                body["tools"].extend(fresh)
                active.update(t["function"]["name"] for t in fresh)
                loaded = [t["function"]["name"] for t in hits]
                result = (
                    "Loaded full schemas into your tool list: "
                    + ", ".join(loaded)
                    + ". Continue the task by calling tools directly; do not search "
                    "again unless you need a new capability."
                    if loaded
                    else "No tools matched that query. Available tools: "
                    + ", ".join(str(t["function"].get("name", "")) for t in catalog)
                )
            else:
                result = lighten.resolve_read_spill(
                    str(args.get("handle", "")),
                    str(args.get("mode", "head")),
                    str(args.get("arg", "")),
                )
            body["messages"].append(
                {"role": "tool", "tool_call_id": call.get("id"), "content": result}
            )

    raise RuntimeError(f"loop cap ({_LIGHTEN_MAX_CALLS}) exhausted")


def _streaming_response(
    response: httpx.Response, req: ProxyRequest, started: float, provider: Provider
) -> StreamingResponse:
    """Forward each chunk immediately; tap it for usage on the way past."""
    tap = UsageTap(provider)

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes():
                yield chunk           # forward first — never make the client wait on us
                tap.feed(chunk)       # then observe
        finally:
            tap.close()
            await response.aclose()
            _finish(req, tap, response.status_code, dict(response.headers), started, streamed=True)

    return StreamingResponse(
        body(),
        status_code=response.status_code,
        headers=response_headers(response.headers),
        media_type=response.headers.get("content-type", "text/event-stream"),
    )


async def _buffered_response(
    response: httpx.Response, req: ProxyRequest, started: float, provider: Provider
) -> Response:
    await response.aread()
    payload = response.content
    await response.aclose()

    tap = UsageTap(provider)
    try:
        body = json.loads(payload) if payload else {}
        if isinstance(body, dict):
            tap = usage_from_json(provider, body)
    except json.JSONDecodeError:
        body = None

    _finish(req, tap, response.status_code, dict(response.headers), started, streamed=False)
    return Response(
        content=payload,
        status_code=response.status_code,
        headers=response_headers(response.headers),
        media_type=response.headers.get("content-type"),
    )


def _finish(
    req: ProxyRequest,
    tap: UsageTap,
    status: int,
    headers: dict[str, str],
    started: float,
    *,
    streamed: bool,
) -> None:
    """Run `after_response` and write one StepEvent. Must never raise."""
    wall_ms = int((time.perf_counter() - started) * 1000)
    resp = safe_after_response(
        ProxyResponse(
            provider=req.provider,
            status_code=status,
            headers=headers,
            stream=streamed,
            input_tokens=tap.input_tokens,
            output_tokens=tap.output_tokens,
            cache_read_tokens=tap.cache_read_tokens,
            cache_write_tokens=tap.cache_write_tokens,
            model=tap.model or req.model,
            tool_uses=tap.tool_uses,
            wall_ms=wall_ms,
            meta={"stop_reason": tap.stop_reason, "sse_events": tap.event_count},
        )
    )

    emit(
        StepEvent.for_llm(
            run_id=str(req.meta.get("run_id", "")),
            model=resp.model,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cache_read_tokens=resp.cache_read_tokens,
            cache_write_tokens=resp.cache_write_tokens,
            wall_ms=resp.wall_ms,
            lane="amortize",
            mode="cold",
            meta={
                "provider": req.provider,
                "path": req.path,
                "status": resp.status_code,
                "streamed": streamed,
                "request_bytes": len(req.raw_body),
                "tool_uses": resp.tool_uses,
                "tools_offered": len(req.tool_names),
                "stop_reason": resp.meta.get("stop_reason"),
                "sse_events": resp.meta.get("sse_events"),
                "client": req.meta.get("client"),
                "agent_id": req.meta.get("agent_id"),
                # Layer-1 counters only — the stashed catalogue never hits the ledger.
                "layer1": (
                    {k: v for k, v in layer1.items() if k != "catalog"}
                    if (layer1 := req.meta.get("layer1"))
                    else None
                ),
                "layer2": req.meta.get("layer2"),
            },
        )
    )


__all__ = [
    "TIMEOUT",
    "UsageTap",
    "build_client",
    "prepare_headers",
    "relay",
    "response_headers",
    "upstream_base",
    "usage_from_json",
]
