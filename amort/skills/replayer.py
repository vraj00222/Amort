"""Skill → warm execution. **STUB — TODO(layer2).**

Layer 2's second half, and where the headline number comes from: on a task that
already has a verified Skill, run the procedure **as code** — the tools directly,
in the recorded order — with only two small LLM calls left in the loop:

1. **Bind.** One call maps this request's user message onto the Skill's declared
   parameters (`date_range`, `queue_names`, …). Small input, small output.
2. **Verify.** One call checks the assembled output against the Skill's output
   template before it is returned.

Everything between them is deterministic code. A cold run of `ticket_triage`
spends five model turns re-deciding a procedure it has already executed
correctly; a warm run should spend two, on a fraction of the context.

## The guarantee that has to hold

**Any guard failure falls back to the full agent — silently to the user, loudly
to the ledger.** Cheap and wrong is strictly worse than expensive and right, so
the replayer is written to give up eagerly:

* a Skill whose `status` is still `candidate` is never replayed;
* a tool missing from the caller's catalogue aborts the replay;
* a step guard that fails (empty fixture, a ticket with no queue) aborts it;
* the verify call disagreeing with the output template aborts it;
* an exception anywhere aborts it.

Each abort emits a `replay` StepEvent with the reason, so the dashboard can show
*why* the warm path was not taken — a fallback rate climbing over time is the
signal that a Skill has gone stale and should be demoted.

## Interface (fixed now, implemented later)

    replay(skill, request) -> ReplayOutcome
        .ok          bool     — the warm path completed
        .output      Any      — the result, when ok
        .fallback    str|None — why the agent had to run instead
        .llm_calls   int      — must be ≤ 2 for a replay to count as warm
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from amort.skills.store_everos import Skill

logger = logging.getLogger("amort.skills.replayer")

# A warm run that needs more than this many model calls is not a warm run.
MAX_WARM_LLM_CALLS = 2


@dataclass
class ReplayOutcome:
    """Result of attempting the warm path."""

    ok: bool
    output: Any = None
    fallback: str | None = None
    llm_calls: int = 0
    tool_calls: int = 0
    wall_ms: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)

    @property
    def took_warm_path(self) -> bool:
        return self.ok and self.llm_calls <= MAX_WARM_LLM_CALLS


def replay(skill: Skill, request: dict[str, Any]) -> ReplayOutcome:
    """TODO(layer2): execute `skill` as code. Always falls back today.

    Returning a fallback rather than raising is the contract: the caller's only
    correct response to "the warm path did not happen" is to run the agent, and
    that should not require exception handling at every call site.
    """
    if skill.status == "candidate":
        return ReplayOutcome(
            ok=False,
            fallback=f"skill {skill.skill_id} is still 'candidate' — never replay an unverified skill",
        )
    logger.info("replay is a stub (TODO layer2) — falling back to the full agent")
    return ReplayOutcome(ok=False, fallback="replayer not implemented (TODO layer2)")


def bind_parameters(skill: Skill, user_message: str) -> dict[str, Any]:
    """TODO(layer2): LLM call #1 — map the user message onto the Skill's params."""
    logger.debug("bind_parameters stub for %s", skill.skill_id)
    return {}


def verify_output(skill: Skill, output: Any) -> bool:
    """TODO(layer2): LLM call #2 — check the output against the Skill's template."""
    logger.debug("verify_output stub for %s", skill.skill_id)
    return False


def check_guards(skill: Skill, step_outputs: list[Any]) -> str | None:
    """TODO(layer2): evaluate the Skill's guards. Returns a failure reason or None."""
    return "guards not implemented (TODO layer2)"


__all__ = [
    "MAX_WARM_LLM_CALLS",
    "ReplayOutcome",
    "bind_parameters",
    "check_guards",
    "replay",
    "verify_output",
]
