"""The playground — `amort playground`, the one-page live demo.

One prompt box. Submitting fans the SAME prompt out to two live lanes:

    left   DIRECT          straight to Novita, full tool catalogue every turn
    right  THROUGH AMORTIZE  via the proxy on :4000 (Layer 1), or a warm
                             skill replay when memory recognises the task (Layer 2)

Both lanes are real runs against Novita — every number on the page is copied
from a recorder step or a graded comparison. On a first prompt the two cold
lanes run and, when their outputs agree field-exactly, the pair is distilled
into a verified Skill (that is Layer 2's promotion rule, not a demo shortcut).
Submitting the same task again replays the skill on the right — live.

Reuses the stage event bus (`stage.push` / SSE) so the memory graph and sponsor
activity carry over unchanged.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from amort.config import get_settings
from amort.demo import stage

logger = logging.getLogger("amort.playground")

_HTML_PATH = Path(__file__).with_name("playground.html")
_busy = threading.Lock()


def _push_step(lane: str, step: dict[str, Any]) -> None:
    stage.push({
        "type": "step", "lane": lane, "mode": step.get("mode", "cold"),
        "kind": step["kind"], "name": step["name"],
        "tokens": int(step.get("input_tokens", 0)) + int(step.get("output_tokens", 0)),
        "cost_usd": float(step.get("cost_usd", 0.0)), "wall_ms": step.get("wall_ms", 0),
    })


def _stream_recorder(lane: str, rec: Any, done: threading.Event) -> None:
    """Poll a live RunRecorder and push each new step as it lands."""
    seen = 0
    while not done.is_set():
        steps = list(rec.steps)
        for step in steps[seen:]:
            _push_step(lane, step.to_dict())
        seen = len(steps)
        done.wait(0.4)
    for step in list(rec.steps)[seen:]:
        _push_step(lane, step.to_dict())


def _run_lane_cold(lane: str, prompt: str, base_url: str, out: dict[str, Any]) -> None:
    from amort.demo.tasks import ticket_triage as task
    from amort.skills.recorder import RunRecorder

    s = get_settings()
    rec = RunRecorder(
        lane=lane, mode="cold", system=task.SYSTEM, user_msg=prompt,
        tool_names=task.TOOL_NAMES, model=s.novita_model,
    )
    done = threading.Event()
    tail = threading.Thread(target=_stream_recorder, args=(lane, rec, done), daemon=True)
    tail.start()
    try:
        report, rec = task.run_live(
            lane=lane, mode="cold", model=s.novita_model,
            base_url=base_url, api_key=s.novita_api_key,
            user_msg=prompt, recorder=rec,
        )
        out["report"], out["rec"] = report, rec
    except Exception as exc:  # noqa: BLE001 — a dead upstream must not kill the server
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        done.set()
        tail.join(timeout=2)


def _try_warm(prompt: str, out: dict[str, Any]) -> bool:
    """Layer 2: replay a verified skill if memory recognises this task."""
    from amort.demo.tasks import ticket_triage as task
    from amort.skills.replayer import replay
    from amort.skills.store_everos import fingerprint, fingerprint_query, search_skill

    s = get_settings()
    fp = fingerprint(task.SYSTEM, prompt, task.TOOL_NAMES)
    match = search_skill(fp, fingerprint_query(task.SYSTEM, prompt, task.TOOL_NAMES))
    if not match or not match.is_confident or match.skill.status != "verified":
        return False
    stage.push({
        "type": "memory", "op": "hit", "node": str(match.skill_id),
        "label": "skill recalled — replaying as code", "backend": "everos",
    })
    outcome = replay(match.skill, {
        "user_msg": prompt, "tool_executor": task.execute_tool,
        "model": s.novita_model,
        "base_url": f"{s.novita_api_url.rstrip('/')}/v1", "api_key": s.novita_api_key,
    })
    if not outcome.took_warm_path:
        stage.push({
            "type": "memory", "op": "add", "node": f"fallback_{int(time.time())}",
            "label": f"guard fallback: {outcome.fallback}", "backend": "everos",
        })
        return False
    tokens = cost = 0.0
    for step in outcome.steps:
        _push_step("amortize", {**step, "mode": "warm"})
        tokens += step.get("input_tokens", 0) + step.get("output_tokens", 0)
        cost += step.get("cost_usd", 0.0)
    out.update(report=outcome.output, warm=True, tokens=int(tokens), cost=cost,
               wall_ms=outcome.wall_ms, llm_calls=outcome.llm_calls,
               tool_calls=outcome.tool_calls, skill_id=match.skill_id)
    return True


def _maybe_compile(case_a: dict[str, Any], case_b: dict[str, Any]) -> None:
    from amort.skills.compiler import compile_skill

    try:
        skill = compile_skill([case_a, case_b])
    except Exception as exc:  # noqa: BLE001
        logger.warning("compile failed: %s", exc)
        return
    if skill is not None:
        stage.push({
            "type": "memory", "op": "skill", "node": str(skill.skill_id),
            "label": f"skill distilled · {skill.status} — repeat this prompt",
            "backend": "everos",
        })


def _record(case: dict[str, Any], label: str) -> None:
    from amort.ledger.events import RunRecord, emit_run, flush
    from amort.skills.store_everos import record_case

    emit_run(RunRecord.from_case(case))
    flush()
    try:
        case_id = record_case(case)
        stage.push({"type": "memory", "op": "add", "node": str(case_id),
                    "label": label, "backend": "everos"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_case failed: %s", exc)


def run_prompt(prompt: str) -> None:
    """The fan-out: both lanes live, then grade, record, and maybe distil."""
    from amort.skills.grader import grade

    s = get_settings()
    novita = f"{s.novita_api_url.rstrip('/')}/v1"
    proxy = f"{s.proxy_base_url}/v1"

    stage.push({"type": "prompt", "text": prompt[:300]})
    a: dict[str, Any] = {}
    b: dict[str, Any] = {}

    stage.push({"type": "run_start", "lane": "baseline", "mode": "cold",
                "task": "ticket_triage", "model": s.novita_model, "simulated": False})
    ta = threading.Thread(target=_run_lane_cold, args=("baseline", prompt, novita, a))
    ta.start()

    warm = _try_warm(prompt, b)
    if warm:
        stage.push({"type": "run_start", "lane": "amortize", "mode": "warm",
                    "task": "ticket_triage", "model": s.novita_model, "simulated": False})
    else:
        stage.push({"type": "run_start", "lane": "amortize", "mode": "cold",
                    "task": "ticket_triage", "model": s.novita_model, "simulated": False})
        tb = threading.Thread(target=_run_lane_cold, args=("amortize", prompt, proxy, b))
        tb.start()
        tb.join()
    ta.join()

    # totals per lane — copied from the recorders, never computed here
    if "rec" in a:
        rec = a["rec"]
        a.update(tokens=rec.input_tokens + rec.output_tokens, cost=rec.cost_usd,
                 wall_ms=rec.wall_ms, llm_calls=rec.llm_calls, tool_calls=rec.tool_calls)
    if "rec" in b:
        rec = b["rec"]
        b.update(tokens=rec.input_tokens + rec.output_tokens, cost=rec.cost_usd,
                 wall_ms=rec.wall_ms, llm_calls=rec.llm_calls, tool_calls=rec.tool_calls)

    for lane, side, mode in (("baseline", a, "cold"), ("amortize", b, "warm" if warm else "cold")):
        stage.push({
            "type": "run_end", "lane": lane, "mode": mode,
            "tokens": side.get("tokens"), "cost_usd": side.get("cost"),
            "wall_ms": side.get("wall_ms"), "llm_calls": side.get("llm_calls"),
            "tool_calls": side.get("tool_calls"),
            "ok": "error" not in side, "simulated": False,
            "error": side.get("error"),
        })

    parity = grade(a.get("report"), b.get("report"))
    stage.push({"type": "parity", "key": "left_vs_right", "verdict": parity.verdict,
                "symbol": parity.symbol, "compared": parity.compared})

    if a.get("tokens") and b.get("tokens"):
        stage.push({
            "type": "delta", "mode": "warm" if warm else "cold",
            "tokens_pct": round((b["tokens"] - a["tokens"]) / a["tokens"] * 100, 1),
            "cost_pct": round((b["cost"] - a["cost"]) / a["cost"] * 100, 1) if a.get("cost") else None,
            "left_wall_ms": a.get("wall_ms"), "right_wall_ms": b.get("wall_ms"),
            "left_cost": a.get("cost"), "right_cost": b.get("cost"),
            "parity": parity.verdict, "compared": parity.compared,
        })

    if "rec" in a:
        _record(a["rec"].to_case(), "case · direct")
    if not warm and "rec" in b:
        case_b = b["rec"].to_case()
        _record(case_b, "case · amortize")
        if parity.ok and "rec" in a:
            _maybe_compile(a["rec"].to_case(), case_b)


def create_app() -> Any:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

    stage.enable()  # once — history persists so the memory graph grows per prompt
    app = FastAPI(title="amortize playground")

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))

    @app.get("/stage")
    def stage_page() -> HTMLResponse:
        return HTMLResponse((Path(__file__).with_name("stage.html")).read_text(encoding="utf-8"))

    @app.get("/events")
    def events() -> StreamingResponse:
        return StreamingResponse(stage._sse(), media_type="text/event-stream",  # noqa: SLF001
                                 headers={"Cache-Control": "no-cache"})

    @app.post("/run")
    async def run(payload: dict[str, Any]) -> JSONResponse:
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            return JSONResponse({"ok": False, "error": "empty prompt"}, status_code=400)
        if not _busy.acquire(blocking=False):
            return JSONResponse({"ok": False, "error": "a run is in flight"}, status_code=409)

        def _go() -> None:
            try:
                run_prompt(prompt)
            except Exception:  # noqa: BLE001
                logger.exception("run_prompt failed")
            finally:
                _busy.release()

        threading.Thread(target=_go, daemon=True).start()
        return JSONResponse({"ok": True})

    return app


def serve(port: int = stage.DEFAULT_PORT) -> None:
    """Foreground server for `amort playground`."""
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


__all__ = ["create_app", "run_prompt", "serve"]
