"""Parity grader — does the warm run produce the same answer as the cold one?

This is the check that makes the savings claim honest. A warm run is only worth
anything if its output is *equivalent* to the cold run it replaced; a cheap wrong
answer is not a saving, it is a regression with a discount.

The comparison is deliberately **field-exact on the structured report**, not a
diff of prose. `ticket_triage` returns a JSON object, so parity is decidable:
same tickets, same queue, same priority, same SLA flag. That is why the demo task
was designed to emit structured output at all.

Three verdicts, and the distinction matters:

* `✓`   — the two runs agree field for field.
* `✗`   — they disagree; the mismatching fields are listed, not summarized.
* `n/a` — there is nothing to compare, because no warm run happened. Today that
  is the normal case: Layer 2 is a stub, so nothing is ever replayed. Reporting
  `n/a` instead of `✓` is the difference between "we verified equivalence" and
  "we did not run the thing that could have broken it".

`record_parity()` is the promotion ladder: every replay's verdict is written
back onto the Skill markdown (`runs_observed`, `parity_rate`, `parity_passes`)
and a fresh append-only SKILLS row is emitted. Two passes promote
`candidate → verified`; ANY fail quarantines the skill so it is never
replayed again until a human (or a re-distillation) clears it.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("amort.skills.grader")

Verdict = Literal["match", "mismatch", "n/a"]

# Fields compared per report row. Ordering and extra keys are ignored; these are
# the ones a wrong answer would get wrong.
REPORT_KEY = "ticket_id"
REPORT_FIELDS = ("queue", "priority", "sla_breach", "draft_reply_needed")


@dataclass
class ParityResult:
    """Outcome of comparing two runs' outputs."""

    verdict: Verdict
    compared: int = 0
    mismatches: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def symbol(self) -> str:
        return {"match": "✓", "mismatch": "✗", "n/a": "n/a"}[self.verdict]

    @property
    def ok(self) -> bool:
        return self.verdict == "match"

    def summary(self) -> str:
        if self.verdict == "n/a":
            return f"parity n/a — {self.reason}"
        if self.verdict == "match":
            return f"parity ✓ — {self.compared} field(s) identical"
        head = "; ".join(self.mismatches[:3])
        more = f" (+{len(self.mismatches) - 3} more)" if len(self.mismatches) > 3 else ""
        return f"parity ✗ — {len(self.mismatches)} mismatch(es): {head}{more}"


def grade(cold: Any, warm: Any, *, reason_when_missing: str = "no warm run to compare") -> ParityResult:
    """Compare a cold and a warm output. Never raises."""
    if cold is None or warm is None:
        return ParityResult("n/a", reason=reason_when_missing)
    if not isinstance(cold, dict) or not isinstance(warm, dict):
        return _compare_scalar(cold, warm)

    cold_rows = cold.get("report")
    warm_rows = warm.get("report")
    if isinstance(cold_rows, list) and isinstance(warm_rows, list):
        return _compare_reports(cold_rows, warm_rows)
    return _compare_scalar(cold, warm)


def _compare_reports(cold: list[Any], warm: list[Any]) -> ParityResult:
    cold_by_id = {r.get(REPORT_KEY): r for r in cold if isinstance(r, dict)}
    warm_by_id = {r.get(REPORT_KEY): r for r in warm if isinstance(r, dict)}
    mismatches: list[str] = []

    for missing in sorted(set(cold_by_id) - set(warm_by_id), key=str):
        mismatches.append(f"{missing}: missing from warm run")
    for extra in sorted(set(warm_by_id) - set(cold_by_id), key=str):
        mismatches.append(f"{extra}: only in warm run")

    compared = 0
    for key in sorted(set(cold_by_id) & set(warm_by_id), key=str):
        for fname in REPORT_FIELDS:
            compared += 1
            a, b = cold_by_id[key].get(fname), warm_by_id[key].get(fname)
            if a != b:
                mismatches.append(f"{key}.{fname}: {a!r} != {b!r}")

    if mismatches:
        return ParityResult("mismatch", compared=compared, mismatches=mismatches)
    return ParityResult("match", compared=compared)


def _compare_scalar(cold: Any, warm: Any) -> ParityResult:
    a = json.dumps(cold, sort_keys=True, default=str)
    b = json.dumps(warm, sort_keys=True, default=str)
    if a == b:
        return ParityResult("match", compared=1)
    return ParityResult("mismatch", compared=1, mismatches=["output differs"])


def grade_accuracy(actual: Any, expected: Any) -> ParityResult:
    """Compare a run against ground truth — a different question from parity.

    Two runs can agree with each other and both be wrong. The demo reports these
    separately so "parity ✓" is never mistaken for "correct".
    """
    result = grade(actual, expected, reason_when_missing="no ground truth available")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Promotion ladder — parity verdicts written back onto the Skill
# ─────────────────────────────────────────────────────────────────────────────


def update_skill_frontmatter(md_path: str, **updates: Any) -> dict[str, Any]:
    """Patch keys into a skill markdown's frontmatter, preserving the rest."""
    from amort.skills.store_everos import _join_markdown, _split_markdown

    path = Path(md_path)
    front, body = _split_markdown(path.read_text("utf-8"))
    front.update(updates)
    path.write_text(_join_markdown(front, body))
    return front


def record_parity(skill_id: str, parity_result: ParityResult) -> None:
    """Fold one replay's parity verdict into the skill's ladder state.

    `runs_observed += 1`; `parity_rate` recomputed from the pass count; two
    passes promote `candidate → verified`; ANY fail sets `status: quarantined`.
    Also emits a fresh append-only SKILLS row. Never raises.
    """
    try:
        from amort.ledger.events import SkillRecord, emit_skill
        from amort.skills.store_everos import get_store

        skill = get_store().local.load_skill(skill_id)
        if skill is None or not skill.md_path:
            logger.warning("record_parity: skill %s not found — verdict dropped", skill_id)
            return
        front, _ = _read_front(skill.md_path)
        runs = int(front.get("runs_observed") or 0) + 1
        passes = int(front.get("parity_passes") or 0) + (1 if parity_result.ok else 0)
        status = str(front.get("status") or "candidate")
        if not parity_result.ok:
            status = "quarantined"
        elif status == "candidate" and passes >= 2:
            status = "verified"
        update_skill_frontmatter(
            skill.md_path,
            runs_observed=runs,
            parity_passes=passes,
            parity_rate=round(passes / runs, 4),
            status=status,
            updated_at=_dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat(),
        )
        emit_skill(SkillRecord(
            skill_id=skill_id,
            task_fingerprint=skill.task_fingerprint,
            # SKILLS.status literal has no 'quarantined'; a quarantined skill is
            # ledgered as a demoted candidate — the markdown is authoritative.
            status="candidate" if status == "quarantined" else status,  # type: ignore[arg-type]
            runs_observed=runs,
            parity_rate=round(passes / runs, 4),
            md_path=skill.md_path,
        ))
        logger.info("record_parity: %s %s -> status=%s rate=%.2f (%d/%d)",
                    skill_id, parity_result.symbol, status, passes / runs, passes, runs)
    except Exception as exc:  # noqa: BLE001 — grading must never fail a run
        logger.warning("record_parity failed for %s: %s", skill_id, exc)


def _read_front(md_path: str) -> tuple[dict[str, Any], str]:
    from amort.skills.store_everos import _split_markdown

    return _split_markdown(Path(md_path).read_text("utf-8"))


__all__ = [
    "REPORT_FIELDS",
    "REPORT_KEY",
    "ParityResult",
    "Verdict",
    "grade",
    "grade_accuracy",
    "record_parity",
    "update_skill_frontmatter",
]
