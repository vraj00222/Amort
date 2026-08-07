"""Snowflake ledger writer — batched, retried, and degradable.

Load-bearing invariants:

* **Batched**: steps buffer and flush every 20 events or 2 seconds, whichever
  comes first. One INSERT per step would put a network round-trip inside the
  proxy's hot path; the buffer keeps `emit()` at memory speed.
* **Degradable**: after retries are exhausted the writer logs *once*, flips to a
  `SqliteWriter`, and replays the pending buffer into it. A booth wifi drop
  costs you the Snowflake rows, not the demo. `name` follows the switch, so the
  report says `sqlite` when that is where the numbers went.
* **VARIANT via `PARSE_JSON`**: `META` is a VARIANT column and cannot be bound
  directly, so the insert is `INSERT ... SELECT ..., PARSE_JSON(%s)` rather than
  `INSERT ... VALUES`.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import TYPE_CHECKING, Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from amort.config import Settings, get_settings
from amort.ledger.events import RunRecord, SkillRecord, StepEvent

if TYPE_CHECKING:
    from amort.ledger.sqlite_writer import SqliteWriter

logger = logging.getLogger("amort.ledger.snowflake")

BATCH_SIZE = 20
FLUSH_INTERVAL_S = 2.0

# `CREATE DATABASE|SCHEMA IF NOT EXISTS <name>` — the two statements in the DDL a
# ledger-scoped role may not be allowed to run. See `ensure_schema`.
_CREATE_CONTAINER = re.compile(
    r'^\s*CREATE\s+(DATABASE|SCHEMA)\s+IF\s+NOT\s+EXISTS\s+([\w."]+)', re.IGNORECASE
)

_RUN_INSERT = """
INSERT INTO RUNS (RUN_ID, TASK_FINGERPRINT, LANE, MODE, MODEL, STARTED_AT, ENDED_AT,
                  WALL_MS, LLM_CALLS, TOOL_CALLS, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD,
                  SKILL_ID, PARITY, OUTPUT_HASH)
VALUES (%s, %s, %s, %s, %s, TO_TIMESTAMP_NTZ(%s), TO_TIMESTAMP_NTZ(%s),
        %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# VARIANT can't be bound in a VALUES clause — SELECT + PARSE_JSON is the sanctioned form.
_STEP_INSERT = """
INSERT INTO STEPS (RUN_ID, STEP_IDX, KIND, NAME, MODEL, INPUT_TOKENS, OUTPUT_TOKENS,
                   COST_USD, WALL_MS, TS, META)
SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, TO_TIMESTAMP_NTZ(%s), PARSE_JSON(%s)
"""

_STEP_COLUMNS = 11


def _step_batch_sql(n_rows: int) -> str:
    """N-row version of `_STEP_INSERT`.

    `executemany` rewrites `INSERT … VALUES` into one multi-row statement, but it
    cannot rewrite the `INSERT … SELECT` form that `PARSE_JSON` forces — it fails
    with `252001: Failed to rewrite multi-row insert`. Rather than fall back to a
    round-trip per step, spell the multi-row insert out: `SELECT … FROM VALUES
    (…), (…)` keeps one statement per flush *and* keeps PARSE_JSON.
    """
    row = "(" + ", ".join(["%s"] * _STEP_COLUMNS) + ")"
    return (
        "INSERT INTO STEPS (RUN_ID, STEP_IDX, KIND, NAME, MODEL, INPUT_TOKENS, "
        "OUTPUT_TOKENS, COST_USD, WALL_MS, TS, META) "
        "SELECT column1, column2, column3, column4, column5, column6, column7, "
        "column8, column9, TO_TIMESTAMP_NTZ(column10), PARSE_JSON(column11) "
        "FROM VALUES " + ", ".join([row] * n_rows)
    )

_SKILL_INSERT = """
INSERT INTO SKILLS (SKILL_ID, TASK_FINGERPRINT, STATUS, CREATED_AT, RUNS_OBSERVED,
                    PARITY_RATE, AVG_COLD_COST, AVG_WARM_COST, TOTAL_SAVED_USD, MD_PATH)
VALUES (%s, %s, %s, TO_TIMESTAMP_NTZ(%s), %s, %s, %s, %s, %s, %s)
"""


class SnowflakeWriter:
    """Buffered writer for `AMORTIZE.LEDGER`, degrading to SQLite on failure."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.name = "snowflake"
        self._conn: Any = None
        self._lock = threading.RLock()
        self._buffer: list[tuple[str, tuple[Any, ...]]] = []
        self._fallback: SqliteWriter | None = None
        self._warned = False
        self._timer: threading.Timer | None = None

    # -- connection ----------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def connect(self) -> Any:
        """Open (or reuse) the connection. Retried; raises if all attempts fail."""
        if self._conn is not None:
            return self._conn
        import snowflake.connector  # imported lazily: heavy, and optional at runtime

        kwargs = self.settings.snowflake_connect_kwargs()
        logger.debug("connecting to snowflake account=%s", kwargs.get("account"))
        self._conn = snowflake.connector.connect(
            **kwargs, client_session_keep_alive=True, login_timeout=15, network_timeout=20
        )
        return self._conn

    def ensure_schema(self, sql_path: str | None = None) -> tuple[list[str], list[str]]:
        """Execute `scripts/snowflake_setup.sql`. Returns `(applied, skipped)`.

        Writing ledger rows needs table rights inside one schema; it does not need
        the right to *create* databases. Snowflake checks CREATE DATABASE /
        CREATE SCHEMA before it honours `IF NOT EXISTS`, so a least-privileged
        role fails on those two lines even when the objects are already there.
        Skip a container statement only after confirming the object exists —
        every other failure still raises.
        """
        from pathlib import Path

        from amort.config import project_root

        path = Path(sql_path) if sql_path else project_root() / "scripts" / "snowflake_setup.sql"
        statements = [s.strip() for s in path.read_text(encoding="utf-8").split(";") if s.strip()]
        conn = self.connect()
        cur = conn.cursor()
        applied: list[str] = []
        skipped: list[str] = []
        try:
            for stmt in statements:
                try:
                    cur.execute(stmt)
                    applied.append(stmt)
                except Exception:
                    container = _CREATE_CONTAINER.match(stmt)
                    if container and self._container_exists(cur, *container.groups()):
                        logger.info("ensure_schema.skipped_existing: %s", container.group(2))
                        skipped.append(stmt)
                        continue
                    raise
        finally:
            cur.close()
        return applied, skipped

    @staticmethod
    def _container_exists(cur: Any, kind: str, name: str) -> bool:
        """True when the DATABASE / SCHEMA in a CREATE statement already exists."""
        parts = name.replace('"', "").split(".")
        scope = f" IN DATABASE {parts[0]}" if kind.upper() == "SCHEMA" and len(parts) > 1 else ""
        cur.execute(f"SHOW {kind.upper()}S LIKE '{parts[-1]}'{scope}")
        return bool(cur.fetchall())

    # -- writes --------------------------------------------------------------

    def write_step(self, event: StepEvent) -> None:
        meta = json.dumps(
            {
                **event.meta,
                "lane": event.lane,
                "mode": event.mode,
                "task_fingerprint": event.task_fingerprint,
            },
            default=str,
        )
        self._enqueue(
            _STEP_INSERT,
            (
                event.run_id, event.step_idx, event.kind, event.name, event.model,
                event.input_tokens, event.output_tokens, event.cost_usd, event.wall_ms,
                _ts(event.ts), meta,
            ),
            fallback=lambda w: w.write_step(event),
        )

    def write_run(self, run: RunRecord) -> None:
        self._enqueue(
            _RUN_INSERT,
            (
                run.run_id, run.task_fingerprint, run.lane, run.mode, run.model,
                _ts(run.started_at), _ts(run.ended_at), run.wall_ms, run.llm_calls,
                run.tool_calls, run.input_tokens, run.output_tokens, run.cost_usd,
                run.skill_id, run.parity, run.output_hash,
            ),
            fallback=lambda w: w.write_run(run),
        )

    def write_skill(self, skill: SkillRecord) -> None:
        self._enqueue(
            _SKILL_INSERT,
            (
                skill.skill_id, skill.task_fingerprint, skill.status, _ts(skill.created_at),
                skill.runs_observed, skill.parity_rate, skill.avg_cold_cost,
                skill.avg_warm_cost, skill.total_saved_usd, skill.md_path,
            ),
            fallback=lambda w: w.write_skill(skill),
        )

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        if self._fallback is not None:
            return self._fallback.query(sql, params)
        self.flush()
        cur = self.connect().cursor()
        try:
            cur.execute(sql, params or None)
            return list(cur.fetchall())
        finally:
            cur.close()

    # -- buffering -----------------------------------------------------------

    def _enqueue(self, sql: str, row: tuple[Any, ...], *, fallback: Any) -> None:
        if self._fallback is not None:
            fallback(self._fallback)
            return
        with self._lock:
            self._buffer.append((sql, row))
            if len(self._buffer) >= BATCH_SIZE:
                self._flush_locked()
            else:
                self._arm_timer()

    def _arm_timer(self) -> None:
        if self._timer is not None:
            return
        self._timer = threading.Timer(FLUSH_INTERVAL_S, self.flush)
        self._timer.daemon = True
        self._timer.start()

    def _disarm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        self._disarm_timer()
        if not self._buffer:
            return
        pending, self._buffer = self._buffer, []
        try:
            self._execute_batch(pending)
        except Exception as exc:  # noqa: BLE001 — degrade rather than lose the demo
            self._degrade(exc, pending)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _execute_batch(self, pending: list[tuple[str, tuple[Any, ...]]]) -> None:
        conn = self.connect()
        cur = conn.cursor()
        try:
            # Group consecutive identical statements so executemany can batch them.
            i = 0
            while i < len(pending):
                sql = pending[i][0]
                rows = []
                while i < len(pending) and pending[i][0] == sql:
                    rows.append(pending[i][1])
                    i += 1
                if len(rows) == 1:
                    cur.execute(sql, rows[0])
                elif sql == _STEP_INSERT:
                    # executemany can't rewrite this one; see _step_batch_sql.
                    flat = [v for row in rows for v in row]
                    cur.execute(_step_batch_sql(len(rows)), flat)
                else:
                    cur.executemany(sql, rows)
            conn.commit()
        finally:
            cur.close()

    def _degrade(self, exc: Exception, pending: list[tuple[str, tuple[Any, ...]]]) -> None:
        """Switch to SQLite once, and replay what was in flight so nothing is lost."""
        if not self._warned:
            logger.warning(
                "Snowflake write failed (%s: %s) — switching this process to the local "
                "SQLite ledger at %s. Re-run `amort snowflake-init` and restart to go back.",
                type(exc).__name__, exc, self.settings.db_path,
            )
            self._warned = True
        if self._fallback is None:
            from amort.ledger.sqlite_writer import SqliteWriter

            self._fallback = SqliteWriter(self.settings)
            self.name = "sqlite"
        for sql, row in pending:
            try:
                self._replay(sql, row)
            except Exception as replay_exc:  # noqa: BLE001
                logger.debug("could not replay row into sqlite: %s", replay_exc)

    def _replay(self, sql: str, row: tuple[Any, ...]) -> None:
        """Re-issue a buffered Snowflake row against the SQLite schema."""
        assert self._fallback is not None
        if sql is _STEP_INSERT or "INTO STEPS" in sql:
            table, cols, n = "STEPS", _SQLITE_STEP_COLS, 11
        elif "INTO RUNS" in sql:
            table, cols, n = "RUNS", _SQLITE_RUN_COLS, 16
        else:
            table, cols, n = "SKILLS", _SQLITE_SKILL_COLS, 10
        placeholders = ", ".join("?" * n)
        self._fallback._insert(  # noqa: SLF001 — deliberate: same package, replay path
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", row
        )

    def close(self) -> None:
        self.flush()
        self._disarm_timer()
        if self._fallback is not None:
            self._fallback.close()
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None


_SQLITE_RUN_COLS = (
    "RUN_ID, TASK_FINGERPRINT, LANE, MODE, MODEL, STARTED_AT, ENDED_AT, WALL_MS, "
    "LLM_CALLS, TOOL_CALLS, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, SKILL_ID, PARITY, OUTPUT_HASH"
)
_SQLITE_STEP_COLS = (
    "RUN_ID, STEP_IDX, KIND, NAME, MODEL, INPUT_TOKENS, OUTPUT_TOKENS, COST_USD, WALL_MS, TS, META"
)
_SQLITE_SKILL_COLS = (
    "SKILL_ID, TASK_FINGERPRINT, STATUS, CREATED_AT, RUNS_OBSERVED, PARITY_RATE, "
    "AVG_COLD_COST, AVG_WARM_COST, TOTAL_SAVED_USD, MD_PATH"
)


def _ts(value: str) -> str:
    """ISO-8601 with the trailing `Z`/offset stripped — TIMESTAMP_NTZ is naive UTC."""
    text = value.replace("Z", "")
    if "+" in text[10:]:
        text = text[: 10 + text[10:].index("+")]
    return text


__all__ = ["BATCH_SIZE", "FLUSH_INTERVAL_S", "SnowflakeWriter"]
