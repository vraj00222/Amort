"""StepEvent + the single `emit()` seam every cost number flows through.

One row per LLM call, tool call, replay step, or grade. This is the PROVE layer's
raw material: the 2x2 demo table, the amortization curve, and the SAVINGS view
are all aggregations of these rows.

Load-bearing invariants:

* **`emit()` never raises and never blocks the request path.** Telemetry that can
  fail a proxied request is worse than no telemetry — a Snowflake hiccup must not
  turn into a 500 for the caller. Every writer is wrapped; failures degrade to
  SQLite and are logged once.
* Backend selection happens once per process (`AMORT_LEDGER=auto|snowflake|sqlite`)
  and is observable via `active_backend()` so the report can state which store the
  numbers came from instead of implying Snowflake.
* `cost_usd` is computed here, from `pricing.py`, so no caller can invent one.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import logging
import threading
import uuid
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from amort.config import Settings, get_settings
from amort.ledger.pricing import cost_usd

logger = logging.getLogger("amort.ledger")

Kind = Literal["llm", "tool", "replay", "grade"]
Lane = Literal["baseline", "amortize"]
Mode = Literal["cold", "warm"]


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


class StepEvent(BaseModel):
    """One unit of work. Schema is authoritative — matches STEPS in Snowflake."""

    run_id: str
    lane: Lane = "baseline"
    mode: Mode = "cold"
    task_fingerprint: str = ""
    step_idx: int = 0
    kind: Kind = "llm"
    name: str = ""
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    wall_ms: int = 0
    ts: str = Field(default_factory=_now_iso)
    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def for_llm(
        cls,
        *,
        run_id: str,
        model: str | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        wall_ms: int = 0,
        **kwargs: Any,
    ) -> StepEvent:
        """Build an LLM step with the cost derived, never passed in."""
        meta = dict(kwargs.pop("meta", {}) or {})
        if cache_read_tokens or cache_write_tokens:
            meta.setdefault("cache_read_tokens", cache_read_tokens)
            meta.setdefault("cache_write_tokens", cache_write_tokens)
        return cls(
            run_id=run_id,
            kind="llm",
            name=kwargs.pop("name", None) or (model or "unknown"),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd(
                model,
                input_tokens,
                output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
            ),
            wall_ms=wall_ms,
            meta=meta,
            **kwargs,
        )


class RunRecord(BaseModel):
    """One row in RUNS — the per-run rollup the dashboard charts."""

    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:16]}")
    task_fingerprint: str = ""
    lane: Lane = "baseline"
    mode: Mode = "cold"
    model: str | None = None
    started_at: str = Field(default_factory=_now_iso)
    ended_at: str = Field(default_factory=_now_iso)
    wall_ms: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    skill_id: str | None = None
    parity: str | None = None
    output_hash: str | None = None

    @classmethod
    def from_case(cls, case: dict[str, Any]) -> RunRecord:
        """Build from `RunRecorder.to_case()` — the demo harness's path in."""
        fields = set(cls.model_fields)
        return cls(**{k: v for k, v in case.items() if k in fields})


class SkillRecord(BaseModel):
    """One row in SKILLS. TODO(layer2): written by `compiler.py` once it exists."""

    skill_id: str
    task_fingerprint: str = ""
    status: Literal["candidate", "verified", "trusted"] = "candidate"
    created_at: str = Field(default_factory=_now_iso)
    runs_observed: int = 0
    parity_rate: float | None = None
    avg_cold_cost: float | None = None
    avg_warm_cost: float | None = None
    total_saved_usd: float | None = None
    md_path: str | None = None


class LedgerWriter(Protocol):
    """The interface both backends satisfy."""

    name: str

    def write_step(self, event: StepEvent) -> None: ...
    def write_run(self, run: RunRecord) -> None: ...
    def write_skill(self, skill: SkillRecord) -> None: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...


# ─────────────────────────────────────────────────────────────────────────────
# Backend selection
# ─────────────────────────────────────────────────────────────────────────────

_LOCK = threading.Lock()
_WRITER: LedgerWriter | None = None


def get_writer(settings: Settings | None = None) -> LedgerWriter:
    """Process-wide writer. Selected once; falls back to SQLite on any failure."""
    global _WRITER
    if _WRITER is not None:
        return _WRITER
    with _LOCK:
        if _WRITER is None:
            _WRITER = _select_writer(settings or get_settings())
    return _WRITER


def _select_writer(settings: Settings) -> LedgerWriter:
    from amort.ledger.sqlite_writer import SqliteWriter

    choice = settings.amort_ledger
    if choice == "sqlite":
        return SqliteWriter(settings)

    if choice in ("auto", "snowflake"):
        if not settings.snowflake_configured:
            if choice == "snowflake":
                logger.warning(
                    "AMORT_LEDGER=snowflake but SNOWFLAKE_ACCOUNT/USER/PASSWORD are unset — "
                    "using the local SQLite ledger instead."
                )
            else:
                logger.info("Snowflake creds not set — using local SQLite ledger.")
            return SqliteWriter(settings)
        try:
            from amort.ledger.snowflake_writer import SnowflakeWriter

            writer = SnowflakeWriter(settings)
            writer.connect()
            logger.info("Ledger backend: Snowflake (%s)", settings.snowflake_database)
            return writer
        except Exception as exc:  # noqa: BLE001 — degrade, never fail startup
            logger.warning("Snowflake unreachable (%s) — falling back to SQLite ledger.", exc)
            return SqliteWriter(settings)

    return SqliteWriter(settings)


def active_backend() -> str:
    """`"snowflake"` or `"sqlite"` — what the numbers actually came from."""
    return get_writer().name


def reset_writer() -> None:
    """Drop the cached writer (tests, and after changing env in-process)."""
    global _WRITER
    with _LOCK:
        if _WRITER is not None:
            with contextlib.suppress(Exception):
                _WRITER.close()
        _WRITER = None


# ─────────────────────────────────────────────────────────────────────────────
# Emit
# ─────────────────────────────────────────────────────────────────────────────


def emit(event: StepEvent) -> StepEvent:
    """Record one step. Swallows every backend error by design."""
    try:
        get_writer().write_step(event)
    except Exception as exc:  # noqa: BLE001 — telemetry must never fail a request
        logger.warning("ledger.write_step failed (%s): %s", type(exc).__name__, exc)
    return event


def emit_run(run: RunRecord) -> RunRecord:
    try:
        get_writer().write_run(run)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ledger.write_run failed (%s): %s", type(exc).__name__, exc)
    return run


def emit_skill(skill: SkillRecord) -> SkillRecord:
    try:
        get_writer().write_skill(skill)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ledger.write_skill failed (%s): %s", type(exc).__name__, exc)
    return skill


def flush() -> None:
    try:
        get_writer().flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ledger.flush failed: %s", exc)


__all__ = [
    "LedgerWriter",
    "RunRecord",
    "SkillRecord",
    "StepEvent",
    "active_backend",
    "emit",
    "emit_run",
    "emit_skill",
    "flush",
    "get_writer",
    "reset_writer",
]
