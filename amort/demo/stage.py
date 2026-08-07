"""Stage view — the projector page behind `amort demo --stage`.

A tiny FastAPI app served from a background thread of the demo process. The
harness pushes plain dicts (`{"type": "run_start"|"step"|"run_end"|"parity"|
"final", ...}`) via `push()`; every connected browser receives the full history
and then live events over SSE (`/events`), so a mid-demo refresh does not blank
the projector.

Honesty rules, same as everywhere else in Amortize:

* every number an event carries is a measured (or explicitly `simulated`) value
  copied from the recorder / report — nothing here computes or invents one;
* replay mode (`amort demo --replay demo_report.json`) synthesizes the same
  event sequence from a recorded report. The report stores per-run totals, not
  per-step token splits, so replayed `step` events carry **no token numbers** —
  only the measured llm/tool call counts pace the animation.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

DEFAULT_PORT = 4700
_HTML_PATH = Path(__file__).with_name("stage.html")

_cond = threading.Condition()
_events: list[dict[str, Any]] = []
_enabled = False


def enable() -> None:
    """Start capturing events. Clears any previous run's history."""
    global _enabled
    with _cond:
        _events.clear()
        _enabled = True


def push(event: dict[str, Any]) -> None:
    """Record one stage event. No-op unless the stage is enabled, so the
    harness can call this unconditionally."""
    if not _enabled:
        return
    with _cond:
        _events.append({**event, "ts": time.time()})
        _cond.notify_all()


def events_snapshot() -> list[dict[str, Any]]:
    """Everything pushed so far (tests, and the SSE history replay)."""
    with _cond:
        return list(_events)


# ─────────────────────────────────────────────────────────────────────────────
# The web app
# ─────────────────────────────────────────────────────────────────────────────


def _sse() -> Iterator[str]:
    """One generator per client: replay history, then stream new events."""
    idx = 0
    while True:
        with _cond:
            _cond.wait_for(lambda i=idx: len(_events) > i, timeout=15.0)
            batch = _events[idx:]
        if not batch:
            yield ": keepalive\n\n"
            continue
        for event in batch:
            yield f"data: {json.dumps(event, default=str)}\n\n"
        idx += len(batch)


def create_app() -> Any:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, StreamingResponse

    app = FastAPI(title="amortize stage")

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))

    @app.get("/events")
    def events() -> StreamingResponse:
        return StreamingResponse(
            _sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return app


def start_stage(port: int = DEFAULT_PORT) -> str:
    """Serve the stage in a daemon thread; returns the URL once it is up."""
    import uvicorn

    enable()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=server.run, name="amort-stage", daemon=True).start()
    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}"


# ─────────────────────────────────────────────────────────────────────────────
# Replay — the offline fallback for a dead network
# ─────────────────────────────────────────────────────────────────────────────


def synthesize_events(report: dict[str, Any]) -> list[tuple[float, dict[str, Any]]]:
    """A recorded `demo_report.json` → the same (delay_s, event) sequence the
    live harness pushes, paced from each run's measured wall time (compressed
    to keep the whole replay under ~30 s)."""
    out: list[tuple[float, dict[str, Any]]] = []
    model = str(report.get("model") or "")
    task = str(report.get("task") or "")
    simulated = bool(report.get("simulated", False))

    for cell, run in (report.get("runs") or {}).items():
        base = {"cell": cell, "lane": run.get("lane"), "mode": run.get("mode")}
        run_simulated = bool(run.get("simulated", simulated))
        out.append((0.4, {
            "type": "run_start", **base, "task": task, "model": model,
            "simulated": run_simulated, "replayed": True,
        }))
        llm = int(run.get("llm_calls") or 0)
        tool = int(run.get("tool_calls") or 0)
        kinds: list[str] = []
        for i in range(max(llm, tool)):
            if i < llm:
                kinds.append("llm")
            if i < tool:
                kinds.append("tool")
        display_s = min(max(float(run.get("wall_ms") or 0) / 1000.0, 1.2), 6.0)
        gap = display_s / max(1, len(kinds))
        for kind in kinds:
            # No token numbers here: the report records run totals only, and a
            # per-step split would be a fabricated number.
            out.append((gap, {
                "type": "step", **base, "kind": kind,
                "name": model if kind == "llm" else "tool", "replayed": True,
            }))
        out.append((0.2, {
            "type": "run_end", **base,
            "tokens": run.get("total_tokens"), "cost_usd": run.get("cost_usd"),
            "wall_ms": run.get("wall_ms"), "llm_calls": llm, "tool_calls": tool,
            "ok": bool(run.get("ok", True)), "simulated": run_simulated,
            "replayed": True,
        }))

    parity = report.get("parity") or {}
    for key, entry in parity.items():
        verdict = str(entry.get("verdict") or "n/a")
        out.append((0.6, {
            "type": "parity", "key": key, "verdict": verdict,
            "symbol": {"match": "✓", "mismatch": "✗"}.get(verdict, "n/a"),
            "replayed": True,
        }))

    warm_parity = parity.get("B_cold_vs_B_warm") or {}
    out.append((0.8, {
        "type": "final", "deltas": report.get("deltas") or {},
        "parity": str(warm_parity.get("verdict") or "n/a"),
        "simulated": simulated, "replayed": True,
    }))
    return out


def replay_report(path: str | Path, *, realtime: bool = True) -> int:
    """Push a recorded report's event sequence. Returns the event count."""
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    seq = synthesize_events(report)
    for delay, event in seq:
        if realtime and delay:
            time.sleep(delay)
        push(event)
    return len(seq)


__all__ = [
    "DEFAULT_PORT",
    "create_app",
    "enable",
    "events_snapshot",
    "push",
    "replay_report",
    "start_stage",
    "synthesize_events",
]
