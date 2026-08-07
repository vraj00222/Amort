"""Fixture server for the end-to-end Claude Code test: mock upstream + real proxy.

Runs the Amortize proxy on `AMORT_PORT` in front of a stand-in for
`api.anthropic.com`, so a real `claude` process can be pointed at the proxy
without spending a token of real quota. The stand-in answers with a fixed
assistant message in the Anthropic wire format (streaming or not).

Not a smoke test on its own — `scripts/smoke_claude_code.py` is. This exists so
the Claude Code CLI has something to talk to:

    AMORT_PORT=4000 MOCK_PORT=4001 uv run python scripts/_gateway_fixture.py &
    ANTHROPIC_BASE_URL=http://127.0.0.1:4000 ANTHROPIC_AUTH_TOKEN=x claude -p "hi"
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

MOCK_PORT = int(os.environ.get("MOCK_PORT", "4101"))
PROXY_PORT = int(os.environ.get("AMORT_PORT", "4100"))
os.environ["AMORT_UPSTREAM_ANTHROPIC"] = f"http://127.0.0.1:{MOCK_PORT}"
os.environ["AMORT_PORT"] = str(PROXY_PORT)

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

REPLY = os.environ.get("MOCK_REPLY", "ok")
mock = FastAPI()
LOG = os.environ.get("MOCK_LOG", "")


@mock.post("/v1/messages")
async def messages(request: Request) -> Any:
    body = await request.json()
    if LOG:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "model": body.get("model"),
                "stream": bool(body.get("stream")),
                "n_messages": len(body.get("messages") or []),
                "n_tools": len(body.get("tools") or []),
                "system_blocks": len(body.get("system") or []) if isinstance(body.get("system"), list) else 1,
                "has_auth": bool(request.headers.get("authorization") or request.headers.get("x-api-key")),
                "anthropic_beta": request.headers.get("anthropic-beta"),
                "session_id": request.headers.get("x-claude-code-session-id"),
                "path": str(request.url.path),
            }) + "\n")
    if body.get("stream"):
        return StreamingResponse(_sse(body.get("model")), media_type="text/event-stream")
    return JSONResponse({
        "id": "msg_fixture", "type": "message", "role": "assistant",
        "model": body.get("model"), "content": [{"type": "text", "text": REPLY}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 5},
    })


@mock.post("/v1/messages/count_tokens")
async def count_tokens(request: Request) -> Any:
    await request.json()
    return JSONResponse({"input_tokens": 100})


@mock.get("/v1/models")
async def models() -> Any:
    return JSONResponse({"data": [{"id": "claude-sonnet-5", "display_name": "Claude Sonnet 5"}]})


async def _sse(model: str | None):
    def ev(name: str, data: dict[str, Any]) -> bytes:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()

    yield ev("message_start", {
        "type": "message_start",
        "message": {"id": "msg_fixture", "type": "message", "role": "assistant",
                    "model": model, "content": [], "stop_reason": None, "stop_sequence": None,
                    "usage": {"input_tokens": 100, "output_tokens": 1}},
    })
    yield ev("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "text", "text": ""}})
    for piece in REPLY.split(" "):
        yield ev("content_block_delta", {"type": "content_block_delta", "index": 0,
                                         "delta": {"type": "text_delta", "text": piece + " "}})
    yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield ev("message_delta", {"type": "message_delta",
                               "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                               "usage": {"output_tokens": 5}})
    yield ev("message_stop", {"type": "message_stop"})


def main() -> None:
    from amort.proxy.server import app as proxy_app

    threading.Thread(
        target=lambda: uvicorn.run(mock, host="127.0.0.1", port=MOCK_PORT, log_level="warning"),
        daemon=True,
    ).start()
    print(f"fixture upstream on :{MOCK_PORT}, amortize proxy on :{PROXY_PORT}", flush=True)
    uvicorn.run(proxy_app, host="127.0.0.1", port=PROXY_PORT, log_level="warning")


if __name__ == "__main__":
    main()
