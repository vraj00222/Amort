"""Skill → warm execution — Layer 2's second half, where the headline number is.

On a task that already has a verified Skill, run the procedure **as code** —
the tools directly, in the compiled order — with exactly two small LLM calls
left in the loop:

1. **Bind.** Map this request's user message onto the Skill's declared
   parameters. Small input, small output.
2. **Verify.** Check a compact digest of the assembled output (counts, breach
   totals, a few sample rows — never the full report) against the Skill's
   output template.

Everything between them is deterministic: step args are resolved from bound
params and earlier tool outputs, every step's guard is checked, and the final
report is assembled in code from the tool outputs per the Skill's output
template. Tool outputs never enter LLM context — that is where the ≥85%
saving lives.

## The guarantee that has to hold

**Any guard failure falls back to the full agent — silently to the user,
loudly to the caller.** Cheap and wrong is strictly worse than expensive and
right, so the replayer gives up eagerly: `candidate` and `quarantined` skills
are never replayed, a missing replay plan aborts, a failing guard aborts, a
verify disagreement aborts, and any exception becomes `ok=False` with a
reason — never a raise.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import operator
import re
import time
from dataclasses import dataclass, field
from typing import Any

from amort.ledger.pricing import cost_usd
from amort.skills.llm import chat
from amort.skills.store_everos import Skill

logger = logging.getLogger("amort.skills.replayer")

# A warm run that needs more than this many model calls is not a warm run.
MAX_WARM_LLM_CALLS = 2

_PLAN_RE = re.compile(r"```replay-plan\s*(\{.*?\})\s*```", re.S)
_GUARD_RE = re.compile(r"^\s*`?(\w+)`?\s+returns\s+([\w.]+)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$")
_OPS = {
    "==": operator.eq, "!=": operator.ne,
    ">=": operator.ge, "<=": operator.le,
    ">": operator.gt, "<": operator.lt,
}


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
    """Execute `skill` as code. Never raises — a fallback reason is the contract."""
    if skill.status == "candidate":
        return ReplayOutcome(
            ok=False,
            fallback=f"skill {skill.skill_id} is still 'candidate' — never replay an unverified skill",
        )
    if skill.status == "quarantined":
        return ReplayOutcome(
            ok=False,
            fallback=f"skill {skill.skill_id} is 'quarantined' — never replay a quarantined skill",
        )
    t0 = time.perf_counter()
    steps: list[dict[str, Any]] = []
    try:
        return _replay_inner(skill, request, steps, t0)
    except Exception as exc:  # noqa: BLE001 — any failure is a fallback, never a raise
        logger.warning("replay %s aborted: %s: %s", skill.skill_id, type(exc).__name__, exc)
        return _outcome(False, steps, t0, fallback=f"replay aborted: {type(exc).__name__}: {exc}")


def _replay_inner(
    skill: Skill, request: dict[str, Any], steps: list[dict[str, Any]], t0: float
) -> ReplayOutcome:
    match = _PLAN_RE.search(skill.body)
    if match is None:
        return _outcome(False, steps, t0, fallback="skill has no replay-plan block")
    plan = json.loads(match.group(1))
    executor = request.get("tool_executor")
    if not callable(executor):
        return _outcome(False, steps, t0, fallback="no tool_executor provided")
    llm_kwargs = {
        "model": request.get("model"),
        "base_url": request.get("base_url"),
        "api_key": request.get("api_key"),
    }

    # -- LLM call #1: BIND the user message onto the declared parameters -----
    params: dict[str, Any] = plan.get("parameters") or {}
    bound = {k: (v or {}).get("default") for k, v in params.items()}
    if params:
        text, usage = chat(
            [
                {"role": "system", "content": (
                    "You bind request parameters for a saved procedure. "
                    "Reply with a single JSON object, no prose."
                )},
                {"role": "user", "content": (
                    f"Request: {request.get('user_msg', '')}\n\n"
                    "Parameters (name: example value):\n"
                    + "".join(f"- {k}: {v.get('default')!r}\n" for k, v in params.items())
                    + "\nReturn JSON mapping every parameter name to its value for this "
                    "request, keeping the same value format as the example."
                )},
            ],
            max_tokens=1024,  # reasoning models spend most of this thinking
            **llm_kwargs,
        )
        steps.append(_llm_step(usage, {"phase": "bind", "skill_id": skill.skill_id}))
        parsed = _parse_json(text)
        if isinstance(parsed, dict):
            for key in params:
                if parsed.get(key) is not None:
                    bound[key] = parsed[key]
        # unparseable bind → keep the recorded defaults; the guards are the net

    # -- Execute the steps as code, guard each one ---------------------------
    outputs: dict[str, Any] = {}
    for idx, st in enumerate(plan.get("steps") or [], 1):
        tool = st["tool"]
        args = _resolve_args(st.get("args") or {}, bound, plan, outputs)
        started = time.perf_counter()
        output = executor(tool, args)
        steps.append(_tool_step(
            tool, args, int((time.perf_counter() - started) * 1000), skill.skill_id
        ))
        guard = st.get("guard")
        if guard:
            reason = _check_guard(guard, output)
            if reason:
                return _outcome(False, steps, t0, fallback=f"step {idx} ({tool}): {reason}")
        outputs[tool] = output  # ponytail: one output per tool name; repeated tools last-win

    # -- Assemble the final output deterministically -------------------------
    if plan.get("output") != "triage_report":
        return _outcome(False, steps, t0,
                        fallback=f"unsupported output template {plan.get('output')!r}")
    final = _assemble_triage(plan, outputs)

    # -- LLM call #2: VERIFY a compact digest against the output template ----
    rows = final["report"]
    digest = {
        "task": final["task"],
        "ticket_count": final["ticket_count"],
        "summary": final["summary"],
        "recount": {
            "rows": len(rows),
            "breaches": sum(1 for r in rows if r["sla_breach"]),
            "p0": sum(1 for r in rows if r["priority"] == "P0"),
        },
        "sample_rows": rows[:3],
    }
    template_txt = _section(_PLAN_RE.sub("", skill.body), "Output template")[:1500]
    text, usage = chat(
        [
            {"role": "user", "content": (
                "A saved procedure assembled a large JSON output. You are checking a DIGEST "
                "of it, not the full output: the full `report` array is deliberately omitted; "
                "`sample_rows` are its first rows and `recount` holds counts recomputed from "
                "all rows.\n\n"
                f"Output template (the shape the full output must have):\n{template_txt}\n\n"
                f"Digest:\n{json.dumps(digest, default=str)}\n\n"
                "Checks: (1) sample_rows match the template's report-row shape; "
                "(2) summary agrees with recount (breaches, p0, ticket_count == rows); "
                "(3) task and summary match the template's top level. "
                "Check tersely — do not re-derive the data. "
                "Reply with exactly VALID, or INVALID: <reason>."
            )},
        ],
        max_tokens=2048,  # reasoning models think before answering; headroom or the answer is cut off
        **llm_kwargs,
    )
    steps.append(_llm_step(usage, {"phase": "verify", "skill_id": skill.skill_id}))
    verdict = text.strip().upper()
    if re.search(r"\bINVALID\b", verdict) or not re.search(r"\bVALID\b", verdict):
        return _outcome(False, steps, t0, fallback=f"verify rejected output: {text.strip()[:200]}")

    return _outcome(True, steps, t0, output=final)


# ─────────────────────────────────────────────────────────────────────────────
# Args, guards, assembly
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_args(
    args: dict[str, Any], bound: dict[str, Any], plan: dict[str, Any], outputs: dict[str, Any]
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in args.items():
        if value == "$fetched_ids":
            resolved[key] = [t["ticket_id"] for t in _fetched(outputs)]
        elif value == "$assignments":
            resolved[key] = _compute_assignments(plan, outputs)
        elif isinstance(value, str) and (m := re.fullmatch(r"\{\{(\w+)\}\}", value)):
            resolved[key] = bound.get(m.group(1))
        else:
            resolved[key] = value
    return resolved


def _fetched(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    for output in outputs.values():
        if isinstance(output, dict) and isinstance(output.get("tickets"), list):
            return output["tickets"]
    raise KeyError("no fetched tickets available to a later step")


def _sla_rows(outputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    for output in outputs.values():
        if isinstance(output, dict) and isinstance(output.get("sla"), list):
            return {r["ticket_id"]: r for r in output["sla"]}
    raise KeyError("no SLA evaluation available to a later step")


def _compute_assignments(plan: dict[str, Any], outputs: dict[str, Any]) -> list[dict[str, Any]]:
    """The SYSTEM rubric as code: queue from the compiled area map, priority
    from the `sla_plan_severity_v1` ladder (breached/plan/severity)."""
    queue_map: dict[str, str] = plan.get("queue_map") or {}
    sla = _sla_rows(outputs)
    assignments = []
    for ticket in sorted(_fetched(outputs), key=lambda t: t["ticket_id"]):
        row = sla[ticket["ticket_id"]]
        breached = bool(row.get("breached"))
        customer_plan = row.get("plan", "free")
        if breached and customer_plan == "enterprise":
            priority = "P0"
        elif breached or customer_plan == "enterprise":
            priority = "P1"
        elif ticket.get("reported_severity") in ("high", "urgent") or customer_plan == "team":
            priority = "P2"
        else:
            priority = "P3"
        assignments.append({
            "ticket_id": ticket["ticket_id"],
            "queue": queue_map.get(ticket.get("product_area"), ""),
            "priority": priority,
        })
    return assignments


def _check_guard(guard: str, output: Any) -> str | None:
    """Evaluate `<tool> returns <field.path> <op> <value>`; None when it holds."""
    m = _GUARD_RE.match(guard)
    if m is None:
        return f"unparseable guard {guard!r}"
    _tool, path, op, literal = m.groups()
    try:
        value: Any = output
        for part in path.split("."):
            value = len(value) if part == "length" else value[part]
    except Exception as exc:  # noqa: BLE001 — a missing field IS a guard failure
        return f"guard {guard!r} failed: cannot resolve {path!r} ({exc})"
    try:
        expected = json.loads(literal)
    except json.JSONDecodeError:
        expected = literal.strip("`'\"")
    if not _OPS[op](value, expected):
        return f"guard failed: {guard} (actual {value!r})"
    return None


def _assemble_triage(plan: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    """The final report, from tool outputs only, per the output template."""
    tickets = sorted(_fetched(outputs), key=lambda t: t["ticket_id"])
    sla = _sla_rows(outputs)
    accepted: dict[str, dict[str, Any]] = {}
    for output in outputs.values():
        if isinstance(output, dict) and isinstance(output.get("assignments"), list):
            accepted = {a["ticket_id"]: a for a in output["assignments"]}
    rows = []
    for ticket in tickets:
        tid = ticket["ticket_id"]
        rows.append({
            "ticket_id": tid,
            "queue": accepted[tid]["queue"],
            "priority": accepted[tid]["priority"],
            "sla_breach": bool(sla[tid].get("breached")),
            "draft_reply_needed": ticket.get("first_response_at") is None,
        })
    by_queue: dict[str, int] = {}
    for row in rows:
        by_queue[row["queue"]] = by_queue.get(row["queue"], 0) + 1
    return {
        "task": plan.get("task_name", "task"),
        "ticket_count": len(rows),
        "report": rows,
        "summary": {
            "breaches": sum(1 for r in rows if r["sla_breach"]),
            "p0": sum(1 for r in rows if r["priority"] == "P0"),
            "by_queue": dict(sorted(by_queue.items())),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step bookkeeping (RecordedStep.to_dict() shape) + shared markdown helpers
# ─────────────────────────────────────────────────────────────────────────────


def _llm_step(usage: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_idx": 0, "kind": "llm", "name": usage["model"], "model": usage["model"],
        "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
        "cost_usd": cost_usd(usage["model"], usage["input_tokens"], usage["output_tokens"]),
        "wall_ms": usage["wall_ms"], "ts": _now(), "args": None, "meta": meta,
    }


def _tool_step(name: str, args: dict[str, Any], wall_ms: int, skill_id: str) -> dict[str, Any]:
    return {
        "step_idx": 0, "kind": "tool", "name": name, "model": None,
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        "wall_ms": wall_ms, "ts": _now(), "args": args, "meta": {"skill_id": skill_id},
    }


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _outcome(
    ok: bool, steps: list[dict[str, Any]], t0: float, *,
    output: Any = None, fallback: str | None = None,
) -> ReplayOutcome:
    return ReplayOutcome(
        ok=ok, output=output, fallback=fallback,
        llm_calls=sum(1 for s in steps if s["kind"] == "llm"),
        tool_calls=sum(1 for s in steps if s["kind"] == "tool"),
        wall_ms=int((time.perf_counter() - t0) * 1000),
        steps=steps,
    )


def _parse_json(text: str) -> Any:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("```")[1]
        candidate = candidate[4:] if candidate.startswith("json") else candidate
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    start, end = candidate.find("{"), candidate.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(candidate[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _section(body: str, title: str) -> str:
    """The text of one `## <title>` section of a skill body."""
    m = re.search(rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    return m.group(1).strip() if m else ""


# ─────────────────────────────────────────────────────────────────────────────
# PLAN REPLAY — the directive text the proxy injects for clients we can't drive
# ─────────────────────────────────────────────────────────────────────────────


def build_plan_directive(skill: Skill, budget_tokens: int) -> str:
    """System-directive text: the prior solution's steps + guards, budget-capped.

    Over budget (len//4 tokens), the steps collapse to their title lines while
    the guards stay — a plan without its guards is not safely followable.
    """
    body = _PLAN_RE.sub("", skill.body)
    steps_txt = _section(body, "Steps")
    guards_txt = _section(body, "Guards")
    header = (
        "PLAN REPLAY: the following is a verified prior solution to this exact task. "
        "Follow it step by step; deviate only if a guard fails."
    )
    text = f"{header}\n\n## Steps\n{steps_txt}\n\n## Guards\n{guards_txt}\n"
    if len(text) // 4 > budget_tokens:
        titles = "\n".join(
            line.strip()[:80] for line in steps_txt.splitlines() if re.match(r"\s*\d+\.", line)
        )
        text = f"{header}\n\n## Steps\n{titles}\n\n## Guards\n{guards_txt}\n"
    return text


__all__ = ["MAX_WARM_LLM_CALLS", "ReplayOutcome", "build_plan_directive", "replay"]
