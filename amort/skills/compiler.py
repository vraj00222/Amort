"""Case → Skill compiler. **STUB — TODO(layer2).**

Layer 2's first half: watch repeated successful runs of the same task, and distil
the procedure they share into a Skill — a human-readable Markdown file with a
trigger, parameters, ordered steps, an output template, and guards.

Nothing here is implemented. The module exists so the interface is fixed and the
call sites (`store_everos.distill_skill`, `cli skills`) are already wired; this
build measures the cold path honestly rather than shipping a half-working
optimizer that the demo would have to apologize for.

## What the implementation looks like

1. **Cluster.** Group Cases by `task_fingerprint`; require at least
   `MIN_CASES_TO_DISTIL` successful ones so a single lucky run can't mint a Skill.
2. **Align.** Find the tool sequence common to every Case in the cluster. Runs
   that differ in tool *order* are not the same procedure and must not be merged.
3. **Abstract.** One LLM call turns the aligned trajectory into Skill Markdown:
   which arguments are constants, which are parameters bound from the user
   message, and which are references to a previous step's output
   (`$steps.N.output`).
4. **Guard.** Derive preconditions and postconditions from what the Cases show —
   step 1 returned a non-empty fixture, step 4 assigned every ticket a queue from
   the known set. Guards are what make the fallback decidable at replay time.
5. **Persist.** Write via `store_everos.write_skill()` with `status: candidate`.
   Promotion to `verified`/`trusted` is the grader's job, not this module's.

## The rule that keeps this safe

A Skill is a *hypothesis* about a procedure, never a fact. It enters at
`candidate`, is only replayed once the parity grader has confirmed it, and any
guard failure at replay time falls back to the full agent. A compiler that emits
`trusted` Skills directly is how a system starts silently returning wrong answers
cheaply.
"""

from __future__ import annotations

import logging
from typing import Any

from amort.skills.store_everos import Skill

logger = logging.getLogger("amort.skills.compiler")

# A procedure seen once is an anecdote.
MIN_CASES_TO_DISTIL = 3

SKILL_TEMPLATE = """\
# Skill: {title}

## Trigger
{trigger}

## Parameters
{parameters}

## Steps
{steps}

## Output template
{output_template}

## Guards
{guards}
"""


def compile_skill(cases: list[dict[str, Any]]) -> Skill | None:
    """TODO(layer2): distil a cluster of Cases into a Skill. Returns None today.

    Args:
        cases: Case dicts (as produced by `RunRecorder.to_case()`), expected to
            share a `task_fingerprint` and to have `ok=True`.

    Returns:
        A `candidate` Skill, or None when the cluster is too small or the runs
        disagree on the procedure.
    """
    if len(cases) < MIN_CASES_TO_DISTIL:
        logger.debug("compile_skill: %d case(s) < %d — not distilling",
                     len(cases), MIN_CASES_TO_DISTIL)
        return None
    logger.info("compile_skill is a stub (TODO layer2) — %d case(s) ignored", len(cases))
    return None


def common_tool_sequence(cases: list[dict[str, Any]]) -> list[str] | None:
    """The tool order shared by every Case, or None if they disagree.

    Implemented because it is pure bookkeeping and the compiler's alignment step
    needs exactly this — and because it makes the stub's future shape concrete
    rather than aspirational.
    """
    sequences = [
        [s["name"] for s in (case.get("steps") or []) if s.get("kind") == "tool"]
        for case in cases
    ]
    if not sequences:
        return None
    first = sequences[0]
    return first if all(seq == first for seq in sequences[1:]) else None


__all__ = ["MIN_CASES_TO_DISTIL", "SKILL_TEMPLATE", "common_tool_sequence", "compile_skill"]
