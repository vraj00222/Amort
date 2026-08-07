"""Demo task: triage 30 support tickets with 8 deterministic mock tools.

This is the payload the demo measures. Three properties matter:

* **Deterministic.** Every tool is a pure function of `tickets.json`. No network,
  no clock, no randomness — so a difference between two runs is a real
  difference, not flakiness. A booth demo that sometimes disagrees with itself
  proves nothing.
* **Verbose, realistic tool schemas.** The 8 tool definitions below are ~7KB of
  JSON Schema, sent on *every* turn of the agent loop. That is deliberate: it is
  the Layer-1 payload, and it is what real agents actually look like — the Claude
  Code session captured in Phase 6 sent 24 tool schemas in an 83KB request.
* **Structured final output.** The agent returns a JSON triage report, so the
  parity grader can compare field by field instead of diffing prose.

Two execution paths share one tool implementation:

    run_live()      drives a real model through an OpenAI-compatible upstream (Novita)
    run_offline()   a scripted agent that calls the same tools in a fixed order

(`run_live_anthropic` keeps the original Anthropic SDK loop intact; nothing in
today's demo depends on it.)

`run_offline` exists so the harness, the ledger, the 2x2 table and the grader can
all be exercised without an API key. Its token counts are **estimated** from the
real serialized payload (chars/4) and every number it produces is tagged
`simulated: true` all the way through to `demo_report.json` — an unlabelled
estimate on a cost dashboard is a lie.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from amort.ledger.events import StepEvent, emit
from amort.ledger.pricing import cost_usd
from amort.skills.recorder import RunRecorder

FIXTURE_PATH = Path(__file__).with_name("tickets.json")
TASK_NAME = "ticket_triage"

# Rough chars-per-token for offline estimation. Real runs use the API's own
# counts; this only ever feeds a run explicitly labelled `simulated`.
CHARS_PER_TOKEN = 4

_QUEUES = ["billing-ops", "identity", "platform-api", "web-app", "mobile", "partner-integrations"]
_AREA_TO_QUEUE = {
    "billing": "billing-ops",
    "auth": "identity",
    "api": "platform-api",
    "dashboard": "web-app",
    "mobile": "mobile",
    "integrations": "partner-integrations",
}


def _fixture() -> dict[str, Any]:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


FIXTURE = _fixture()
TICKETS: list[dict[str, Any]] = FIXTURE["tickets"]
CUSTOMERS: dict[str, Any] = FIXTURE["customers"]
KB: list[dict[str, Any]] = FIXTURE["kb"]


# ─────────────────────────────────────────────────────────────────────────────
# Tool catalogue — deliberately verbose, as a production agent's would be
# ─────────────────────────────────────────────────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "fetch_tickets",
        "description": (
            "Retrieve support tickets from the helpdesk. Use this first: every other tool in this "
            "toolset operates on ticket ids returned here. Results are ordered by creation time, "
            "oldest first, and include the full ticket body so a follow-up fetch is never needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "range": {
                    "type": "string",
                    "enum": ["today", "last_24_hours", "last_7_days", "last_30_days", "all_open"],
                    "description": "Relative window over ticket creation time.",
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "pending", "solved", "any"],
                    "description": "Filter by workflow status. Defaults to 'any'.",
                },
                "product_area": {
                    "type": "string",
                    "enum": ["billing", "auth", "api", "dashboard", "mobile", "integrations", "any"],
                    "description": "Restrict to one product area. Defaults to 'any'.",
                },
                "limit": {
                    "type": "integer", "minimum": 1, "maximum": 200,
                    "description": "Maximum tickets to return. Defaults to 100.",
                },
            },
            "required": ["range"],
        },
    },
    {
        "name": "get_customer",
        "description": (
            "Look up the customer account behind a ticket: plan, ARR, contractual SLA in hours, "
            "90-day CSAT, and how many tickets they already have open. Needed to decide priority — "
            "an enterprise account with a 4-hour SLA outranks a free account with the same symptom."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string", "pattern": "^CUS-[0-9]{3}$",
                    "description": "Customer id exactly as it appears on the ticket.",
                },
                "include_history": {
                    "type": "boolean",
                    "description": "Include the 90-day interaction summary. Defaults to false.",
                },
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "search_kb",
        "description": (
            "Search the internal knowledge base for a documented resolution. Returns scored "
            "matches with a one-paragraph summary. Use before drafting a reply so the response "
            "cites an approved article instead of improvising a fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query."},
                "product_area": {
                    "type": "string",
                    "enum": ["billing", "auth", "api", "dashboard", "mobile", "integrations", "any"],
                    "description": "Narrow to one product area. Defaults to 'any'.",
                },
                "top_k": {
                    "type": "integer", "minimum": 1, "maximum": 10,
                    "description": "Number of articles to return. Defaults to 3.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "classify",
        "description": (
            "Classify tickets into an issue category and a confidence score using the current "
            "taxonomy. Accepts a batch of ticket ids — classify all tickets in one call rather "
            "than looping, which is both faster and cheaper."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_ids": {
                    "type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Ticket ids to classify.",
                },
                "taxonomy_version": {
                    "type": "string", "enum": ["v1", "v2", "latest"],
                    "description": "Taxonomy revision. Defaults to 'latest'.",
                },
            },
            "required": ["ticket_ids"],
        },
    },
    {
        "name": "check_sla",
        "description": (
            "Evaluate each ticket against its customer's contractual SLA and report whether the "
            "first-response clock has already been breached, plus hours remaining where it has "
            "not, plus the customer's plan tier (needed to set priority). Accounts for tickets "
            "that have received no first response at all."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_ids": {
                    "type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Ticket ids to evaluate.",
                },
                "business_hours_only": {
                    "type": "boolean",
                    "description": "Count only business hours against the SLA. Defaults to false.",
                },
                "as_of": {
                    "type": "string",
                    "description": "ISO-8601 evaluation time. Defaults to the fixture's reference time.",
                },
            },
            "required": ["ticket_ids"],
        },
    },
    {
        "name": "assign_queue",
        "description": (
            "Route tickets to handling queues. Every ticket must be assigned to exactly one queue "
            "drawn from the known queue set; an unknown queue name is rejected rather than created."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "assignments": {
                    "type": "array",
                    "description": "One entry per ticket.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticket_id": {"type": "string"},
                            "queue": {"type": "string", "enum": _QUEUES},
                            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                        },
                        "required": ["ticket_id", "queue", "priority"],
                    },
                },
                "queues": {
                    "type": "array", "items": {"type": "string", "enum": _QUEUES},
                    "description": "The permitted queue set for this run.",
                },
            },
            "required": ["assignments"],
        },
    },
    {
        "name": "draft_reply",
        "description": (
            "Draft a customer-facing first response for one ticket, citing knowledge-base articles "
            "by id. Returns the draft for review; it is never sent automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Ticket to draft a reply for."},
                "tone": {
                    "type": "string", "enum": ["formal", "neutral", "warm", "apologetic"],
                    "description": "Voice for the reply. Defaults to 'neutral'.",
                },
                "kb_refs": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Knowledge-base doc ids to cite, e.g. ['KB-101'].",
                },
            },
            "required": ["ticket_id"],
        },
    },
    {
        "name": "log_resolution",
        "description": (
            "Record the triage decision on a ticket for audit and downstream reporting. Call once "
            "per ticket after it has been assigned a queue and a priority."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "outcome": {
                    "type": "string",
                    "enum": ["triaged", "escalated", "duplicate", "needs_info", "auto_resolved"],
                },
                "notes": {"type": "string", "description": "One-line rationale for the audit log."},
            },
            "required": ["ticket_id", "outcome"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOLS]

SYSTEM = (
    "You are a support triage agent for a B2B SaaS company. You have tools for reading tickets, "
    "looking up customers, searching the knowledge base, classifying, checking SLAs, assigning "
    "queues, drafting replies, and logging outcomes.\n\n"
    "Procedure — exactly four tool calls, in this order, each tool called AT MOST ONCE with all "
    "ticket ids batched (never one call per ticket):\n"
    "1. fetch_tickets for the requested window.\n"
    "2. classify every ticket in a single batched call.\n"
    "3. check_sla for every ticket in a single batched call (its result includes each "
    "customer's plan tier — you do not need get_customer).\n"
    "4. assign_queue for every ticket: the queue that matches its product area "
    "(billing→billing-ops, auth→identity, api→platform-api, dashboard→web-app, mobile→mobile, "
    "integrations→partner-integrations).\n"
    "5. Return the final triage report.\n\n"
    "Set priority with exactly this rule, using check_sla's `breached` and `plan` fields:\n"
    "  P0 = breached AND plan is enterprise\n"
    "  P1 = breached OR plan is enterprise (but not both)\n"
    "  P2 = neither, AND (reported_severity is high or urgent, OR plan is team)\n"
    "  P3 = everything else\n"
    "sla_breach is check_sla's `breached` verbatim. draft_reply_needed is true if and only if "
    "the ticket's first_response_at is null.\n\n"
    "The final message must be a single JSON object and nothing else — no prose, no code fence:\n"
    '{"task": "ticket_triage", "ticket_count": <int>, "report": [\n'
    '  {"ticket_id": str, "queue": str, "priority": "P0"|"P1"|"P2"|"P3", '
    '"sla_breach": bool, "draft_reply_needed": bool}\n'
    "], \"summary\": {\"breaches\": <int>, \"p0\": <int>, \"by_queue\": {<queue>: <int>}}}\n"
    "Include every ticket exactly once, ordered by ticket_id ascending."
)

TASK_PROMPT = (
    "Triage all open support tickets from the last 7 days: classify them, check every ticket "
    "against its SLA, and assign each one to the right queue with a priority. Flag which ones "
    "need a drafted first response."
)


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations — pure functions of the fixture
# ─────────────────────────────────────────────────────────────────────────────


def _ticket(ticket_id: str) -> dict[str, Any] | None:
    return next((t for t in TICKETS if t["ticket_id"] == ticket_id), None)


def _sla_for(ticket: dict[str, Any]) -> tuple[bool, float | None]:
    """(breached, hours_remaining). No first response with an SLA = breached."""
    customer = CUSTOMERS.get(ticket["customer_id"], {})
    sla_hours = customer.get("sla_hours")
    if sla_hours is None:
        return False, None
    if ticket["first_response_at"] is None:
        return True, 0.0
    created_h = int(ticket["created_at"][11:13])
    responded_h = int(ticket["first_response_at"][11:13])
    elapsed = float(responded_h - created_h)
    return elapsed > sla_hours, max(0.0, sla_hours - elapsed)


def _priority_for(ticket: dict[str, Any], breached: bool) -> str:
    customer = CUSTOMERS.get(ticket["customer_id"], {})
    plan = customer.get("plan", "free")
    if breached and plan == "enterprise":
        return "P0"
    if breached or plan == "enterprise":
        return "P1"
    if ticket["reported_severity"] in ("high", "urgent") or plan == "team":
        return "P2"
    return "P3"


def execute_tool(name: str, args: dict[str, Any]) -> Any:
    """Run one mock tool. Deterministic; raises on an unknown tool."""
    if name == "fetch_tickets":
        status = args.get("status", "any")
        area = args.get("product_area", "any")
        limit = int(args.get("limit", 100))
        rows = [
            t for t in TICKETS
            if (status in ("any", t["status"])) and (area in ("any", t["product_area"]))
        ]
        return {"range": args.get("range"), "count": len(rows[:limit]), "tickets": rows[:limit]}

    if name == "get_customer":
        customer = CUSTOMERS.get(args["customer_id"])
        if customer is None:
            return {"error": f"unknown customer {args['customer_id']}"}
        out = dict(customer)
        if not args.get("include_history"):
            out.pop("csat_90d", None)
        return out

    if name == "search_kb":
        area = args.get("product_area", "any")
        top_k = int(args.get("top_k", 3))
        query_terms = {w for w in str(args.get("query", "")).lower().split() if len(w) > 3}
        scored = []
        for doc in KB:
            if area not in ("any", doc["product_area"]):
                continue
            text = f"{doc['title']} {doc['summary']}".lower()
            overlap = sum(1 for term in query_terms if term in text)
            scored.append((overlap, doc))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["doc_id"]))
        return {"results": [{**doc, "score": round(score / max(1, len(query_terms)), 3)}
                            for score, doc in scored[:top_k]]}

    if name == "classify":
        out = []
        for tid in args["ticket_ids"]:
            ticket = _ticket(tid)
            if ticket is None:
                out.append({"ticket_id": tid, "error": "unknown ticket"})
                continue
            out.append({
                "ticket_id": tid,
                "category": ticket["product_area"],
                "sub_category": ticket["tags"][0],
                "confidence": round(0.72 + (len(ticket["subject"]) % 20) / 100, 2),
            })
        return {"taxonomy_version": args.get("taxonomy_version", "latest"), "classifications": out}

    if name == "check_sla":
        out = []
        for tid in args["ticket_ids"]:
            ticket = _ticket(tid)
            if ticket is None:
                out.append({"ticket_id": tid, "error": "unknown ticket"})
                continue
            breached, remaining = _sla_for(ticket)
            customer = CUSTOMERS.get(ticket["customer_id"], {})
            out.append({
                "ticket_id": tid,
                "sla_hours": customer.get("sla_hours"),
                "plan": customer.get("plan", "free"),
                "breached": breached,
                "hours_remaining": remaining,
                "first_response_at": ticket["first_response_at"],
            })
        return {"evaluated": len(out), "sla": out}

    if name == "assign_queue":
        allowed = set(args.get("queues") or _QUEUES)
        accepted, rejected = [], []
        for item in args["assignments"]:
            if item.get("queue") in allowed:
                accepted.append(item)
            else:
                rejected.append({**item, "reason": "unknown queue"})
        return {"assigned": len(accepted), "rejected": rejected, "assignments": accepted}

    if name == "draft_reply":
        ticket = _ticket(args["ticket_id"])
        if ticket is None:
            return {"error": f"unknown ticket {args['ticket_id']}"}
        refs = args.get("kb_refs") or []
        return {
            "ticket_id": ticket["ticket_id"],
            "tone": args.get("tone", "neutral"),
            "draft": (
                f"Hi — thanks for reporting \"{ticket['subject']}\". We've reproduced the issue and "
                f"routed it to our {_AREA_TO_QUEUE[ticket['product_area']]} team. "
                + (f"See {', '.join(refs)} for the documented workaround. " if refs else "")
                + "We'll follow up with an update shortly."
            ),
            "kb_refs": refs,
        }

    if name == "log_resolution":
        return {"ticket_id": args["ticket_id"], "outcome": args["outcome"], "logged": True}

    raise KeyError(f"unknown tool: {name}")


# ─────────────────────────────────────────────────────────────────────────────
# The expected report — what a correct run produces
# ─────────────────────────────────────────────────────────────────────────────


def expected_report() -> dict[str, Any]:
    """The ground-truth triage report, computed straight from the fixture.

    Used by the grader as an accuracy reference, separately from parity (which
    compares two runs to each other). A warm run that matches the cold run but
    both are wrong is parity ✓ / accuracy ✗, and the demo should be able to say so.
    """
    rows = []
    for ticket in sorted(TICKETS, key=lambda t: t["ticket_id"]):
        breached, _ = _sla_for(ticket)
        rows.append({
            "ticket_id": ticket["ticket_id"],
            "queue": _AREA_TO_QUEUE[ticket["product_area"]],
            "priority": _priority_for(ticket, breached),
            "sla_breach": breached,
            "draft_reply_needed": ticket["first_response_at"] is None,
        })
    by_queue: dict[str, int] = {}
    for row in rows:
        by_queue[row["queue"]] = by_queue.get(row["queue"], 0) + 1
    return {
        "task": TASK_NAME,
        "ticket_count": len(rows),
        "report": rows,
        "summary": {
            "breaches": sum(1 for r in rows if r["sla_breach"]),
            "p0": sum(1 for r in rows if r["priority"] == "P0"),
            "by_queue": dict(sorted(by_queue.items())),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Offline agent — scripted, no model, estimated tokens
# ─────────────────────────────────────────────────────────────────────────────


def _estimate_tokens(payload: Any) -> int:
    return math.ceil(len(json.dumps(payload, default=str)) / CHARS_PER_TOKEN)


def run_offline(
    *,
    lane: str,
    mode: str,
    model: str,
    recorder: RunRecorder | None = None,
    lighten: bool = False,
) -> tuple[dict[str, Any], RunRecorder]:
    """A scripted agent that calls the real tools in the documented order.

    Every LLM "call" is charged for the payload it would actually have carried:
    system prompt + full tool catalogue + the conversation so far. Token counts
    are estimated (`CHARS_PER_TOKEN`), and the recorder tags the run
    `simulated=True` so no downstream surface can present these as measured.

    `lighten` is the Layer-1 switch: when Workstream A's stub builder is
    present, llm turns are charged for the stub catalogue (one synthetic
    `search_tools` tool) instead of the full TOOLS payload. Until it merges,
    the full catalogue is charged and the llm steps say so in `meta`.
    """
    rec = recorder or RunRecorder(
        lane=lane, mode=mode, system=SYSTEM, user_msg=TASK_PROMPT,
        tool_names=TOOL_NAMES, model=model, simulated=True,
    )

    tool_payload: Any = TOOLS
    lighten_note: str | None = None
    if lighten:
        try:
            from amort.proxy.lighten import build_stub_tool

            tool_payload = [build_stub_tool(TOOLS_OPENAI)]
        except ImportError:
            lighten_note = (
                "lighten requested but amort.proxy.lighten is not merged yet — "
                "charged the full catalogue"
            )
    llm_meta: dict[str, Any] = {"simulated": True, "lighten": lighten and not lighten_note}
    if lighten_note:
        llm_meta["lighten_note"] = lighten_note
    messages: list[dict[str, Any]] = [{"role": "user", "content": TASK_PROMPT}]

    def llm_turn(output_payload: Any) -> None:
        """Charge one model call for the context it would carry."""
        started = time.perf_counter()
        input_tokens = _estimate_tokens([SYSTEM, tool_payload, messages])
        output_tokens = _estimate_tokens(output_payload)
        time.sleep(0.02)  # a turn is not free; keep wall-clock non-degenerate
        wall_ms = int((time.perf_counter() - started) * 1000)
        step = rec.llm_step(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd(model, input_tokens, output_tokens),
            wall_ms=wall_ms,
            meta=dict(llm_meta),
        )
        emit(StepEvent(
            run_id=rec.run_id, lane=rec.lane, mode=rec.mode,
            task_fingerprint=rec.task_fingerprint, step_idx=step.step_idx, kind="llm",
            name=model, model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=step.cost_usd, wall_ms=wall_ms, meta={**llm_meta, "task": TASK_NAME},
        ))

    def tool_turn(name: str, args: dict[str, Any]) -> Any:
        started = time.perf_counter()
        result = execute_tool(name, args)
        wall_ms = int((time.perf_counter() - started) * 1000)
        step = rec.tool_step(name, args=args, output=result, wall_ms=wall_ms)
        emit(StepEvent(
            run_id=rec.run_id, lane=rec.lane, mode=rec.mode,
            task_fingerprint=rec.task_fingerprint, step_idx=step.step_idx, kind="tool",
            name=name, wall_ms=wall_ms,
            meta={"simulated": True, "task": TASK_NAME,
                  "result_bytes": len(json.dumps(result, default=str))},
        ))
        messages.append({"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": args}]})
        messages.append({"role": "user", "content": [{"type": "tool_result", "content": result}]})
        return result

    # The procedure the system prompt prescribes.
    llm_turn({"tool": "fetch_tickets"})
    fetched = tool_turn("fetch_tickets", {"range": "last_7_days", "status": "any", "limit": 100})
    ids = [t["ticket_id"] for t in fetched["tickets"]]

    llm_turn({"tool": "classify"})
    tool_turn("classify", {"ticket_ids": ids, "taxonomy_version": "latest"})

    llm_turn({"tool": "check_sla"})
    sla = tool_turn("check_sla", {"ticket_ids": ids, "business_hours_only": False})
    breached = {row["ticket_id"] for row in sla["sla"] if row.get("breached")}

    llm_turn({"tool": "assign_queue"})
    assignments = []
    for ticket in sorted(fetched["tickets"], key=lambda t: t["ticket_id"]):
        assignments.append({
            "ticket_id": ticket["ticket_id"],
            "queue": _AREA_TO_QUEUE[ticket["product_area"]],
            "priority": _priority_for(ticket, ticket["ticket_id"] in breached),
        })
    tool_turn("assign_queue", {"assignments": assignments, "queues": _QUEUES})

    report = expected_report()
    llm_turn(report)
    rec.finish(final_output=report)
    return report, rec


# ─────────────────────────────────────────────────────────────────────────────
# Live agent — OpenAI-compatible loop (Novita is the working demo upstream)
# ─────────────────────────────────────────────────────────────────────────────

# The same 8 tools in OpenAI function-calling form. One schema source (TOOLS),
# two wire formats — the demo must never triage against a different catalogue
# than the one Layer 1 diets.
TOOLS_OPENAI: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOLS
]


def run_live(
    *,
    lane: str,
    mode: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    max_turns: int = 12,
    recorder: RunRecorder | None = None,
) -> tuple[dict[str, Any], RunRecorder]:
    """Drive the task against an OpenAI-compatible upstream (Novita).

    Same loop shape as `run_live_anthropic`, different wire format:
    `tool_calls` carry JSON-*string* arguments, tool results are `role:"tool"`
    messages, and usage lives on `prompt_tokens`/`completion_tokens`. Assistant
    echoes are sanitized to `{role, content, tool_calls}` — deepseek via Novita
    can return extra fields (`reasoning_content`) that 400 when echoed back.
    """
    from openai import OpenAI

    rec = recorder or RunRecorder(
        lane=lane, mode=mode, system=SYSTEM, user_msg=TASK_PROMPT,
        tool_names=TOOL_NAMES, model=model,
    )
    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=2, timeout=600.0)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": TASK_PROMPT},
    ]
    final_text = ""

    for _turn in range(max_turns):
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=model, max_tokens=8192, temperature=0, seed=20260807,
            tools=TOOLS_OPENAI, messages=messages,
        )
        wall_ms = int((time.perf_counter() - started) * 1000)
        usage = response.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cache_read = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        model_id = response.model or model
        choice = response.choices[0]
        step = rec.llm_step(
            model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd(
                model_id, input_tokens, output_tokens, cache_read_tokens=cache_read,
            ),
            wall_ms=wall_ms,
            meta={"stop_reason": choice.finish_reason, "cache_read_tokens": cache_read},
        )
        emit(StepEvent(
            run_id=rec.run_id, lane=rec.lane, mode=rec.mode,
            task_fingerprint=rec.task_fingerprint, step_idx=step.step_idx, kind="llm",
            name=model_id, model=model_id,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=step.cost_usd, wall_ms=wall_ms,
            meta={"task": TASK_NAME, "stop_reason": choice.finish_reason,
                  "cache_read_tokens": cache_read},
        ))

        tool_calls = choice.message.tool_calls or []
        echo: dict[str, Any] = {"role": "assistant", "content": choice.message.content or ""}
        if tool_calls:
            echo["tool_calls"] = [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in tool_calls
            ]
        messages.append(echo)
        if not tool_calls:
            final_text = choice.message.content or ""
            break

        for call in tool_calls:
            started = time.perf_counter()
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                output = execute_tool(call.function.name, args)
                is_error = False
            except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
                output, is_error = {"error": str(exc)}, True
            wall_ms = int((time.perf_counter() - started) * 1000)
            tstep = rec.tool_step(call.function.name, args=args, output=output, wall_ms=wall_ms)
            emit(StepEvent(
                run_id=rec.run_id, lane=rec.lane, mode=rec.mode,
                task_fingerprint=rec.task_fingerprint, step_idx=tstep.step_idx, kind="tool",
                name=call.function.name, wall_ms=wall_ms,
                meta={"task": TASK_NAME, "is_error": is_error,
                      "result_bytes": len(json.dumps(output, default=str))},
            ))
            messages.append({
                "role": "tool", "tool_call_id": call.id,
                "content": json.dumps(output, default=str),
            })

    report = parse_report(final_text)
    if report is None:
        rec.fail(f"model did not return a parseable JSON report (got {final_text[:200]!r})")
        report = {"task": TASK_NAME, "error": "unparseable", "raw": final_text[:2000]}
    rec.finish(final_output=report)
    return report, rec


# ─────────────────────────────────────────────────────────────────────────────
# Live agent — the Anthropic SDK loop (kept intact; today's demo does not use it)
# ─────────────────────────────────────────────────────────────────────────────


def run_live_anthropic(
    *,
    lane: str,
    mode: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    max_turns: int = 12,
    recorder: RunRecorder | None = None,
) -> tuple[dict[str, Any], RunRecorder]:
    """Drive the task with a real model. `base_url=None` talks to the provider."""
    import anthropic

    rec = recorder or RunRecorder(
        lane=lane, mode=mode, system=SYSTEM, user_msg=TASK_PROMPT,
        tool_names=TOOL_NAMES, model=model,
    )
    client = anthropic.Anthropic(
        api_key=api_key, base_url=base_url, max_retries=2, timeout=600.0
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": TASK_PROMPT}]
    final_text = ""

    for _turn in range(max_turns):
        started = time.perf_counter()
        response = client.messages.create(
            model=model, max_tokens=8192, system=SYSTEM, tools=TOOLS, messages=messages,
        )
        wall_ms = int((time.perf_counter() - started) * 1000)
        usage = response.usage
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        step = rec.llm_step(
            response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost_usd(
                response.model, usage.input_tokens, usage.output_tokens,
                cache_read_tokens=cache_read, cache_write_tokens=cache_write,
            ),
            wall_ms=wall_ms,
            meta={"stop_reason": response.stop_reason,
                  "cache_read_tokens": cache_read, "cache_write_tokens": cache_write},
        )
        emit(StepEvent(
            run_id=rec.run_id, lane=rec.lane, mode=rec.mode,
            task_fingerprint=rec.task_fingerprint, step_idx=step.step_idx, kind="llm",
            name=response.model, model=response.model,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cost_usd=step.cost_usd, wall_ms=wall_ms,
            meta={"task": TASK_NAME, "stop_reason": response.stop_reason,
                  "cache_read_tokens": cache_read, "cache_write_tokens": cache_write},
        ))

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            final_text = "".join(b.text for b in response.content if b.type == "text")
            break

        results = []
        for block in tool_uses:
            started = time.perf_counter()
            try:
                output = execute_tool(block.name, dict(block.input))
                is_error = False
            except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
                output, is_error = {"error": str(exc)}, True
            wall_ms = int((time.perf_counter() - started) * 1000)
            tstep = rec.tool_step(block.name, args=dict(block.input), output=output, wall_ms=wall_ms)
            emit(StepEvent(
                run_id=rec.run_id, lane=rec.lane, mode=rec.mode,
                task_fingerprint=rec.task_fingerprint, step_idx=tstep.step_idx, kind="tool",
                name=block.name, wall_ms=wall_ms,
                meta={"task": TASK_NAME, "is_error": is_error,
                      "result_bytes": len(json.dumps(output, default=str))},
            ))
            results.append({
                "type": "tool_result", "tool_use_id": block.id,
                "content": json.dumps(output, default=str), "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    report = parse_report(final_text)
    if report is None:
        rec.fail(f"model did not return a parseable JSON report (got {final_text[:200]!r})")
        report = {"task": TASK_NAME, "error": "unparseable", "raw": final_text[:2000]}
    rec.finish(final_output=report)
    return report, rec


def parse_report(text: str) -> dict[str, Any] | None:
    """Extract the JSON report, tolerating a code fence or surrounding prose."""
    if not text:
        return None
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
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


__all__ = [
    "CUSTOMERS",
    "KB",
    "SYSTEM",
    "TASK_NAME",
    "TASK_PROMPT",
    "TICKETS",
    "TOOLS",
    "TOOLS_OPENAI",
    "TOOL_NAMES",
    "execute_tool",
    "expected_report",
    "parse_report",
    "run_live",
    "run_live_anthropic",
    "run_offline",
]
