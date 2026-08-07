"""Trajectory recorder — turns a live run into a Case dict.

One `RunRecorder` per run. The agent (or the proxy) calls `llm_step()` /
`tool_step()` as things happen; `finish()` closes the run and returns the dict
that `store_everos.record_case()` persists and that `ledger` writes as a `RUNS`
row.

Load-bearing invariants:

* The recorder is **pure bookkeeping** — it never calls a model, never touches
  the network, and must never raise into the request path. A run that fails
  mid-way still produces a usable Case (`ok=False`), because a failed trajectory
  is evidence too.
* `task_fingerprint` is computed once, at `start`, from the *inputs* (system
  prompt, user message, tool catalogue) — never from anything observed later, or
  a warm run could not be matched to its cold ancestor.
* Wall-clock is measured with `perf_counter`; step timings must stay comparable
  across lanes, so no wall-clock arithmetic on `ts`.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from amort.skills.store_everos import fingerprint, fingerprint_query

Kind = Literal["llm", "tool", "replay", "grade"]


@dataclass
class RecordedStep:
    """One unit of work inside a run. Mirrors `StepEvent`'s shape."""

    step_idx: int
    kind: Kind
    name: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    wall_ms: int = 0
    ts: str = ""
    args: dict[str, Any] | None = None
    output: Any = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "kind": self.kind,
            "name": self.name,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "wall_ms": self.wall_ms,
            "ts": self.ts,
            "args": self.args,
            "meta": self.meta,
        }


class RunRecorder:
    """Accumulates a run's trajectory into a Case dict.

    Usage::

        rec = RunRecorder(lane="baseline", mode="cold", system=SYS,
                          user_msg=TASK, tool_names=[t["name"] for t in TOOLS])
        rec.llm_step("claude-…", input_tokens=…, output_tokens=…, wall_ms=…)
        rec.tool_step("fetch_tickets", args={...}, output=[...], wall_ms=…)
        case = rec.finish(final_output={...})
    """

    def __init__(
        self,
        *,
        lane: Literal["baseline", "amortize"],
        mode: Literal["cold", "warm"],
        system: str,
        user_msg: str,
        tool_names: list[str],
        run_id: str | None = None,
        model: str | None = None,
        simulated: bool = False,
    ) -> None:
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:16]}"
        # True when the numbers are estimated rather than reported by the API.
        # Carried all the way to demo_report.json — an unlabelled estimate on a
        # cost dashboard is indistinguishable from a measurement, and worse.
        self.simulated = simulated
        self.lane = lane
        self.mode = mode
        self.system = system
        self.user_msg = user_msg
        self.tool_names = list(tool_names)
        self.model = model
        self.task_fingerprint = fingerprint(system, user_msg, self.tool_names)
        self.query = fingerprint_query(system, user_msg, self.tool_names)
        self.steps: list[RecordedStep] = []
        self.started_at = _dt.datetime.now(_dt.UTC)
        self.ended_at: _dt.datetime | None = None
        self._t0 = time.perf_counter()
        self.final_output: Any = None
        self.ok = True
        self.error: str | None = None
        self.skill_id: str | None = None
        self.parity: str | None = None

    # -- recording -----------------------------------------------------------

    def add(self, step: RecordedStep) -> RecordedStep:
        step.step_idx = len(self.steps)
        step.ts = step.ts or _dt.datetime.now(_dt.UTC).isoformat()
        self.steps.append(step)
        return step

    def llm_step(
        self,
        model: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        wall_ms: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> RecordedStep:
        self.model = self.model or model
        return self.add(
            RecordedStep(
                step_idx=0,
                kind="llm",
                name=model,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                wall_ms=wall_ms,
                meta=meta or {},
            )
        )

    def tool_step(
        self,
        name: str,
        *,
        args: dict[str, Any] | None = None,
        output: Any = None,
        wall_ms: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> RecordedStep:
        return self.add(
            RecordedStep(
                step_idx=0,
                kind="tool",
                name=name,
                args=args,
                output=output,
                wall_ms=wall_ms,
                meta=meta or {},
            )
        )

    def replay_step(self, skill_id: str, *, wall_ms: int = 0, **meta: Any) -> RecordedStep:
        """One replayed-skill marker step (the harness's warm-lane bookkeeping)."""
        self.skill_id = skill_id
        return self.add(
            RecordedStep(step_idx=0, kind="replay", name=f"skill:{skill_id}", wall_ms=wall_ms, meta=meta)
        )

    def grade_step(self, verdict: str, *, wall_ms: int = 0, **meta: Any) -> RecordedStep:
        """One parity-grade marker step — warm output vs cold output."""
        self.parity = verdict
        return self.add(
            RecordedStep(step_idx=0, kind="grade", name=f"grade:{verdict}", wall_ms=wall_ms, meta=meta)
        )

    def fail(self, error: str) -> None:
        self.ok = False
        self.error = error

    # -- rollups -------------------------------------------------------------

    @property
    def wall_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    @property
    def input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.steps)

    @property
    def output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.steps)

    @property
    def cost_usd(self) -> float:
        return round(sum(s.cost_usd for s in self.steps), 6)

    @property
    def llm_calls(self) -> int:
        return sum(1 for s in self.steps if s.kind == "llm")

    @property
    def tool_calls(self) -> int:
        return sum(1 for s in self.steps if s.kind == "tool")

    @property
    def output_hash(self) -> str:
        """Stable hash of the final output — the parity grader's cheap first pass."""
        payload = json.dumps(self.final_output, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    # -- close ---------------------------------------------------------------

    def finish(self, final_output: Any = None) -> dict[str, Any]:
        """Close the run and return the Case dict."""
        self.final_output = final_output
        self.ended_at = _dt.datetime.now(_dt.UTC)
        return self.to_case()

    def to_case(self) -> dict[str, Any]:
        """The dict consumed by `store_everos.record_case()` and the ledger."""
        return {
            "run_id": self.run_id,
            "lane": self.lane,
            "mode": self.mode,
            "task_fingerprint": self.task_fingerprint,
            "query": self.query,
            "task_intent": self.user_msg,
            "user_msg": self.user_msg,
            "system": self.system,
            "model": self.model,
            "tool_names": self.tool_names,
            "started_at": self.started_at.isoformat(),
            "ended_at": (self.ended_at or _dt.datetime.now(_dt.UTC)).isoformat(),
            "wall_ms": self.wall_ms,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "skill_id": self.skill_id,
            "parity": self.parity,
            "output_hash": self.output_hash,
            "final_output": self.final_output,
            "ok": self.ok,
            "error": self.error,
            "simulated": self.simulated,
            "quality_score": 1.0 if self.ok else 0.0,
            "key_insight": self._key_insight(),
            "steps": [s.to_dict() for s in self.steps],
        }

    def _key_insight(self) -> str:
        """One line an LLM would otherwise have to re-derive: the tool order."""
        order = " → ".join(s.name for s in self.steps if s.kind == "tool")
        if not order:
            return ""
        return f"Tool order that solved this task: {order}"


__all__ = ["RecordedStep", "RunRecorder"]
