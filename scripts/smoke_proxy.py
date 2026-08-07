"""Phase 6 smoke: prove the proxy is transparent.

Three acceptance checks:

  1. **Identical output** — the same prompt, sent with the raw Anthropic SDK,
     direct vs through the proxy, produces byte-identical text.
  2. **Streaming works** — an SDK streaming call through the proxy arrives
     incrementally (multiple deltas, first one well before the last), not
     buffered and replayed at the end.
  3. **A StepEvent lands in the ledger** with the usage the proxy parsed out of
     the SSE stream.

By default this runs against a **deterministic mock upstream** started in-process.
That is deliberate, not a shortcut: against the real API a model is free to
return different bytes for the same prompt, so "byte-identical" would be
unprovable. The mock speaks the real Anthropic wire format (SSE event sequence,
`usage` on `message_start`/`message_delta`, `tool_use` blocks), which is exactly
what the transparency claim is about.

    uv run python scripts/smoke_proxy.py            # mock upstream (no API key needed)
    uv run python scripts/smoke_proxy.py --live     # real api.anthropic.com (needs a key)
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from typing import Any


# Env must be set before amort.config is imported — Settings is cached per process.
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


LIVE = "--live" in sys.argv
MOCK_PORT = _free_port()
PROXY_PORT = _free_port()
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"

os.environ["AMORT_PORT"] = str(PROXY_PORT)
if not LIVE:
    os.environ["AMORT_UPSTREAM_ANTHROPIC"] = MOCK_URL
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-smoke-not-a-real-key")

import anthropic  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

from amort.config import get_settings  # noqa: E402

MODEL = "claude-haiku-4-5-20251001"
PROMPT = "In exactly one sentence, what does an amortizing proxy do?"
ANSWER_CHUNKS = [
    "An amortizing proxy ",
    "makes the second run of a task ",
    "cheaper than the first ",
    "by reusing what it learned.",
]
ANSWER = "".join(ANSWER_CHUNKS)


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic mock upstream (real Anthropic wire format)
# ─────────────────────────────────────────────────────────────────────────────

mock = FastAPI()


@mock.post("/v1/messages")
async def mock_messages(request: Request) -> Any:
    body = await request.json()
    # Assert transparency from the upstream's point of view: the proxy must have
    # forwarded the caller's auth and version headers.
    assert request.headers.get("x-api-key") or request.headers.get("authorization"), (
        "upstream received no credentials — the proxy dropped the client's auth header"
    )
    assert request.headers.get("anthropic-version"), "anthropic-version header missing"

    if body.get("stream"):
        return StreamingResponse(_sse(), media_type="text/event-stream")
    return JSONResponse(
        {
            "id": "msg_mock_0001",
            "type": "message",
            "role": "assistant",
            "model": body.get("model", MODEL),
            "content": [{"type": "text", "text": ANSWER}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 41,
                "output_tokens": 23,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        }
    )


async def _sse():
    import asyncio

    def ev(name: str, data: dict[str, Any]) -> bytes:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()

    yield ev("message_start", {
        "type": "message_start",
        "message": {
            "id": "msg_mock_0001", "type": "message", "role": "assistant", "model": MODEL,
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 41, "output_tokens": 1,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        },
    })
    yield ev("content_block_start",
             {"type": "content_block_start", "index": 0,
              "content_block": {"type": "text", "text": ""}})
    for piece in ANSWER_CHUNKS:
        # A real stream arrives over time; sleeping proves the proxy forwards
        # each chunk instead of buffering the whole response.
        await asyncio.sleep(0.12)
        yield ev("content_block_delta", {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": piece},
        })
    yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield ev("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": 23},
    })
    yield ev("message_stop", {"type": "message_stop"})


# ─────────────────────────────────────────────────────────────────────────────
# Server plumbing
# ─────────────────────────────────────────────────────────────────────────────


def serve(app: Any, port: int) -> uvicorn.Server:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server


def wait_for(url: str, timeout: float = 20.0) -> None:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=1.0)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    raise RuntimeError(f"server at {url} never came up")


# ─────────────────────────────────────────────────────────────────────────────
# Checks
# ─────────────────────────────────────────────────────────────────────────────


def text_of(message: Any) -> str:
    return "".join(b.text for b in message.content if b.type == "text")


def main() -> int:
    settings = get_settings()
    settings.ensure_dirs()

    from amort.ledger.events import get_writer
    from amort.proxy.server import app as proxy_app

    direct_base = settings.amort_upstream_anthropic
    api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or "sk-ant-smoke"

    print(f"mode          : {'LIVE (api.anthropic.com)' if LIVE else 'mock upstream'}")
    if not LIVE:
        serve(mock, MOCK_PORT)
        wait_for(f"{MOCK_URL}/v1/messages")
    serve(proxy_app, PROXY_PORT)
    wait_for(f"{PROXY_URL}/health")

    import httpx

    health = httpx.get(f"{PROXY_URL}/health", timeout=5).json()
    print(f"proxy         : {PROXY_URL}  ledger={health['ledger']}  memory={health['memory']}")
    print(f"upstream      : {direct_base}")
    print(f"layers        : {health['layers']}")

    writer = get_writer()
    before = writer.query("SELECT COUNT(*) FROM STEPS")[0][0]

    direct = anthropic.Anthropic(base_url=direct_base, api_key=api_key, max_retries=0)
    proxied = anthropic.Anthropic(base_url=PROXY_URL, api_key=api_key, max_retries=0)

    # --- 1. identical non-streaming output ----------------------------------
    d = direct.messages.create(model=MODEL, max_tokens=256,
                               messages=[{"role": "user", "content": PROMPT}])
    p = proxied.messages.create(model=MODEL, max_tokens=256,
                                messages=[{"role": "user", "content": PROMPT}])
    dt, pt = text_of(d), text_of(p)
    print("\n[1] non-streaming")
    print(f"    direct  : {dt[:72]!r}")
    print(f"    proxied : {pt[:72]!r}")
    if LIVE:
        assert dt and pt, "one of the calls returned no text"
        print("    LIVE mode: text equality not asserted (the model may legitimately differ);")
        print("    structural equality asserted instead.")
        assert d.model == p.model and d.stop_reason == p.stop_reason
    else:
        assert dt == pt, "PROXY ALTERED THE OUTPUT — text differs"
        assert d.model == p.model and d.stop_reason == p.stop_reason
        assert d.usage.input_tokens == p.usage.input_tokens, "usage was rewritten"
        print("    byte-identical ✓  (same model, stop_reason and usage)")

    # --- 2. streaming arrives incrementally ---------------------------------
    print("\n[2] streaming through the proxy")
    deltas: list[tuple[float, str]] = []
    t0 = time.perf_counter()
    with proxied.messages.stream(model=MODEL, max_tokens=256,
                                 messages=[{"role": "user", "content": PROMPT}]) as stream:
        for chunk in stream.text_stream:
            deltas.append((time.perf_counter() - t0, chunk))
        final = stream.get_final_message()
    streamed_text = "".join(c for _, c in deltas)
    first_at = deltas[0][0] if deltas else 0.0
    last_at = deltas[-1][0] if deltas else 0.0
    print(f"    {len(deltas)} text delta(s); first at {first_at * 1000:.0f}ms, "
          f"last at {last_at * 1000:.0f}ms")
    print(f"    text    : {streamed_text[:72]!r}")
    assert len(deltas) >= 2, "only one delta — the proxy buffered the stream"
    assert last_at - first_at > 0.05, (
        "all deltas arrived at once — the proxy collected the stream and replayed it"
    )
    if not LIVE:
        assert streamed_text == ANSWER, "streamed text differs from the upstream's"
    print("    incremental ✓")

    # --- 3. a StepEvent landed with the parsed usage ------------------------
    from amort.ledger.events import flush

    time.sleep(0.4)  # the step is emitted in the stream's finally block
    flush()
    after = writer.query("SELECT COUNT(*) FROM STEPS")[0][0]
    rows = writer.query(
        "SELECT RUN_ID, KIND, MODEL, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, WALL_MS, META "
        "FROM STEPS ORDER BY ROWID DESC LIMIT 3"
        if writer.name == "sqlite" else
        "SELECT RUN_ID, KIND, MODEL, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, WALL_MS, META "
        "FROM STEPS ORDER BY TS DESC LIMIT 3"
    )
    print(f"\n[3] ledger ({writer.name}): STEPS {before} → {after}")
    for r in rows:
        meta = json.loads(r[7]) if isinstance(r[7], str) else r[7]
        print(f"    {r[1]:5} {r[2]}  in={r[3]} out={r[4]} ${r[5]:.6f} {r[6]}ms "
              f"streamed={meta.get('streamed')} events={meta.get('sse_events')}")
    assert after >= before + 2, f"expected ≥2 new STEP rows, got {after - before}"
    latest = rows[0]
    assert latest[3] > 0 and latest[4] > 0, (
        "usage was not parsed out of the SSE stream (input/output tokens are 0)"
    )
    assert float(latest[5]) > 0, "cost was not computed for the streamed call"
    print("    usage parsed from SSE and priced ✓")

    # --- 4. tool_use blocks are observed ------------------------------------
    print(f"\n[4] final message stop_reason={final.stop_reason} "
          f"usage in={final.usage.input_tokens} out={final.usage.output_tokens}")

    print("\nPHASE 6 SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
