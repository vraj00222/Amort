"""Interceptor seams — where Layers 1 and 2 will plug in.

Today both hooks are **strict pass-throughs**: they receive the parsed request or
response, return it unchanged, and the proxy is byte-identical to talking to the
provider directly. That is the point of this build — the seams exist and are
wired, so adding an optimization later is a change to one function body rather
than surgery on the request path.

## The contract

    before_request(req)  -> ProxyRequest     # may rewrite what goes upstream
    after_response(resp) -> ProxyResponse    # may rewrite what goes to the client

Two invariants any future implementation must hold:

1. **Semantic identity.** Whatever these hooks do, the client's final output must
   be indistinguishable from the un-proxied call. Layer 1 removes tokens the model
   did not need; it must never remove information the model did need. The parity
   grader (`skills/grader.py`) is what proves this, and a guard failure must fall
   back to the untouched request.
2. **Never fail the request.** A hook that raises must degrade to pass-through.
   A proxy that 500s because its optimizer had a bad day is worse than no proxy.

## What goes here later

`before_request` — **TODO(layer1)** dynamic tool discovery. Strip the full
`tools` array (verbose JSON Schemas dominate the prompt on tool-heavy agents),
replace it with one-line stubs plus a synthetic `search_tools` tool, and hydrate
the real schema only when the model asks for it. Cursor measured 46.9% token
reduction with this pattern. Requires: a per-conversation tool registry keyed by
the stripped catalogue's hash, and handling of the model calling `search_tools`
mid-turn.

### Two hazards Layer 1 must respect (from the gateway protocol reference)

* **Do not touch the `system` array's shape.** Claude Code prepends an
  attribution block that `api.anthropic.com` strips *positionally* — only if it
  is still the first entry of the array it arrived in. Prepending a block,
  reordering, or collapsing the array to a string defeats the strip, and the
  block then lands in the prompt *and* the cache key. Rewrite `tools`, not
  `system`.
* **A beta header and its body field travel as a pair.** Stripping
  `anthropic-beta` while forwarding the field it authorizes (`output_config`,
  `context_management`, `strict`/`defer_loading` on tools) produces a hard 400.
  Layer 1 removes tool *schemas*; it must leave those fields and their headers
  alone. This is why `passthrough.py` forwards headers wholesale rather than
  against an allowlist — the capability set grows with every Claude Code release.

`before_request` — **TODO(layer2)** skill lookup. Fingerprint (system, user
message, tool names), ask `skills.store_everos.search_skill()`, and on a
confident, `verified`-or-better hit hand the request to `skills.replayer` instead
of the model. Guard failure → fall through to this same pass-through path.

`after_response` — **TODO(layer1)** oversized tool-result spill. When a
`tool_result` block exceeds the spill threshold, write it to `AMORT_SPILL_DIR`
and hand the model a handle plus a preview, so a 200KB API dump does not occupy
the context window for the rest of the run.

`after_response` — **TODO(layer2)** trajectory capture for distillation. The run
recorder already collects this in the demo harness; the proxy path needs the same
capture so *any* client's runs become Cases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger("amort.proxy.interceptors")

Provider = Literal["anthropic", "openai"]

# TODO(layer1): spill anything larger than this to AMORT_SPILL_DIR and pass a handle.
SPILL_THRESHOLD_BYTES = 8 * 1024


@dataclass
class ProxyRequest:
    """A client request on its way upstream."""

    provider: Provider
    path: str
    method: str
    headers: dict[str, str]
    raw_body: bytes
    body: dict[str, Any] | None = None
    stream: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> str | None:
        return (self.body or {}).get("model")

    @property
    def tool_names(self) -> list[str]:
        """Tool names in the request, in whichever format the provider uses."""
        body = self.body or {}
        names: list[str] = []
        for tool in body.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            if "name" in tool:  # Anthropic
                names.append(str(tool["name"]))
            elif isinstance(tool.get("function"), dict):  # OpenAI
                names.append(str(tool["function"].get("name", "")))
        return [n for n in names if n]

    @property
    def system_text(self) -> str:
        """System prompt as text, flattening Anthropic's block form."""
        system = (self.body or {}).get("system")
        if isinstance(system, str):
            return system
        if isinstance(system, list):
            return "\n".join(
                str(b.get("text", "")) for b in system if isinstance(b, dict)
            )
        for msg in (self.body or {}).get("messages") or []:
            if isinstance(msg, dict) and msg.get("role") == "system":
                return _flatten_content(msg.get("content"))
        return ""

    @property
    def last_user_message(self) -> str:
        for msg in reversed((self.body or {}).get("messages") or []):
            if isinstance(msg, dict) and msg.get("role") == "user":
                return _flatten_content(msg.get("content"))
        return ""


@dataclass
class ProxyResponse:
    """An upstream response on its way back to the client."""

    provider: Provider
    status_code: int
    headers: dict[str, str]
    raw_body: bytes | None = None
    body: dict[str, Any] | None = None
    stream: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str | None = None
    tool_uses: list[str] = field(default_factory=list)
    wall_ms: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


def before_request(req: ProxyRequest) -> ProxyRequest:
    """Layer 1/2 entry point. Currently a strict pass-through.

    TODO(layer1): tool-schema dieting — replace `req.body["tools"]` with compact
    stubs + a synthetic `search_tools` tool, and record the mapping so
    `after_response` can hydrate a stub the model selected.

    TODO(layer2): skill lookup — fingerprint the task and, on a confident hit,
    mark `req.meta["skill_id"]` so the server can route to the replayer instead
    of upstream.
    """
    return req


def after_response(resp: ProxyResponse) -> ProxyResponse:
    """Layer 1/2 exit point. Currently a strict pass-through.

    TODO(layer1): spill `tool_result` blocks over `SPILL_THRESHOLD_BYTES` to
    `AMORT_SPILL_DIR` and substitute `{handle, preview, bytes}`.

    TODO(layer2): hand the completed trajectory to `skills.recorder` so every
    proxied run — not just demo runs — becomes an EverOS Case.
    """
    return resp


def safe_before_request(req: ProxyRequest) -> ProxyRequest:
    """`before_request` with the never-fail-the-request guarantee applied."""
    try:
        return before_request(req)
    except Exception as exc:  # noqa: BLE001 — an optimizer bug must not 500 the caller
        logger.warning("before_request failed (%s) — passing through untouched: %s",
                       type(exc).__name__, exc)
        return req


def safe_after_response(resp: ProxyResponse) -> ProxyResponse:
    """`after_response` with the never-fail-the-request guarantee applied."""
    try:
        return after_response(resp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("after_response failed (%s) — passing through untouched: %s",
                       type(exc).__name__, exc)
        return resp


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text", "")) for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


__all__ = [
    "SPILL_THRESHOLD_BYTES",
    "Provider",
    "ProxyRequest",
    "ProxyResponse",
    "after_response",
    "before_request",
    "safe_after_response",
    "safe_before_request",
]
