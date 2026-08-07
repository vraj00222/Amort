"""Acceptance test — Layer 2 AMORTIZE headline claims (BUILD_SPEC B6).

Written BEFORE the implementation (test-first). Flow, all against live Novita:

  1. two cold runs of the fixture task (direct + via nothing — no proxy needed;
     FULL REPLAY is harness-side), both recorded as Cases
  2. compile_skill([case_a, case_b]) -> Skill; two agreeing ok runs with the
     same fingerprint promote candidate -> verified at compile time
  3. warm FULL REPLAY via replay(skill, request) with the task's tool executor:
       (a) >= 85% cheaper than this session's own cold baseline (measured)
       (b) parity: field-exact equal to the cold output
  4. (c) broken guard: a tool executor that returns an empty fixture must abort
     the replay cleanly (ok=False, fallback set) — and a cold run still works
  5. (d) [--plan-replay] PLAN REPLAY through the proxy is strictly cheaper than
     cold; prints the real % (no fixed bar). Needs the integrator wiring.

Exit 0 only when every executed check passes.
"""

from __future__ import annotations

import os
import sys
from typing import Any

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

FAILURES: list[str] = []
STATE: dict[str, Any] = {}


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        print(f"  PASS  {name}  {detail}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(name)
        print(f"  FAIL  {name}  ({type(exc).__name__}: {exc})")


def _cold_run(lane: str):
    from amort.config import get_settings
    from amort.demo.tasks import ticket_triage as task

    s = get_settings()
    report, rec = task.run_live(
        lane=lane, mode="cold", model=s.novita_model,
        base_url=f"{s.novita_api_url.rstrip('/')}/v1", api_key=s.novita_api_key,
    )
    assert rec.ok, f"cold run failed: {rec.error}"
    return report, rec


def check_cold_and_record() -> str:
    from amort.skills.store_everos import record_case

    report_a, rec_a = _cold_run("baseline")
    report_b, rec_b = _cold_run("amortize")
    case_a, case_b = rec_a.to_case(), rec_b.to_case()
    record_case(case_a)
    record_case(case_b)
    STATE.update(case_a=case_a, case_b=case_b, report_b=report_b,
                 cold_cost=rec_b.cost_usd, cold_tokens=rec_b.input_tokens + rec_b.output_tokens)
    return f"[2 cold runs, cold baseline ${rec_b.cost_usd:.4f} / {STATE['cold_tokens']:,} tok]"


def check_compile_promotes() -> str:
    from amort.skills.compiler import compile_skill

    skill = compile_skill([STATE["case_a"], STATE["case_b"]])
    assert skill is not None, "compiler returned None on two ok cases"
    assert skill.status == "verified", (
        f"two agreeing cold runs must promote at compile time, got {skill.status!r}"
    )
    assert skill.tools_required, "skill must declare tools_required (Layer 1's warm subset)"
    STATE["skill"] = skill
    return f"[{skill.skill_id} verified, tools={skill.tools_required}]"


def check_full_replay() -> str:
    from amort.config import get_settings
    from amort.demo.tasks import ticket_triage as task
    from amort.skills.grader import grade
    from amort.skills.replayer import replay

    s = get_settings()
    outcome = replay(STATE["skill"], {
        "user_msg": task.TASK_PROMPT,
        "tool_executor": task.execute_tool,
        "model": s.novita_model,
        "base_url": f"{s.novita_api_url.rstrip('/')}/v1",
        "api_key": s.novita_api_key,
    })
    assert outcome.ok, f"replay fell back: {outcome.fallback}"
    assert outcome.took_warm_path and outcome.llm_calls <= 2, (
        f"warm path must use <= 2 LLM calls, used {outcome.llm_calls}"
    )
    parity = grade(STATE["report_b"], outcome.output)
    assert parity.ok, f"warm output differs from cold: {parity.reason} {parity.mismatches[:3]}"

    warm_cost = sum(float(step.get("cost_usd", 0)) for step in outcome.steps)
    cold_cost = STATE["cold_cost"]
    assert cold_cost > 0, "cold baseline recorded no cost"
    saving = 1 - warm_cost / cold_cost
    assert saving >= 0.85, f"warm saving {saving:.1%} < 85% (${warm_cost:.4f} vs ${cold_cost:.4f})"
    return f"[parity OK; ${cold_cost:.4f} -> ${warm_cost:.4f}, -{saving:.1%}, {outcome.llm_calls} llm]"


def check_broken_guard_falls_back() -> str:
    from amort.config import get_settings
    from amort.demo.tasks import ticket_triage as task
    from amort.skills.replayer import replay

    s = get_settings()

    def empty_fixture_executor(name: str, args: dict[str, Any]) -> Any:
        if name == "fetch_tickets":
            return {"range": args.get("range"), "count": 0, "tickets": []}
        return task.execute_tool(name, args)

    outcome = replay(STATE["skill"], {
        "user_msg": task.TASK_PROMPT,
        "tool_executor": empty_fixture_executor,
        "model": s.novita_model,
        "base_url": f"{s.novita_api_url.rstrip('/')}/v1",
        "api_key": s.novita_api_key,
    })
    assert not outcome.ok, "an empty fixture must trip a guard, not produce output"
    assert outcome.fallback, "fallback reason must be recorded"
    # ...and the cold path still completes after the fallback:
    report, rec = _cold_run("amortize")
    assert rec.ok and isinstance(report, dict)
    return f"[guard tripped: {outcome.fallback!r}; cold fallback completed]"


def check_plan_replay() -> str:
    import subprocess
    import time

    import httpx

    from amort.config import get_settings
    from amort.demo.tasks import ticket_triage as task

    s = get_settings()
    port = 4453
    env = os.environ | {"AMORT_LIGHTEN": "false"}  # isolate Layer 2's effect
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "amort.proxy.server:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        report, rec = task.run_live(
            lane="amortize", mode="warm", model=s.novita_model,
            base_url=f"http://127.0.0.1:{port}/v1", api_key=s.novita_api_key,
        )
        assert rec.ok, f"plan-replay run failed: {rec.error}"
        cold_tokens = STATE["cold_tokens"]
        warm_tokens = rec.input_tokens + rec.output_tokens
        assert warm_tokens < cold_tokens, (
            f"plan replay not cheaper: {warm_tokens:,} vs cold {cold_tokens:,} tok"
        )
        return f"[{cold_tokens:,} -> {warm_tokens:,} tok, -{1 - warm_tokens / cold_tokens:.1%} (real number, no fixed bar)]"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main() -> int:
    from amort.config import get_settings

    if not get_settings().novita_api_key:
        print("accept_layer2: FAIL — NOVITA_API_KEY required (live-only test)")
        return 1
    plan_replay = "--plan-replay" in sys.argv
    print("accept_layer2 — AMORTIZE acceptance (live)")
    check("2 cold runs recorded as Cases", check_cold_and_record)
    if not FAILURES:
        check("compile promotes 2 agreeing runs to verified", check_compile_promotes)
    if not FAILURES:
        check("FULL REPLAY >=85% cheaper, parity, <=2 llm", check_full_replay)
        check("broken guard -> clean cold fallback", check_broken_guard_falls_back)
    if plan_replay and not FAILURES:
        check("PLAN REPLAY via proxy cheaper than cold", check_plan_replay)
    elif not plan_replay:
        print("  NOTE  plan-replay check skipped (--plan-replay) — runs after integrator wiring; see BUILD_SPEC B6(d)")
    print(f"accept_layer2: {'PASS' if not FAILURES else 'FAIL ' + str(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
