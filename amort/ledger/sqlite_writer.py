"""Local SQLite ledger — same schema as Snowflake, no credentials required.

This is the fallback *and* the default developer experience. The column names and
order mirror `scripts/snowflake_setup.sql` exactly so the dashboard runs one set
of queries against either backend, and so a local run can be replayed into
Snowflake later without a translation step.

Two deliberate divergences from the Snowflake DDL, both forced by SQLite:
`TIMESTAMP_NTZ` becomes `TEXT` (ISO-8601, UTC) and `VARIANT` becomes `TEXT`
holding JSON. `SAVINGS` is a view with the same column names, rewritten from
`IFF(...)` to `CASE WHEN ...`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from amort.config import Settings, get_settings
from amort.ledger.events import RunRecord, SkillRecord, StepEvent

logger = logging.getLogger("amort.ledger.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS RUNS (
  RUN_ID TEXT, TASK_FINGERPRINT TEXT, LANE TEXT, MODE TEXT,
  MODEL TEXT, STARTED_AT TEXT, ENDED_AT TEXT,
  WALL_MS INTEGER, LLM_CALLS INTEGER, TOOL_CALLS INTEGER,
  INPUT_TOKENS INTEGER, OUTPUT_TOKENS INTEGER, COST_USD REAL,
  SKILL_ID TEXT, PARITY TEXT, OUTPUT_HASH TEXT
);

CREATE TABLE IF NOT EXISTS STEPS (
  RUN_ID TEXT, STEP_IDX INTEGER, KIND TEXT, NAME TEXT, MODEL TEXT,
  INPUT_TOKENS INTEGER, OUTPUT_TOKENS INTEGER, COST_USD REAL,
  WALL_MS INTEGER, TS TEXT, META TEXT
);

CREATE TABLE IF NOT EXISTS SKILLS (
  SKILL_ID TEXT, TASK_FINGERPRINT TEXT, STATUS TEXT,
  CREATED_AT TEXT, RUNS_OBSERVED INTEGER, PARITY_RATE REAL,
  AVG_COLD_COST REAL, AVG_WARM_COST REAL, TOTAL_SAVED_USD REAL, MD_PATH TEXT
);

CREATE INDEX IF NOT EXISTS IDX_STEPS_RUN ON STEPS(RUN_ID);
CREATE INDEX IF NOT EXISTS IDX_RUNS_FP ON RUNS(TASK_FINGERPRINT);

CREATE VIEW IF NOT EXISTS SAVINGS AS
SELECT TASK_FINGERPRINT,
       AVG(CASE WHEN LANE='baseline' THEN COST_USD END)                        AS AVG_BASELINE_COST,
       AVG(CASE WHEN LANE='amortize' AND MODE='cold' THEN COST_USD END)        AS AVG_LIGHTENED_COST,
       AVG(CASE WHEN LANE='amortize' AND MODE='warm' THEN COST_USD END)        AS AVG_WARM_COST,
       SUM(CASE WHEN LANE='baseline' THEN COST_USD ELSE -COST_USD END)         AS NET_SAVED_USD,
       COUNT(*) AS TOTAL_RUNS
FROM RUNS GROUP BY TASK_FINGERPRINT;
"""

_RUN_COLS = (
    "RUN_ID, TASK_FINGERPRINT, LANE, MODE, MODEL, STARTED_AT, ENDED_AT, WALL_MS, "
    "LLM_CALLS, TOOL_CALLS, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, SKILL_ID, PARITY, OUTPUT_HASH"
)
_STEP_COLS = (
    "RUN_ID, STEP_IDX, KIND, NAME, MODEL, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, WALL_MS, TS, META"
)
_SKILL_COLS = (
    "SKILL_ID, TASK_FINGERPRINT, STATUS, CREATED_AT, RUNS_OBSERVED, PARITY_RATE, "
    "AVG_COLD_COST, AVG_WARM_COST, TOTAL_SAVED_USD, MD_PATH"
)


class SqliteWriter:
    """Thread-safe SQLite ledger. Writes are immediate — no batching needed."""

    name = "sqlite"

    def __init__(self, settings: Settings | None = None, path: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = path or self.settings.db_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False + an explicit lock: uvicorn serves from a
        # threadpool, and one connection guarded by a lock beats a connection
        # pool for a write volume measured in events per second.
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        logger.debug("sqlite ledger at %s", self.path)

    def write_step(self, event: StepEvent) -> None:
        row = (
            event.run_id,
            event.step_idx,
            event.kind,
            event.name,
            event.model,
            event.input_tokens,
            event.output_tokens,
            event.cost_usd,
            event.wall_ms,
            event.ts,
            json.dumps({**event.meta, "lane": event.lane, "mode": event.mode,
                        "task_fingerprint": event.task_fingerprint}, default=str),
        )
        self._insert(f"INSERT INTO STEPS ({_STEP_COLS}) VALUES ({_qs(11)})", row)

    def write_run(self, run: RunRecord) -> None:
        row = (
            run.run_id, run.task_fingerprint, run.lane, run.mode, run.model,
            run.started_at, run.ended_at, run.wall_ms, run.llm_calls, run.tool_calls,
            run.input_tokens, run.output_tokens, run.cost_usd,
            run.skill_id, run.parity, run.output_hash,
        )
        self._insert(f"INSERT INTO RUNS ({_RUN_COLS}) VALUES ({_qs(16)})", row)

    def write_skill(self, skill: SkillRecord) -> None:
        row = (
            skill.skill_id, skill.task_fingerprint, skill.status, skill.created_at,
            skill.runs_observed, skill.parity_rate, skill.avg_cold_cost,
            skill.avg_warm_cost, skill.total_saved_usd, skill.md_path,
        )
        self._insert(f"INSERT INTO SKILLS ({_SKILL_COLS}) VALUES ({_qs(10)})", row)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    def flush(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()

    def _insert(self, sql: str, row: tuple[Any, ...]) -> None:
        with self._lock:
            self._conn.execute(sql, row)
            self._conn.commit()


def _qs(n: int) -> str:
    return ", ".join("?" * n)


__all__ = ["SCHEMA", "SqliteWriter"]
