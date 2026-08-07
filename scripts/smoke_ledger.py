"""Phase 5 smoke: insert 1 synthetic RUN + 3 STEPS, then SELECT COUNT(*) them back.

Reports which backend actually served the write — the point of the exercise is
knowing whether the numbers are in Snowflake or in SQLite, not asserting one.

    uv run python scripts/smoke_ledger.py
"""

from __future__ import annotations

import sys
import uuid

from amort.config import get_settings
from amort.ledger import events as ledger
from amort.ledger.events import RunRecord, StepEvent, active_backend, emit, emit_run
from amort.ledger.pricing import cost_usd, known_models, pricing_note, rate_for

MODEL = "claude-haiku-4-5-20251001"


def main() -> int:
    settings = get_settings()
    settings.ensure_dirs()

    # --- pricing -----------------------------------------------------------
    r = rate_for(MODEL)
    print(f"pricing table   : {', '.join(known_models())}")
    print(f"resolved {MODEL} -> {r.model}  ${r.input}/${r.output} per Mtok "
          f"(cache read ${r.cache_read:.2f}, write ${r.cache_write_5m:.2f})")
    assert r.known, "dated snapshot did not resolve to its base model"
    assert cost_usd(MODEL, 1_000_000, 0) == 1.0, "input cost math is wrong"
    assert cost_usd(MODEL, 0, 1_000_000) == 5.0, "output cost math is wrong"
    assert cost_usd("totally-made-up-model", 1_000_000, 1_000_000) == 0.0, (
        "an unknown model must cost 0.0, never a guessed rate"
    )
    print("pricing math    : input/output/unknown-model cases OK")

    # --- write -------------------------------------------------------------
    backend = active_backend()
    print(f"\nledger backend  : {backend}")
    print(f"ledger location : "
          f"{settings.db_path if backend == 'sqlite' else settings.snowflake_database}")

    run_id = f"run_smoke_{uuid.uuid4().hex[:8]}"
    fp = "fp_smoke_ledger"

    steps = [
        StepEvent.for_llm(
            run_id=run_id, model=MODEL, input_tokens=12_400, output_tokens=880,
            wall_ms=3100, lane="baseline", mode="cold", task_fingerprint=fp, step_idx=0,
        ),
        StepEvent(
            run_id=run_id, kind="tool", name="fetch_tickets", wall_ms=12,
            lane="baseline", mode="cold", task_fingerprint=fp, step_idx=1,
            meta={"args": {"range": "last_7_days"}},
        ),
        StepEvent.for_llm(
            run_id=run_id, model=MODEL, input_tokens=9_100, output_tokens=1_240,
            cache_read_tokens=8_000, wall_ms=2600, lane="baseline", mode="cold",
            task_fingerprint=fp, step_idx=2,
        ),
    ]
    for step in steps:
        emit(step)

    total_cost = round(sum(s.cost_usd for s in steps), 6)
    emit_run(
        RunRecord(
            run_id=run_id, task_fingerprint=fp, lane="baseline", mode="cold", model=MODEL,
            wall_ms=5712, llm_calls=2, tool_calls=1,
            input_tokens=21_500, output_tokens=2_120, cost_usd=total_cost,
            output_hash="smoke0000",
        )
    )
    ledger.flush()
    print(f"wrote           : 1 RUN + {len(steps)} STEPS  (cost ${total_cost:.4f})")

    # --- read back ---------------------------------------------------------
    writer = ledger.get_writer()
    runs = writer.query("SELECT COUNT(*) FROM RUNS WHERE RUN_ID = ?"
                        if writer.name == "sqlite"
                        else "SELECT COUNT(*) FROM RUNS WHERE RUN_ID = %s", (run_id,))
    step_rows = writer.query("SELECT COUNT(*) FROM STEPS WHERE RUN_ID = ?"
                             if writer.name == "sqlite"
                             else "SELECT COUNT(*) FROM STEPS WHERE RUN_ID = %s", (run_id,))
    n_runs, n_steps = runs[0][0], step_rows[0][0]
    print(f"SELECT COUNT(*) : RUNS={n_runs}  STEPS={n_steps}")
    assert n_runs == 1, f"expected 1 RUN row, got {n_runs}"
    assert n_steps == 3, f"expected 3 STEP rows, got {n_steps}"

    savings = writer.query(
        "SELECT TASK_FINGERPRINT, AVG_BASELINE_COST, TOTAL_RUNS FROM SAVINGS "
        + ("WHERE TASK_FINGERPRINT = ?" if writer.name == "sqlite" else "WHERE TASK_FINGERPRINT = %s"),
        (fp,),
    )
    print(f"SAVINGS view    : {savings}")
    assert savings, "SAVINGS view returned no row for the synthetic fingerprint"

    print(f"\nBACKEND USED    : {writer.name.upper()}")
    print(f"NOTE            : {pricing_note()}")
    print("\nPHASE 5 SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
