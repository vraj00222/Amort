"""The comparison harness — `amort demo`. **Demo-only, not the request path.**

In normal use Amortize is invisible: you set one env var and your client behaves
exactly as before. This module is the *pitch*, not the product — it deliberately
runs the same task twice down two lanes so the difference can be put on screen.
Nothing here is imported by `amort.proxy`.

## The four runs

    A-cold   baseline  → provider directly, full tool catalogue
    B-cold   amortize  → identical agent, through the local proxy
    A-warm   baseline  → the same task asked again (nothing is reused)
    B-warm   amortize  → the same task asked again (Layer 2 would replay here)

A and B alternate rather than running A twice then B twice: interleaving keeps a
warming network or a rate-limit backoff from landing entirely on one lane.

## What this build will show, and why that is the point

Layer 1 and Layer 2 are stubs, so **all four runs cost the same**. The harness is
built to prove that honestly: it computes the deltas from measurements rather
than asserting them, and `report.py` prints `0%` when the answer is 0%. A demo
harness that can only produce a favourable number is not evidence of anything.
The warm path is already wired (`mode="warm"`, skill lookup, parity grading), so
when the layers land the same command produces the real table with no changes here.
"""

from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from rich.console import Console

from amort.config import get_settings
from amort.demo import stage
from amort.ledger.events import RunRecord, StepEvent, emit, emit_run, flush
from amort.skills.grader import ParityResult, grade, grade_accuracy
from amort.skills.recorder import RunRecorder

console = Console()

Lane = Literal["baseline", "amortize"]
Mode = Literal["cold", "warm"]

TASKS = {"ticket_triage": "amort.demo.tasks.ticket_triage"}


@dataclass
class RunResult:
    """One cell of the 2x2, plus everything needed to explain it."""

    lane: Lane
    mode: Mode
    run_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    wall_ms: int
    llm_calls: int
    tool_calls: int
    output: Any
    output_hash: str
    simulated: bool
    ok: bool
    error: str | None = None
    skill_id: str | None = None
    replay_fallback: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane, "mode": self.mode, "run_id": self.run_id,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens, "cost_usd": round(self.cost_usd, 6),
            "wall_ms": self.wall_ms, "llm_calls": self.llm_calls, "tool_calls": self.tool_calls,
            "output_hash": self.output_hash, "simulated": self.simulated,
            "ok": self.ok, "error": self.error, "skill_id": self.skill_id,
            "replay_fallback": self.replay_fallback,
        }


@dataclass
class DemoResult:
    """Everything `report.py` needs, and everything `demo_report.json` records."""

    task: str
    model: str
    live: bool
    simulated: bool
    ledger_backend: str
    memory_backend: str
    proxy_url: str
    started_at: str
    runs: dict[str, RunResult] = field(default_factory=dict)
    parity: dict[str, ParityResult] = field(default_factory=dict)
    accuracy: dict[str, ParityResult] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _run_once(
    module: Any,
    *,
    lane: Lane,
    mode: Mode,
    model: str,
    live: bool,
    proxy_url: str | None,
    api_key: str | None,
) -> tuple[RunResult, dict[str, Any]]:
    """Execute one cell. Lane B routes through the proxy by setting `base_url`.

    Returns the RunResult plus the recorder's Case dict — the compile hook
    needs the raw cases, not just the rollups.
    """
    settings = get_settings()
    skill_id: str | None = None
    replay_fallback: str | None = None
    took_warm_path = False
    output: Any = None

    recorder = RunRecorder(
        lane=lane, mode=mode, system=module.SYSTEM, user_msg=module.TASK_PROMPT,
        tool_names=module.TOOL_NAMES, model=model, simulated=not live,
    )
    started = time.perf_counter()

    # --- the warm path, when the lane and mode call for it ------------------
    if lane == "amortize" and mode == "warm":
        from amort.skills.replayer import replay
        from amort.skills.store_everos import fingerprint, fingerprint_query, search_skill

        fp = fingerprint(module.SYSTEM, module.TASK_PROMPT, module.TOOL_NAMES)
        match = search_skill(fp, fingerprint_query(module.SYSTEM, module.TASK_PROMPT, module.TOOL_NAMES))
        if match and match.is_confident:
            skill_id = match.skill_id
            outcome = replay(match.skill, {
                "user_msg": module.TASK_PROMPT,
                "tool_executor": module.execute_tool,
                "model": model,
                "base_url": f"{settings.novita_api_url.rstrip('/')}/v1",
                "api_key": settings.novita_api_key,
            })
            if outcome.took_warm_path:
                _replay_into_recorder(recorder, outcome, skill_id=skill_id, module=module)
                output = outcome.output
                took_warm_path = True
            replay_fallback = outcome.fallback
        else:
            replay_fallback = "no confident skill match (Layer 2 compiles none yet)"

    if took_warm_path:
        pass  # the recorder already holds the replayed trajectory
    elif live:
        # The OpenAI SDK appends `/chat/completions` to base_url, so both lanes
        # need the `/v1` suffix — lane B's lands on the proxy's
        # `/v1/chat/completions` route, which relays to Novita.
        output, recorder = module.run_live(
            lane=lane, mode=mode, model=model,
            base_url=(
                f"{proxy_url}/v1" if lane == "amortize"
                else f"{settings.novita_api_url.rstrip('/')}/v1"
            ),
            api_key=api_key, recorder=recorder,
        )
    else:
        output, recorder = module.run_offline(
            lane=lane, mode=mode, model=model, recorder=recorder,
            lighten=(lane == "amortize"),
        )
    wall_ms = int((time.perf_counter() - started) * 1000)

    case = recorder.to_case()
    case["skill_id"] = skill_id
    emit_run(RunRecord.from_case(case))

    # Record the run as a Case so Layer 2 has material to distil later.
    from amort.skills.store_everos import record_case

    try:
        record_case(case)
    except Exception as exc:  # noqa: BLE001 — memory must not fail the demo
        console.print(f"[yellow]note:[/yellow] could not record case: {exc}")

    return RunResult(
        lane=lane, mode=mode, run_id=recorder.run_id,
        input_tokens=recorder.input_tokens, output_tokens=recorder.output_tokens,
        cost_usd=recorder.cost_usd, wall_ms=wall_ms,
        llm_calls=recorder.llm_calls, tool_calls=recorder.tool_calls,
        output=output, output_hash=recorder.output_hash, simulated=not live,
        ok=recorder.ok, error=recorder.error,
        skill_id=skill_id, replay_fallback=replay_fallback,
    ), case


def _replay_into_recorder(
    rec: RunRecorder, outcome: Any, *, skill_id: str, module: Any
) -> None:
    """Mirror `outcome.steps` (`RecordedStep.to_dict()`-shaped) into the
    recorder, emitting one StepEvent per step exactly as the live loop does."""
    task_name = getattr(module, "TASK_NAME", "")
    common = {
        "run_id": rec.run_id, "lane": rec.lane, "mode": rec.mode,
        "task_fingerprint": rec.task_fingerprint,
    }
    for s in outcome.steps:
        kind = s.get("kind")
        name = str(s.get("name") or "")
        meta = dict(s.get("meta") or {})
        wall_ms = int(s.get("wall_ms") or 0)
        if kind == "llm":
            step = rec.llm_step(
                s.get("model") or name or "llm",
                input_tokens=int(s.get("input_tokens") or 0),
                output_tokens=int(s.get("output_tokens") or 0),
                cost_usd=float(s.get("cost_usd") or 0.0),
                wall_ms=wall_ms, meta=meta,
            )
            emit(StepEvent(
                **common, step_idx=step.step_idx, kind="llm",
                name=name or step.name, model=s.get("model"),
                input_tokens=step.input_tokens, output_tokens=step.output_tokens,
                cost_usd=step.cost_usd, wall_ms=wall_ms,
                meta={**meta, "task": task_name},
            ))
        elif kind == "tool":
            step = rec.tool_step(name, args=s.get("args"), wall_ms=wall_ms, meta=meta)
            emit(StepEvent(
                **common, step_idx=step.step_idx, kind="tool", name=name,
                wall_ms=wall_ms, meta={**meta, "task": task_name},
            ))
        elif kind == "replay":
            step = rec.replay_step(skill_id, wall_ms=wall_ms, **meta)
            emit(StepEvent(
                **common, step_idx=step.step_idx, kind="replay",
                name=f"skill:{skill_id}", wall_ms=wall_ms,
                meta={**meta, "task": task_name},
            ))
    rec.finish(outcome.output)


def _compile_hook(case_a: dict[str, Any], case_b: dict[str, Any],
                  *, run: RunResult, result: DemoResult) -> None:
    """Hand the two cold Cases to Layer 2's compiler after B_cold completes.

    Per CONTRACTS.md the compile call is logged under B_cold's run_id as
    `kind="llm", name="compile", meta.phase="compile"`. The compiler emits its
    own LLM-cost StepEvents; `compile_skill`'s return value exposes no usage,
    so this marker is logged at $0.00 rather than inventing a number.
    """
    from amort.skills.compiler import compile_skill

    started = time.perf_counter()
    skill = None
    error: str | None = None
    try:
        skill = compile_skill([case_a, case_b])
    except Exception as exc:  # noqa: BLE001 — compiling must never fail the demo
        error = f"{type(exc).__name__}: {exc}"
    wall_ms = int((time.perf_counter() - started) * 1000)

    skill_id = skill.skill_id if skill is not None else None
    emit(StepEvent(
        run_id=run.run_id, lane=run.lane, mode=run.mode,
        task_fingerprint=case_b.get("task_fingerprint", ""),
        step_idx=len(case_b.get("steps") or []), kind="llm", name="compile",
        wall_ms=wall_ms,
        meta={"phase": "compile", "skill_id": skill_id, "task": result.task,
              "cost_note": "marker at $0.00 — the compiler logs its own LLM usage"},
    ))
    if error:
        result.notes.append(f"compile_skill([A_cold, B_cold]) raised: {error}")
    elif skill is None:
        result.notes.append(
            "compile_skill([A_cold, B_cold]) returned no skill — the Layer 2 compiler "
            "is not merged yet (or the cases did not qualify), so nothing was distilled."
        )
    else:
        result.notes.append(
            f"compiled skill {skill_id} (status={skill.status}) from the two cold runs"
        )


def run_demo(
    *,
    task: str = "ticket_triage",
    lanes: str = "both",
    repeat: bool = True,
    live: bool = True,
    write_report: bool = True,
) -> DemoResult:
    """Run the 2x2 and render it. Returns the result for programmatic use."""
    import importlib

    if task not in TASKS:
        raise SystemExit(f"unknown task {task!r}; available: {', '.join(TASKS)}")
    module = importlib.import_module(TASKS[task])

    settings = get_settings()
    settings.ensure_dirs()
    # Live runs drive Novita (the working upstream); offline keeps the
    # configured demo model for its labelled estimates.
    model = settings.novita_model if live else settings.amort_demo_model
    api_key = settings.novita_api_key

    from amort.ledger.events import active_backend
    from amort.skills.store_everos import get_store

    notes: list[str] = []
    if live and not api_key:
        live = False
        model = settings.amort_demo_model
        notes.append(
            "No NOVITA_API_KEY, so the demo ran offline: a scripted agent calls the same "
            "8 tools and token counts are ESTIMATED from the real payload size (chars/4). "
            "Every number below is tagged simulated=true. Set the key and re-run for measured numbers."
        )

    proxy_url = settings.proxy_base_url
    if live:
        import httpx

        try:
            httpx.get(f"{proxy_url}/health", timeout=3)
        except Exception:  # noqa: BLE001
            raise SystemExit(
                f"Lane B needs the proxy running at {proxy_url}. Start it with `amort up` "
                "in another terminal, then re-run `amort demo`."
            ) from None

    result = DemoResult(
        task=task, model=model, live=live, simulated=not live,
        ledger_backend=active_backend(), memory_backend=get_store().backend_name,
        proxy_url=proxy_url,
        started_at=_dt.datetime.now(_dt.UTC).isoformat(),
        notes=notes,
    )

    want_a = lanes in ("both", "baseline")
    want_b = lanes in ("both", "amortize")

    # A-first, B-first (cold), then the re-prompt pass. Interleaved so a warming
    # network or a rate-limit backoff can't land entirely on one lane.
    plan: list[tuple[str, Lane, Mode]] = []
    if want_a:
        plan.append(("A_cold", "baseline", "cold"))
    if want_b:
        plan.append(("B_cold", "amortize", "cold"))
    if repeat:
        if want_a:
            plan.append(("A_warm", "baseline", "warm"))
        if want_b:
            plan.append(("B_warm", "amortize", "warm"))

    console.print(
        f"\n[bold cyan]amort demo[/bold cyan] · task={task} · model={model} · "
        f"{'LIVE' if live else 'OFFLINE (simulated)'} · ledger={result.ledger_backend}\n"
    )
    cases: dict[str, dict[str, Any]] = {}
    for cell, lane, mode in plan:
        label = f"{cell:<7} {lane}/{mode}"
        stage.push({
            "type": "run_start", "cell": cell, "lane": lane, "mode": mode,
            "task": task, "model": model, "simulated": not live,
        })
        with console.status(f"[dim]{label}…[/dim]"):
            run, case = _run_once(
                module, lane=lane, mode=mode, model=model, live=live,
                proxy_url=proxy_url, api_key=api_key,
            )
        result.runs[cell] = run
        cases[cell] = case
        for s in case.get("steps") or []:
            stage.push({
                "type": "step", "cell": cell, "lane": lane, "mode": mode,
                "kind": s["kind"], "name": s["name"],
                "tokens": s["input_tokens"] + s["output_tokens"],
                "cost_usd": s["cost_usd"], "wall_ms": s["wall_ms"],
            })
        stage.push({
            "type": "run_end", "cell": cell, "lane": lane, "mode": mode,
            "tokens": run.total_tokens, "cost_usd": run.cost_usd,
            "wall_ms": run.wall_ms, "llm_calls": run.llm_calls,
            "tool_calls": run.tool_calls, "ok": run.ok, "simulated": run.simulated,
        })
        console.print(
            f"  {label}  {run.total_tokens:>8,} tok  ${run.cost_usd:>7.4f}  "
            f"{run.wall_ms / 1000:>5.1f}s  {run.llm_calls} llm / {run.tool_calls} tool"
            + (f"  [yellow]{run.error}[/yellow]" if not run.ok else "")
        )
        if cell == "B_cold" and "A_cold" in cases:
            _compile_hook(cases["A_cold"], case, run=run, result=result)
    flush()

    # --- grading ------------------------------------------------------------
    a_cold, b_cold = result.runs.get("A_cold"), result.runs.get("B_cold")
    b_warm = result.runs.get("B_warm")

    if a_cold and b_cold:
        result.parity["A_cold_vs_B_cold"] = grade(a_cold.output, b_cold.output)
    if b_cold and b_warm:
        result.parity["B_cold_vs_B_warm"] = grade(
            b_cold.output, b_warm.output,
            reason_when_missing="Layer 2 is a stub — no replay happened, so the warm run is a cold run",
        )
    expected = module.expected_report() if hasattr(module, "expected_report") else None
    for cell, run in result.runs.items():
        if expected is not None:
            result.accuracy[cell] = grade_accuracy(run.output, expected)

    if b_warm and b_warm.replay_fallback:
        result.notes.append(f"Warm lane fell back to the full agent: {b_warm.replay_fallback}")

    for key, parity in result.parity.items():
        stage.push({
            "type": "parity", "key": key,
            "verdict": parity.verdict, "symbol": parity.symbol,
        })

    from amort.demo.report import render, to_dict, write_json

    render(result)
    if write_report:
        path = write_json(result)
        console.print(f"[dim]wrote {path}[/dim]")

    warm_parity = result.parity.get("B_cold_vs_B_warm")
    stage.push({
        "type": "final", "deltas": to_dict(result)["deltas"],
        "parity": warm_parity.verdict if warm_parity else "n/a",
        "simulated": result.simulated,
    })
    return result


__all__ = ["DemoResult", "RunResult", "TASKS", "run_demo"]
