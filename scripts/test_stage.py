"""Stage-view checks (assert-based, no pytest).

1. Replay-mode event synthesis produces a well-formed sequence from a report.
2. The harness pushes stage events during an offline demo run.

    AMORT_LEDGER=sqlite uv run python scripts/test_stage.py
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("AMORT_LEDGER", "sqlite")

from amort.demo import stage  # noqa: E402

SAMPLE_REPORT = {
    "task": "ticket_triage",
    "model": "test-model",
    "simulated": True,
    "runs": {
        "A_cold": {"lane": "baseline", "mode": "cold", "total_tokens": 100, "cost_usd": 0.01,
                   "wall_ms": 1500, "llm_calls": 5, "tool_calls": 4, "ok": True, "simulated": True},
        "B_cold": {"lane": "amortize", "mode": "cold", "total_tokens": 100, "cost_usd": 0.01,
                   "wall_ms": 1400, "llm_calls": 5, "tool_calls": 4, "ok": True, "simulated": True},
        "B_warm": {"lane": "amortize", "mode": "warm", "total_tokens": 10, "cost_usd": 0.001,
                   "wall_ms": 300, "llm_calls": 2, "tool_calls": 4, "ok": True, "simulated": True},
    },
    "parity": {"B_cold_vs_B_warm": {"verdict": "match"}},
    "deltas": {"warm_tokens_pct": -90.0, "cold_tokens_pct": 0.0},
}


def check_synthesis() -> None:
    seq = stage.synthesize_events(SAMPLE_REPORT)
    events = [e for _, e in seq]
    assert all(isinstance(d, (int, float)) and d >= 0 for d, _ in seq), "negative delay"
    assert all("type" in e for e in events), "event without a type"

    for cell, run in SAMPLE_REPORT["runs"].items():
        cell_events = [e for e in events if e.get("cell") == cell]
        types = [e["type"] for e in cell_events]
        assert types[0] == "run_start", f"{cell}: first event {types[0]}"
        assert types[-1] == "run_end", f"{cell}: last event {types[-1]}"
        assert types.count("run_start") == 1 and types.count("run_end") == 1, cell
        steps = [e for e in cell_events if e["type"] == "step"]
        assert len(steps) == run["llm_calls"] + run["tool_calls"], f"{cell}: step count"
        # no fabricated numbers: replayed steps must not carry token counts
        assert all("tokens" not in s for s in steps), f"{cell}: replayed step has tokens"
        end = cell_events[-1]
        assert end["tokens"] == run["total_tokens"], f"{cell}: run_end tokens"
        assert end["simulated"] is True, f"{cell}: lost the simulated label"

    types = [e["type"] for e in events]
    assert types.count("final") == 1 and types[-1] == "final", "final must close the sequence"
    last_run_end = max(i for i, t in enumerate(types) if t == "run_end")
    first_parity = types.index("parity")
    assert first_parity > last_run_end, "parity must come after all runs"
    final = events[-1]
    assert final["deltas"]["warm_tokens_pct"] == -90.0
    assert final["parity"] == "match"
    print(f"synthesis: {len(events)} events well-formed")


def check_harness_pushes() -> None:
    from amort.demo.harness import run_demo

    stage.enable()
    run_demo(task="ticket_triage", live=False, write_report=False)
    events = stage.events_snapshot()
    types = [e["type"] for e in events]
    assert types.count("run_start") == 4, f"expected 4 run_start, got {types.count('run_start')}"
    assert types.count("run_end") == 4, f"expected 4 run_end, got {types.count('run_end')}"
    assert "step" in types, "no step events pushed"
    assert "parity" in types, "no parity events pushed"
    assert types[-1] == "final", f"last event {types[-1]}, expected final"
    for e in events:
        if e["type"] in ("run_start", "run_end"):
            assert e.get("simulated") is True, "offline run lost the simulated label"
    steps = [e for e in events if e["type"] == "step"]
    assert all(isinstance(s.get("tokens"), int) for s in steps if s["kind"] == "llm"), \
        "live-harness llm steps must carry measured token counts"
    print(f"harness: {len(events)} events pushed in offline mode")


def main() -> int:
    check_synthesis()
    check_harness_pushes()
    print("\nSTAGE TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
