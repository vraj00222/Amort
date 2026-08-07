"""Focused Layer-1 unit tests (assert-based, no network, no pytest).

    uv run python scripts/test_lighten.py

Covers what accept_layer1's unit checks do not:
  1. the proxy-side search loop against a scripted fake upstream — a mixed
     synthetic + real tool_calls turn (real calls dropped from the splice,
     schemas hydrated, usage accumulated, client never sees synthetics)
  2. loop-cap exhaustion -> one clean re-send of the ORIGINAL raw body
  3. spill round-trip on non-fixture content, incl. determinism by content
  4. carry-forward derivation from visible history + spill of history results
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys

os.environ.setdefault("AMORT_LEDGER", "sqlite")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

FAILURES: list[str] = []


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        print(f"  PASS  {name}  {detail}")
    except Exception as exc:  # noqa: BLE001 — report, don't crash the suite
        FAILURES.append(name)
        print(f"  FAIL  {name}  ({type(exc).__name__}: {exc})")


def _request(tools, messages):
    from amort.proxy.interceptors import ProxyRequest

    body = {
        "model": "fake-model",
        "max_tokens": 512,
        "messages": messages,
        "tools": tools,
    }
    return ProxyRequest(
        provider="openai",
        path="/v1/chat/completions",
        method="POST",
        headers={},
        raw_body=json.dumps(body).encode(),
        body=body,
        stream=False,
        meta={"run_id": "test_lighten"},
    )


def _chat_response(tool_calls=None, content="", usage=(100, 10)):
    import httpx

    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "fake-model",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": usage[0],
            "completion_tokens": usage[1],
            "total_tokens": usage[0] + usage[1],
        },
    }
    return httpx.Response(200, json=payload, headers={"content-type": "application/json"})


def _call(call_id, name, args):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


class _FallbackClient:
    """Stands in for httpx.AsyncClient on the fallback re-send path only."""

    def __init__(self, response):
        self.response = response
        self.sent: list[bytes] = []

    def build_request(self, method, url, headers=None, content=None):
        self.sent.append(content)
        return ("request", content)

    async def send(self, request, stream=True):
        return self.response


def check_search_loop_mixed() -> str:
    from amort.demo.tasks.ticket_triage import SYSTEM, TASK_PROMPT, TOOLS_OPENAI
    from amort.proxy import passthrough
    from amort.proxy.interceptors import before_request

    req = before_request(
        _request(
            copy.deepcopy(TOOLS_OPENAI),
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": TASK_PROMPT},
            ],
        )
    )
    assert req.meta.get("layer1"), "fixture request must arm layer1"

    real_call = _call("call_real", "fetch_tickets", {"range": "last_7_days"})
    script = [
        # mixed turn: one synthetic search + one real call the model jumped ahead on
        _chat_response(
            tool_calls=[
                _call("call_syn", "amort__search_tools", {"query": "fetch tickets and check sla"}),
                real_call,
            ],
            usage=(100, 10),
        ),
        # after hydration the model re-issues the real call — final for the client
        _chat_response(tool_calls=[real_call], usage=(200, 20)),
    ]
    seen_bodies: list[dict] = []

    async def fake_upstream(client, method, url, headers, content):
        seen_bodies.append(json.loads(content))
        return script.pop(0)

    original = passthrough._upstream_json
    passthrough._upstream_json = fake_upstream
    try:
        response = asyncio.run(
            passthrough._lighten_relay(
                req, client=None, url="http://fake/v1/chat/completions", headers={}, provider="openai"
            )
        )
    finally:
        passthrough._upstream_json = original

    assert len(seen_bodies) == 2, f"expected 2 upstream calls, saw {len(seen_bodies)}"

    # iteration 1 carried only the stub
    first_tools = [t["function"]["name"] for t in seen_bodies[0]["tools"]]
    assert first_tools == ["amort__search_tools"], first_tools

    # iteration 2: splice carries ONLY the synthetic call + its tool result,
    # and the matched schemas were hydrated into the outbound tool set
    second = seen_bodies[1]
    spliced = second["messages"][-2]
    assert spliced["role"] == "assistant"
    assert [c["id"] for c in spliced["tool_calls"]] == ["call_syn"], "real call must be dropped"
    result_msg = second["messages"][-1]
    assert result_msg["role"] == "tool" and result_msg["tool_call_id"] == "call_syn"
    assert "fetch_tickets" in result_msg["content"] and "check_sla" in result_msg["content"]
    second_tools = [t["function"]["name"] for t in second["tools"]]
    assert second_tools[0] == "amort__search_tools"
    assert "fetch_tickets" in second_tools and "check_sla" in second_tools
    hydrated = next(t for t in second["tools"] if t["function"]["name"] == "fetch_tickets")
    assert hydrated["function"]["parameters"].get("properties"), "must hydrate the FULL schema"

    # the client sees the final real tool_calls, no synthetics, accumulated usage
    final = json.loads(response.body)
    assert "amort__" not in json.dumps(final), "synthetic tools leaked to the client"
    final_calls = final["choices"][0]["message"]["tool_calls"]
    assert [c["id"] for c in final_calls] == ["call_real"]
    assert final["usage"]["prompt_tokens"] == 300, final["usage"]
    assert final["usage"]["completion_tokens"] == 30, final["usage"]
    assert final["usage"]["total_tokens"] == 330, final["usage"]
    return "[2 iterations, usage 300/30]"


def check_loop_cap_fallback() -> str:
    from amort.demo.tasks.ticket_triage import SYSTEM, TASK_PROMPT, TOOLS_OPENAI
    from amort.proxy import passthrough
    from amort.proxy.interceptors import before_request

    req = before_request(
        _request(
            copy.deepcopy(TOOLS_OPENAI),
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": TASK_PROMPT},
            ],
        )
    )
    assert req.meta.get("layer1"), "fixture request must arm layer1"
    original_raw = req.raw_body

    calls = {"n": 0}

    async def always_searching(client, method, url, headers, content):
        calls["n"] += 1
        return _chat_response(
            tool_calls=[_call(f"c{calls['n']}", "amort__search_tools", {"query": "more tools"})],
            usage=(50, 5),
        )

    fallback = _FallbackClient(_chat_response(content='{"done": true}', usage=(999, 42)))
    original = passthrough._upstream_json
    passthrough._upstream_json = always_searching
    try:
        response = asyncio.run(
            passthrough._lighten_relay(
                req,
                client=fallback,
                url="http://fake/v1/chat/completions",
                headers={},
                provider="openai",
            )
        )
    finally:
        passthrough._upstream_json = original

    assert calls["n"] == 6, f"loop cap must be 6 upstream calls, made {calls['n']}"
    assert fallback.sent == [original_raw], "fallback must re-send the ORIGINAL raw body once"
    final = json.loads(response.body)
    assert final["choices"][0]["message"]["content"] == '{"done": true}'
    assert response.status_code == 200, "never fail the request"
    return "[cap at 6, original body re-sent]"


def check_spill_roundtrip_determinism() -> str:
    from amort.proxy.lighten import resolve_read_spill, spill_result

    small = "tiny result, well under threshold"
    assert spill_result(small) is small, "small results must pass through unchanged"

    rows = [f'{{"row_id": "ROW-{i}", "value": {i * 7}, "note": "padding padding padding"}}'
            for i in range(200)]
    content = "[" + ",\n".join(rows) + "]"
    assert len(content) // 4 > 1500, "test content must exceed the spill threshold"

    first = spill_result(content)
    assert first != content and "amort-spill:" in first
    assert "ROW-0" in first and "ROW-199" in first, "id digest must surface every id"
    assert spill_result(content) == first, "spill must be deterministic by content"
    assert spill_result(first) == first, "a replacement must never be re-spilled"

    handle = first.split("amort-spill:")[1].split("]")[0]
    head = resolve_read_spill(handle, "head", "5")
    assert head.count("\n") <= 5 and "ROW-0" in head
    tail = resolve_read_spill(handle, "tail", "5")
    assert "ROW-199" in tail
    grep = resolve_read_spill(handle, "grep", r"ROW-19\d")
    assert "ROW-190" in grep and "ROW-0\"" not in grep, "grep must honour the regex"
    assert len(resolve_read_spill(handle, "head", "9999")) <= 4200, "output must stay bounded"
    assert "error" in resolve_read_spill("no-such-handle", "head", "")
    return f"[{len(content):,}B -> {len(first):,}B, handle {handle}]"


def check_carry_forward() -> str:
    from amort.demo.tasks.ticket_triage import SYSTEM, TASK_PROMPT, TOOLS_OPENAI, execute_tool
    from amort.proxy.interceptors import before_request

    big = json.dumps(execute_tool("fetch_tickets", {"range": "last_7_days"}), default=str)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": TASK_PROMPT},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [_call("c1", "fetch_tickets", {"range": "last_7_days"})],
        },
        {"role": "tool", "tool_call_id": "c1", "content": big},
    ]
    req = _request(copy.deepcopy(TOOLS_OPENAI), messages)
    out = before_request(req)

    names = [t["function"]["name"] for t in out.body["tools"]]
    assert names == ["amort__search_tools", "fetch_tickets", "amort__read_spill"], names
    carried = out.body["tools"][1]
    assert carried["function"]["parameters"].get("properties"), "carry-forward keeps the FULL schema"

    assert out.body["messages"][0]["content"] == SYSTEM, "system message must never be touched"
    spilled = out.body["messages"][3]["content"]
    assert "amort-spill:" in spilled and "TKT-" in spilled
    layer1 = out.meta["layer1"]
    assert layer1["spilled_tokens"] > 0
    assert layer1["schema_tokens_after"] < layer1["schema_tokens_before"]
    return f"[tools {names}, spilled {layer1['spilled_tokens']:,} tok]"


def main() -> int:
    print("test_lighten — Layer 1 unit tests")
    check("search loop: mixed synthetic+real, usage accumulated", check_search_loop_mixed)
    check("loop cap exhaustion -> original request re-sent once", check_loop_cap_fallback)
    check("spill round-trip: determinism, regex grep, bounds", check_spill_roundtrip_determinism)
    check("carry-forward derived from history; spill in history", check_carry_forward)
    print(f"test_lighten: {'PASS' if not FAILURES else 'FAIL ' + str(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
