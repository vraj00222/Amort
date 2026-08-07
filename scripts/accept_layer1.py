"""Acceptance test — Layer 1 LIGHTEN headline claims (BUILD_SPEC A4).

Written BEFORE the implementation (test-first). Encodes the demo's Layer-1 claims:

  unit (no network, always run):
    1. the 8-tool fixture request is dieted to stubs + `amort__search_tools`,
       schema tokens (chars/4, stub text INCLUDED) reduced >= 60%
    2. a small request (<= threshold tools) passes through untouched
    3. `amort__search_tools` resolves catalogue matches (substring + fuzzy)
    4. spill round-trip: oversized result -> handle + preview + digest; read back
       via head|tail|grep
  live (--live, needs NOVITA_API_KEY; run from gate level 2):
    5. end-to-end through two proxies (AMORT_LIGHTEN on vs off): field-exact
       equal final reports, strictly fewer measured input tokens with L1 on

Exit code 0 only when every executed check passes. A check that fails because
the implementation does not exist yet prints FAIL(not implemented) — that is
the test-first contract, not an error in this script.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from typing import Any

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


def _tokens(payload: Any) -> int:
    return len(json.dumps(payload, default=str)) // 4


def _fixture_request(tools: list[dict[str, Any]]) -> Any:
    from amort.demo.tasks.ticket_triage import SYSTEM, TASK_PROMPT
    from amort.proxy.interceptors import ProxyRequest

    body = {
        "model": "deepseek/deepseek-v4-flash",
        "max_tokens": 8192,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": TASK_PROMPT},
        ],
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
    )


# ─── unit checks ─────────────────────────────────────────────────────────────


def check_dieting() -> str:
    from amort.demo.tasks.ticket_triage import TOOLS_OPENAI
    from amort.proxy.interceptors import before_request

    req = _fixture_request(copy.deepcopy(TOOLS_OPENAI))
    original = copy.deepcopy(req.body)
    out = before_request(req)

    assert out.body is not None and out.body is not original, "must return a fresh body dict"
    tools_after = out.body.get("tools") or []
    names = [t.get("function", {}).get("name", "") for t in tools_after]
    assert "amort__search_tools" in names, f"synthetic tool missing, got {names}"
    assert all(n.startswith("amort__") for n in names), (
        f"fresh conversation must carry only synthetic tools, got {names}"
    )

    before_tok = _tokens(TOOLS_OPENAI)
    after_tok = _tokens(tools_after)  # stub text lives in the tool description — counted
    reduction = 1 - after_tok / before_tok
    assert reduction >= 0.60, f"schema reduction {reduction:.1%} < 60%"

    layer1 = (out.meta or {}).get("layer1") or {}
    for key in ("schema_tokens_before", "schema_tokens_after", "spilled_tokens"):
        assert key in layer1, f"meta.layer1.{key} missing"
    return f"[schema {before_tok:,} -> {after_tok:,} tok, -{reduction:.1%}]"


def check_small_request_untouched() -> str:
    from amort.demo.tasks.ticket_triage import TOOLS_OPENAI
    from amort.proxy.interceptors import before_request

    small = copy.deepcopy(TOOLS_OPENAI[:3])  # threshold default is 4
    req = _fixture_request(small)
    parsed = req.body
    out = before_request(req)
    assert out.body is parsed, "<= threshold tools must pass through with body untouched"
    return "[3 tools -> untouched]"


def check_search_resolution() -> str:
    from amort.demo.tasks.ticket_triage import TOOLS_OPENAI
    from amort.proxy.lighten import resolve_search_tools

    hits = resolve_search_tools(TOOLS_OPENAI, "fetch the open support tickets")
    hit_names = [t["function"]["name"] for t in hits]
    assert "fetch_tickets" in hit_names, f"expected fetch_tickets in {hit_names}"
    full = next(t for t in hits if t["function"]["name"] == "fetch_tickets")
    assert full["function"]["parameters"].get("properties"), "must return the FULL schema"

    fuzzy = resolve_search_tools(TOOLS_OPENAI, "check service level agreement deadlines")
    assert any(t["function"]["name"] == "check_sla" for t in fuzzy), "fuzzy match failed"
    return f"[query -> {hit_names}]"


def check_spill_roundtrip() -> str:
    from amort.demo.tasks.ticket_triage import execute_tool
    from amort.proxy.lighten import resolve_read_spill, spill_result

    big = json.dumps(execute_tool("fetch_tickets", {"range": "last_7_days"}), default=str)
    assert len(big) // 4 > 1500, "fixture result unexpectedly small — pick a bigger payload"

    replacement = spill_result(big)
    assert isinstance(replacement, str) and len(replacement) // 4 < len(big) // 4, "no shrink"
    assert "amort-spill" in replacement, "replacement must carry the handle marker"
    assert "TKT-" in replacement, "preview/digest must expose the ticket ids"

    handle = replacement.split("amort-spill:")[1].split()[0].strip("]\"' ")
    head = resolve_read_spill(handle, "head", "")
    grep = resolve_read_spill(handle, "grep", "TKT-")
    assert head and grep and "TKT-" in grep, "read_spill head/grep failed"
    # re-entrancy: a replacement is never re-spilled
    assert spill_result(replacement) == replacement, "re-spilled its own replacement"
    return f"[{len(big):,}B spilled -> {len(replacement):,}B handle+preview]"


# ─── live end-to-end ─────────────────────────────────────────────────────────


def _spawn_proxy(port: int, lighten: bool) -> subprocess.Popen:
    # Plan replay off: this test isolates Layer 1, and a verified skill from an
    # earlier Layer-2 run would otherwise hijack both arms of the comparison.
    env = os.environ | {
        "AMORT_LIGHTEN": "true" if lighten else "false",
        "AMORT_PLAN_REPLAY": "false",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "amort.proxy.server:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    import httpx

    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
            return proc
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"proxy on :{port} never became healthy")


def check_live_on_vs_off() -> str:
    """2 runs per arm, compare MEANS — a single pair is a coin flip.

    deepseek's trajectory varies ±1 full turn run-to-run (measured spread on
    one arm: 31k-42k input tokens on identical code), which swamps a
    single-pair comparison. Means over 2 pairs measure the layer, not the dice.
    Parity is still asserted on every individual pair — output equality has no
    noise budget.
    """
    from amort.config import get_settings
    from amort.demo.tasks import ticket_triage as task
    from amort.skills.grader import grade

    settings = get_settings()
    assert settings.novita_api_key, "NOVITA_API_KEY required for the live check"

    baseline_report = None
    tokens: dict[str, list[int]] = {"off": [], "on": []}
    for label, port, lighten in (("off", 4452, False), ("on", 4451, True)):
        proc = _spawn_proxy(port, lighten)
        try:
            for _ in range(2):
                report, rec = task.run_live(
                    lane="amortize", mode="cold", model=settings.novita_model,
                    base_url=f"http://127.0.0.1:{port}/v1", api_key=settings.novita_api_key,
                )
                assert rec.ok, f"lighten={label} run failed: {rec.error}"
                if baseline_report is None:
                    baseline_report = report
                else:
                    parity = grade(baseline_report, report)
                    assert parity.ok, (
                        f"lighten={label} output differs: {parity.reason} {parity.mismatches[:3]}"
                    )
                tokens[label].append(rec.input_tokens)
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    off_mean = sum(tokens["off"]) / len(tokens["off"])
    on_mean = sum(tokens["on"]) / len(tokens["on"])
    assert on_mean < off_mean, (
        f"mean input tokens not reduced: on={tokens['on']} off={tokens['off']}"
    )
    return (
        f"[parity OK on all pairs; mean input tokens {off_mean:,.0f} -> {on_mean:,.0f} "
        f"(-{1 - on_mean / off_mean:.1%}) | off={tokens['off']} on={tokens['on']}]"
    )


def main() -> int:
    live = "--live" in sys.argv
    print("accept_layer1 — LIGHTEN acceptance (unit" + (" + live)" if live else ")"))
    check("dieting >=60% on the 8-tool fixture", check_dieting)
    check("<= threshold tools pass through untouched", check_small_request_untouched)
    check("search_tools resolves substring + fuzzy", check_search_resolution)
    check("spill round-trip head/tail/grep + re-entrancy", check_spill_roundtrip)
    if live:
        check("LIVE: equal output, fewer input tokens (on vs off)", check_live_on_vs_off)
    print(f"accept_layer1: {'PASS' if not FAILURES else 'FAIL ' + str(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
