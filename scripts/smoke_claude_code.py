"""Phase 6, acceptance 3: verify Claude Code can route through the proxy.

Runs the gateway checks from the official docs against a live `amort up`:

  https://code.claude.com/docs/en/llm-gateway-connect   (developer setup)
  https://code.claude.com/docs/en/llm-gateway-protocol  (what CC actually sends)

What this script can prove without a human at a terminal:

  A. The documented `curl` verification request succeeds through the proxy
     (`Authorization: Bearer` + `anthropic-version: 2023-06-01`).
  B. The `x-api-key` credential variant works too.
  C. `HEAD /` — Claude Code's startup connectivity probe — is answered.
  D. `POST /v1/messages?beta=true` — the real inference path, note the query
     string — is routed, and `anthropic-beta` / `anthropic-version` reach the
     upstream **unchanged**.
  E. `/v1/messages/count_tokens` and `GET /v1/models?limit=1000` (model
     discovery) relay.
  F. SSE `ping` / comment keep-alive lines are forwarded, not swallowed —
     Claude Code aborts a stream that goes silent for 300s.
  G. `x-claude-code-session-id` becomes the ledger's run_id, so a whole session
     rolls up as one run.
  H. Upstream error bodies are forwarded verbatim — Claude Code's auto-retry
     matches on the upstream's error *wording*, so a re-wrapped error breaks it.

What it cannot prove: the `/status` screen showing `Anthropic base URL`. That is
an interactive TUI check with a real key; the exact steps are in the README.

    uv run python scripts/smoke_claude_code.py
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from typing import Any


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


MOCK_PORT = _free_port()
PROXY_PORT = _free_port()
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"

os.environ["AMORT_UPSTREAM_ANTHROPIC"] = MOCK_URL
os.environ["AMORT_PORT"] = str(PROXY_PORT)
os.environ.setdefault("ANTHROPIC_API_KEY", "")

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

TOKEN = "sk-gateway-smoke-token"  # noqa: S105 — fixture, never a real credential

# What the upstream saw, so we can assert the proxy forwarded it unchanged.
seen: dict[str, Any] = {}

mock = FastAPI()


@mock.post("/v1/messages")
async def messages(request: Request) -> Any:
    body = await request.json()
    seen["headers"] = dict(request.headers)
    seen["query"] = str(request.url.query)
    seen["system"] = body.get("system")
    if body.get("stream"):
        return StreamingResponse(_sse(), media_type="text/event-stream")
    return JSONResponse(
        {
            "id": "msg_gw_0001", "type": "message", "role": "assistant",
            "model": body.get("model"), "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 7, "output_tokens": 2},
        }
    )


@mock.post("/v1/messages/count_tokens")
async def count_tokens(request: Request) -> Any:
    await request.json()
    return JSONResponse({"input_tokens": 12})


@mock.get("/v1/models")
async def models(request: Request) -> Any:
    seen["models_query"] = str(request.url.query)
    seen["models_auth"] = {
        k: v for k, v in request.headers.items() if k.lower() in ("authorization", "x-api-key")
    }
    return JSONResponse(
        {"data": [{"id": "claude-sonnet-5", "display_name": "Claude Sonnet 5"},
                  {"id": "claude-opus-5"}]}
    )


@mock.post("/v1/error")
async def upstream_error() -> Any:
    # Deliberately Anthropic's exact wording — Claude Code's compact-and-retry
    # path matches on it, so the proxy must not re-wrap the body.
    return JSONResponse(
        status_code=400,
        content={"type": "error",
                 "error": {"type": "invalid_request_error", "message": "prompt is too long"}},
    )


async def _sse():
    import asyncio

    def ev(name: str, data: dict[str, Any]) -> bytes:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()

    yield ev("message_start", {
        "type": "message_start",
        "message": {"id": "msg_gw_0001", "type": "message", "role": "assistant",
                    "model": "claude-sonnet-5", "content": [], "stop_reason": None,
                    "usage": {"input_tokens": 7, "output_tokens": 1}},
    })
    yield b"event: ping\ndata: {\"type\": \"ping\"}\n\n"   # keep-alive
    yield b": keep-alive comment\n\n"                        # SSE comment line
    await asyncio.sleep(0.1)
    yield ev("content_block_start",
             {"type": "content_block_start", "index": 0,
              "content_block": {"type": "text", "text": ""}})
    await asyncio.sleep(0.1)
    yield ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta", "text": "ok"}})
    yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield ev("message_delta", {"type": "message_delta",
                               "delta": {"stop_reason": "end_turn"},
                               "usage": {"output_tokens": 2}})
    yield ev("message_stop", {"type": "message_stop"})


def serve(app: Any, port: int) -> None:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    threading.Thread(target=server.run, daemon=True).start()


def wait_for(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.request("GET", url, timeout=1.0)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    raise RuntimeError(f"{url} never came up")


def main() -> int:
    from amort.config import get_settings
    from amort.ledger.events import flush, get_writer
    from amort.proxy.server import app as proxy_app

    get_settings().ensure_dirs()
    serve(mock, MOCK_PORT)
    serve(proxy_app, PROXY_PORT)
    wait_for(f"{MOCK_URL}/v1/models")
    wait_for(f"{PROXY_URL}/health")

    print(f"proxy    : {PROXY_URL}   (ANTHROPIC_BASE_URL)")
    print(f"upstream : {MOCK_URL}    (stands in for api.anthropic.com)\n")

    body = {"model": "claude-sonnet-5", "max_tokens": 1,
            "messages": [{"role": "user", "content": "."}]}

    # --- A. the documented curl verification, bearer token ------------------
    r = httpx.post(
        f"{PROXY_URL}/v1/messages",
        headers={"Authorization": f"Bearer {TOKEN}", "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=body, timeout=20,
    )
    print(f"[A] docs curl (Authorization: Bearer)   -> {r.status_code} {r.text[:44]}…")
    assert r.status_code == 200 and r.json()["id"].startswith("msg_"), r.text
    assert seen["headers"].get("authorization") == f"Bearer {TOKEN}", (
        "the bearer token did not reach the upstream unchanged"
    )

    # --- B. x-api-key variant ----------------------------------------------
    r = httpx.post(
        f"{PROXY_URL}/v1/messages",
        headers={"x-api-key": TOKEN, "anthropic-version": "2023-06-01"},
        json=body, timeout=20,
    )
    print(f"[B] docs curl (x-api-key)               -> {r.status_code}")
    assert r.status_code == 200
    assert seen["headers"].get("x-api-key") == TOKEN

    # --- C. HEAD / startup probe -------------------------------------------
    r = httpx.head(f"{PROXY_URL}/", timeout=10)
    print(f"[C] HEAD / startup probe                -> {r.status_code}")
    assert r.status_code == 200, "Claude Code's connectivity probe was not answered"

    # --- D. the real inference path, with betas ----------------------------
    betas = "context-management-2025-06-27,fine-grained-tool-streaming-2025-05-14"
    r = httpx.post(
        f"{PROXY_URL}/v1/messages?beta=true",
        headers={"Authorization": f"Bearer {TOKEN}", "anthropic-version": "2023-06-01",
                 "anthropic-beta": betas,
                 "x-claude-code-session-id": "sess_smoke_0001",
                 "x-claude-code-agent-id": "agent_smoke_0001"},
        json={**body, "system": [
            {"type": "text", "text": "You are Claude Code, Anthropic's official CLI…"},
            {"type": "text", "text": "project context"},
        ]},
        timeout=20,
    )
    print(f"[D] POST /v1/messages?beta=true         -> {r.status_code} query={seen['query']!r}")
    assert r.status_code == 200
    assert seen["query"] == "beta=true", "the query string was dropped"
    assert seen["headers"].get("anthropic-beta") == betas, "anthropic-beta was altered"
    assert seen["headers"].get("anthropic-version") == "2023-06-01"
    assert isinstance(seen["system"], list) and len(seen["system"]) == 2, (
        "the system array's shape changed — that breaks attribution-block stripping"
    )
    assert seen["system"][0]["text"].startswith("You are Claude Code"), (
        "the attribution block is no longer first in the system array"
    )
    print("    anthropic-beta + anthropic-version forwarded unchanged ✓")
    print("    system array shape preserved (attribution block still first) ✓")

    # --- E. count_tokens + model discovery ---------------------------------
    r = httpx.post(f"{PROXY_URL}/v1/messages/count_tokens",
                   headers={"Authorization": f"Bearer {TOKEN}"}, json=body, timeout=20)
    print(f"[E] /v1/messages/count_tokens           -> {r.status_code} {r.text.strip()}")
    assert r.status_code == 200 and "input_tokens" in r.json()

    r = httpx.get(f"{PROXY_URL}/v1/models?limit=1000",
                  headers={"Authorization": f"Bearer {TOKEN}"}, timeout=20)
    ids = [m["id"] for m in r.json()["data"]]
    print(f"    GET /v1/models?limit=1000           -> {r.status_code} {ids}")
    assert r.status_code == 200 and seen["models_query"] == "limit=1000"
    assert seen["models_auth"].get("authorization") == f"Bearer {TOKEN}"

    # --- F. keep-alives survive the relay ----------------------------------
    chunks: list[bytes] = []
    with httpx.stream(
        "POST", f"{PROXY_URL}/v1/messages",
        headers={"Authorization": f"Bearer {TOKEN}", "anthropic-version": "2023-06-01"},
        json={**body, "stream": True}, timeout=30,
    ) as resp:
        for raw in resp.iter_raw():
            chunks.append(raw)
    stream_bytes = b"".join(chunks)
    print(f"[F] streaming: {len(chunks)} chunk(s), {len(stream_bytes)} bytes")
    assert b"event: ping" in stream_bytes, "SSE ping was swallowed — CC aborts after 300s of silence"
    assert b": keep-alive comment" in stream_bytes, "SSE comment line was swallowed"
    assert b"message_stop" in stream_bytes
    print("    ping + comment keep-alives forwarded ✓")

    # --- G. session id becomes the run id ----------------------------------
    time.sleep(0.4)
    flush()
    writer = get_writer()
    rows = writer.query(
        "SELECT RUN_ID, META FROM STEPS WHERE RUN_ID = ?" if writer.name == "sqlite"
        else "SELECT RUN_ID, META FROM STEPS WHERE RUN_ID = %s",
        ("sess_smoke_0001",),
    )
    print(f"[G] ledger rows for the CC session id   -> {len(rows)}")
    assert rows, "x-claude-code-session-id did not become the run_id"
    meta = json.loads(rows[0][1]) if isinstance(rows[0][1], str) else rows[0][1]
    assert meta.get("client") == "claude-code", meta
    assert meta.get("agent_id") == "agent_smoke_0001", meta
    print(f"    client={meta['client']} agent_id={meta['agent_id']} ✓")

    # --- H. upstream errors are forwarded verbatim --------------------------
    r = httpx.post(f"{PROXY_URL}/v1/error",
                   headers={"Authorization": f"Bearer {TOKEN}"}, json=body, timeout=20)
    print(f"[H] upstream 400 relayed                -> {r.status_code} {r.text.strip()}")
    assert r.status_code == 400, "the upstream status code was rewritten"
    assert r.json()["error"]["message"] == "prompt is too long", (
        "the upstream error body was re-wrapped — Claude Code's auto-retry matches on its wording"
    )

    print("\nPHASE 6 CLAUDE-CODE COMPATIBILITY: PASS")
    print("Remaining check needs a human + a real key: `/status` → `Anthropic base URL`.")
    print("Exact steps are in README.md → Connecting Claude Code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
