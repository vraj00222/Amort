"""Case → Skill compiler — Layer 2's first half.

Watch repeated successful runs of the same task and distil the procedure they
share into a Skill: human-readable Markdown (Trigger / Parameters / Steps /
Output template / Guards) plus an embedded machine-readable ``replay-plan``
block that `replayer.py` executes as code.

Two compile paths, one honest cut line:

* **llm** — one LLM call turns the best case's trajectory into the markdown
  sections. Validated (all sections present, no hallucinated tools); the
  machine plan is always built deterministically from the recorded steps, so
  replay correctness never depends on model prose.
* **template** — if the LLM output fails validation (or the call fails), the
  same sections are rendered from `common_tool_sequence()` + the recorded
  steps, marked `compiler: template` in frontmatter.

Promotion at compile time: `status="verified"` iff ≥2 contributing cases'
final outputs pass the parity grader field-exact pairwise — two agreeing runs
are the promotion ladder's two passes. Otherwise `candidate`.

A Skill is a *hypothesis* about a procedure, never a fact. Any guard failure
at replay time falls back to the full agent; the grader demotes on any parity
fail. A compiler that emits `trusted` Skills directly is how a system starts
silently returning wrong answers cheaply.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import logging
import re
from pathlib import Path
from typing import Any

from amort.ledger.events import SkillRecord, StepEvent, emit, emit_skill
from amort.ledger.pricing import cost_usd
from amort.skills.grader import grade, update_skill_frontmatter
from amort.skills.llm import chat
from amort.skills.replayer import _section
from amort.skills.store_everos import (
    Skill,
    _sanitize_skill_name,
    _split_markdown,
    get_settings,
    get_store,
)

logger = logging.getLogger("amort.skills.compiler")

# A procedure seen once is an anecdote; two agreeing runs are a pattern.
MIN_CASES_TO_DISTIL = 2

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

_SECTIONS = ("Trigger", "Parameters", "Steps", "Output template", "Guards")

# Machine-checkable guards per known tool (`<tool> returns <field> <op> <value>`).
# ponytail: guard vocabulary covers the fixture task's tools; a new task family
# adds its rows here or ships guard-less steps (which replay skips checking).
_DEFAULT_GUARDS = {
    "fetch_tickets": "fetch_tickets returns count >= 1",
    "classify": "classify returns classifications.length >= 1",
    "check_sla": "check_sla returns evaluated >= 1",
    "assign_queue": "assign_queue returns rejected.length == 0",
}


def compile_skill(cases: list[dict[str, Any]]) -> Skill | None:
    """Distil a cluster of Cases into a Skill.

    Args:
        cases: Case dicts (as produced by `RunRecorder.to_case()`), expected to
            share a `task_fingerprint` and to have `ok=True`.

    Returns:
        The persisted Skill (`verified` when the cases' outputs agree
        field-exact, else `candidate`), or None when the cluster is too small.
    """
    ok_cases = [c for c in cases if c.get("ok") and c.get("task_fingerprint")]
    if not ok_cases:
        return None
    fp = str(ok_cases[0]["task_fingerprint"])
    cluster = [c for c in ok_cases if c["task_fingerprint"] == fp]
    if len(cluster) < MIN_CASES_TO_DISTIL:
        logger.debug("compile_skill: %d case(s) < %d — not distilling",
                     len(cluster), MIN_CASES_TO_DISTIL)
        return None

    best = min(cluster, key=lambda c: (c.get("llm_calls") or 99, c.get("cost_usd") or 0.0))
    plan = _build_plan(best, cluster)
    if not plan["steps"]:
        logger.info("compile_skill: no tool steps recorded — nothing to distil")
        return None

    # Promotion at compile time: >=2 agreeing final outputs = the ladder's two passes.
    verified = True
    for a, b in itertools.combinations(cluster, 2):
        parity = grade(a.get("final_output"), b.get("final_output"))
        if not parity.ok:
            verified = False
            logger.warning("compile_skill: %s vs %s disagree — %s",
                           a.get("run_id"), b.get("run_id"), parity.summary())
    status = "verified" if verified else "candidate"

    markdown, compiler_kind, usage = _markdown(best, plan)
    body = markdown.rstrip() + "\n\n```replay-plan\n" + json.dumps(plan, indent=2) + "\n```\n"

    final = best.get("final_output") if isinstance(best.get("final_output"), dict) else {}
    name = str((final or {}).get("task") or f"skill_{fp[3:11]}")
    skill_id = f"skl_{fp[3:15]}"
    skill = Skill(
        skill_id=skill_id,
        name=name,
        description=str(best.get("user_msg") or "")[:160],
        task_fingerprint=fp,
        status=status,
        body=body,
        source_case_ids=[str(c.get("run_id") or "") for c in cluster],
        tools_required=list(dict.fromkeys(st["tool"] for st in plan["steps"])),
        parity_rate=1.0 if verified else None,
        confidence=0.9 if verified else 0.5,
        maturity_score=float(len(cluster)),
    )

    version = _next_version(name)
    md_path = get_store().write_skill(skill)
    update_skill_frontmatter(
        md_path,
        version=version,
        runs_observed=len(cluster),
        parity_passes=len(cluster) if verified else 0,
        compiler=compiler_kind,
    )

    if usage:  # the one compile LLM call, logged under the amortize-lane cold run
        run_id = next(
            (str(c["run_id"]) for c in reversed(cluster) if c.get("lane") == "amortize"),
            str(cluster[-1].get("run_id") or ""),
        )
        emit(StepEvent(
            run_id=run_id, lane="amortize", mode="cold", task_fingerprint=fp,
            kind="llm", name="compile", model=usage["model"],
            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
            cost_usd=cost_usd(usage["model"], usage["input_tokens"], usage["output_tokens"]),
            wall_ms=usage["wall_ms"],
            meta={"phase": "compile", "compiler": compiler_kind, "skill_id": skill_id},
        ))

    emit_skill(SkillRecord(
        skill_id=skill_id, task_fingerprint=fp, status=status,
        runs_observed=len(cluster), parity_rate=1.0 if verified else None,
        avg_cold_cost=round(sum(float(c.get("cost_usd") or 0.0) for c in cluster) / len(cluster), 6),
        md_path=md_path,
    ))
    logger.info("compiled %s (%s, %s) from %d case(s) -> %s",
                skill_id, status, compiler_kind, len(cluster), md_path)
    return dataclasses.replace(skill, md_path=md_path)


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic replay plan — built from the recorded trajectory, never the LLM
# ─────────────────────────────────────────────────────────────────────────────


def _build_plan(case: dict[str, Any], cluster: list[dict[str, Any]]) -> dict[str, Any]:
    """The executable half of the Skill: steps, args, params, guards, rubric."""
    user_msg = str(case.get("user_msg") or "")
    recorded = [s for s in (case.get("steps") or []) if s.get("kind") == "tool"]
    common = common_tool_sequence(cluster)
    if common is not None and [s["name"] for s in recorded] != common:
        recorded = [s for s in recorded if s["name"] in common]

    params: dict[str, dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []
    for s in recorded:
        args: dict[str, Any] = {}
        for key, value in (s.get("args") or {}).items():
            if key == "ticket_ids" and isinstance(value, list):
                args[key] = "$fetched_ids"  # re-derived from the fetch step's output
            elif key == "assignments" and isinstance(value, list):
                args[key] = "$assignments"  # recomputed from the rubric at replay
            elif isinstance(value, str) and key not in params and _mentioned(value, user_msg):
                params[key] = {"default": value}
                args[key] = "{{" + key + "}}"
            else:
                args[key] = value
        steps.append({"tool": s["name"], "args": args, "guard": _DEFAULT_GUARDS.get(s["name"])})

    final = case.get("final_output") if isinstance(case.get("final_output"), dict) else {}
    return {
        "task_name": str((final or {}).get("task") or "task"),
        "output": "triage_report" if isinstance((final or {}).get("report"), list) else "verbatim",
        "parameters": params,
        # The routing rubric, lifted from the recorded system prompt ("billing→billing-ops, …").
        "queue_map": dict(re.findall(r"(\w+)→([\w-]+)", str(case.get("system") or ""))),
        # ponytail: the priority ladder is a named rule implemented in replayer.py
        # (breached/plan/severity, exactly the SYSTEM rubric); a second task
        # family needs its own named rule or a real derivation DSL.
        "priority_rule": "sla_plan_severity_v1",
        "steps": steps,
    }


def _mentioned(value: str, user_msg: str) -> bool:
    """A recorded arg whose value the user message contains is a parameter."""
    norm = value.replace("_", " ").strip().lower()
    return len(norm) >= 3 and re.search(rf"\b{re.escape(norm)}\b", user_msg.lower()) is not None


def _next_version(name: str) -> int:
    """Bump `version` on every re-distillation of the same skill."""
    path = get_settings().skills_dir / f"skill_{_sanitize_skill_name(name)}" / "SKILL.md"
    if not path.exists():
        return 1
    front, _ = _split_markdown(Path(path).read_text("utf-8"))
    return int(front.get("version") or 0) + 1


# ─────────────────────────────────────────────────────────────────────────────
# Markdown — one LLM call, validated, with a deterministic template fallback
# ─────────────────────────────────────────────────────────────────────────────


def _markdown(case: dict[str, Any], plan: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    """Returns (markdown, compiler_kind, llm_usage|None)."""
    tools_used = [st["tool"] for st in plan["steps"]]
    guards = [st["guard"] for st in plan["steps"] if st.get("guard")]
    prompt = (
        f"Task request: {case.get('user_msg')}\n\n"
        "Trajectory (tool calls in order, with arguments):\n"
        f"{json.dumps([{'tool': st['tool'], 'args': _truncate(st['args'])} for st in plan['steps']], indent=2)}\n\n"
        f"Parameters bound from the request: {json.dumps(plan['parameters'])}\n\n"
        f"Final output shape (truncated):\n{json.dumps(_truncate(case.get('final_output')), indent=2)}\n\n"
        "Rules:\n"
        f"- ## Steps: one numbered item per tool call, in order, naming each tool exactly "
        f"(they were: {', '.join(tools_used)}); show constant arguments verbatim and write each "
        "parameter as a {{name}} placeholder. Do not invent tools.\n"
        f"- ## Guards: one guard per step, machine-checkable phrasing "
        f"`<tool> returns <field> <op> <value>`. Use exactly these guards:\n"
        + "".join(f"  - {g}\n" for g in guards)
        + "- ## Output template: the JSON shape of the final output, with <int>/<str>/<bool> placeholders.\n"
        "- ## Trigger: one sentence saying when this skill applies.\n"
        "- ## Parameters: a bullet per parameter with its example value, or `(none)`.\n"
    )
    try:
        text, usage = chat(
            [
                {"role": "system", "content": (
                    "You distil an agent trajectory into a reusable Skill. Reply with markdown "
                    "only, containing exactly these five second-level sections: ## Trigger, "
                    "## Parameters, ## Steps, ## Output template, ## Guards."
                )},
                {"role": "user", "content": prompt},
            ],
            max_tokens=6144,  # reasoning + ~600 tokens of markdown
        )
    except Exception as exc:  # noqa: BLE001 — cut line: never let compile fail on the LLM
        logger.warning("compile LLM call failed (%s) — using template compiler", exc)
        return _markdown_template(case, plan), "template", None

    rebuilt = _rebuild(text, plan, case)
    if rebuilt is None:
        logger.warning("compile LLM output failed validation — using template compiler")
        return _markdown_template(case, plan), "template", usage
    return rebuilt, "llm", usage


def _rebuild(text: str, plan: dict[str, Any], case: dict[str, Any]) -> str | None:
    """Validate the LLM's markdown; rebuild it into SKILL_TEMPLATE, or None."""
    sections = {title: _section(text, title) for title in _SECTIONS}
    if any(not content for content in sections.values()):
        return None
    catalogue = [str(t) for t in (case.get("tool_names") or [])]
    used = {st["tool"] for st in plan["steps"]}
    named = {t for t in catalogue if re.search(rf"\b{re.escape(t)}\b", sections["Steps"])}
    if named != used:  # missing a real step, or a hallucinated tool
        return None
    return SKILL_TEMPLATE.format(
        title=plan["task_name"],
        trigger=sections["Trigger"],
        parameters=sections["Parameters"],
        steps=sections["Steps"],
        output_template=sections["Output template"],
        guards=sections["Guards"],
    )


def _markdown_template(case: dict[str, Any], plan: dict[str, Any]) -> str:
    """Deterministic fallback: the same sections, rendered from the records."""
    user_msg = str(case.get("user_msg") or "").strip()
    params = plan["parameters"]
    parameters = "\n".join(
        f"- {{{{{k}}}}} — bound from the user request, e.g. `{v['default']}`"
        for k, v in params.items()
    ) or "(none — every argument is a constant)"
    steps = "\n".join(
        f"{i}. tool: `{st['tool']}` — args: `{json.dumps(st['args'], default=str)}`"
        for i, st in enumerate(plan["steps"], 1)
    )
    guards = "\n".join(f"- {st['guard']}" for st in plan["steps"] if st.get("guard")) or "(none)"
    output_template = (
        "```json\n" + json.dumps(_truncate(case.get("final_output")), indent=2, default=str) + "\n```"
    )
    return SKILL_TEMPLATE.format(
        title=plan["task_name"],
        trigger=f"When the request asks: {user_msg.split('.')[0][:200]}.",
        parameters=parameters,
        steps=steps,
        output_template=output_template,
        guards=guards,
    )


def _truncate(obj: Any, *, max_items: int = 3, max_str: int = 200) -> Any:
    """Shrink big lists/strings so prompts stay small (display only)."""
    if isinstance(obj, list):
        head = [_truncate(v, max_items=max_items, max_str=max_str) for v in obj[:max_items]]
        if len(obj) > max_items:
            head.append(f"... +{len(obj) - max_items} more")
        return head
    if isinstance(obj, dict):
        return {k: _truncate(v, max_items=max_items, max_str=max_str) for k, v in obj.items()}
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + "…"
    return obj


def common_tool_sequence(cases: list[dict[str, Any]]) -> list[str] | None:
    """The tool order shared by every Case, or None if they disagree."""
    sequences = [
        [s["name"] for s in (case.get("steps") or []) if s.get("kind") == "tool"]
        for case in cases
    ]
    if not sequences:
        return None
    first = sequences[0]
    return first if all(seq == first for seq in sequences[1:]) else None


__all__ = ["MIN_CASES_TO_DISTIL", "SKILL_TEMPLATE", "common_tool_sequence", "compile_skill"]
