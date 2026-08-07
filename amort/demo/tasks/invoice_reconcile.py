"""Demo task: reconcile 30 invoices against 26 payments with 8 deterministic tools.

The second demo task, built to the same contract as `ticket_triage` so the
harness, ledger, grader and stage view need no changes to run it:

* **Deterministic.** Every tool is a pure function of `invoices.json`. No
  network, no clock, no randomness — a difference between two runs is a real
  difference, not flakiness.
* **Verbose, realistic tool schemas.** ~6 KB of JSON Schema sent on every turn.
  That is the Layer-1 payload; a second task means the dieting claim is measured
  against more than one catalogue shape.
* **Structured final output**, so parity is decidable field by field.

## Why the output key is `lines` and not `report`

`skills/grader.py` compares a `report` list by `REPORT_KEY = "ticket_id"` and the
four ticket-triage fields — those names are frozen and the file belongs to
Workstream B. If this task emitted `report`, the grader would look up
`ticket_id` on rows that have none, find `None` on both sides, and return
**parity ✓ having compared nothing**. A green check that proves nothing is worse
than no check.

Naming the list `lines` routes `grade()` to its `_compare_scalar` branch, which
compares the entire serialized object exactly. Stricter than the ticket path, and
it cannot pass vacuously.

## The reconciliation rules (fully specified, so the model cannot guess)

For each invoice, with `variance = paid + credit_notes − amount`:

| Condition | status | action |
|---|---|---|
| no payment received | `unpaid` | `chase` |
| `abs(variance) <= tolerance` | `matched` | `close` |
| `variance < -tolerance` | `short_paid` | `chase` |
| `variance > tolerance` | `over_paid` | `refund` |

Tolerance is the customer's, in cents, from `get_customer_terms`. A credit note
counts toward the invoice it names — two of the four short payments are fully
explained by one, which is what makes the task non-trivial: a model that ignores
credit notes gets exactly two rows wrong.
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

FIXTURE_PATH = Path(__file__).with_name("invoices.json")
TASK_NAME = "invoice_reconcile"

# Rough chars-per-token for offline estimation. Real runs use the API's own
# counts; this only ever feeds a run explicitly labelled `simulated`.
CHARS_PER_TOKEN = 4


def _fixture() -> dict[str, Any]:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


FIXTURE = _fixture()
INVOICES: list[dict[str, Any]] = FIXTURE["invoices"]
PAYMENTS: list[dict[str, Any]] = FIXTURE["payments"]
CUSTOMERS: dict[str, Any] = FIXTURE["customers"]
CREDIT_NOTES: list[dict[str, Any]] = FIXTURE["credit_notes"]

_ACTIONS = {"matched": "close", "short_paid": "chase", "over_paid": "refund", "unpaid": "chase"}


# ─────────────────────────────────────────────────────────────────────────────
# Tool catalogue — deliberately verbose, as a production agent's would be
# ─────────────────────────────────────────────────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "fetch_invoices",
        "description": (
            "Retrieve invoices from the billing ledger. Use this first: every other tool in this "
            "toolset operates on invoice ids returned here. Results are ordered by issue date, "
            "oldest first, and include the full invoice header so a follow-up fetch is never needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["current_month", "last_month", "last_quarter", "all_open"],
                    "description": "Relative window over the invoice issue date.",
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "paid", "void", "any"],
                    "description": "Filter by billing status. Defaults to 'any'.",
                },
                "customer_id": {
                    "type": "string",
                    "description": "Restrict to one customer. Omit for all customers.",
                },
                "limit": {
                    "type": "integer", "minimum": 1, "maximum": 200,
                    "description": "Maximum invoices to return. Defaults to 100.",
                },
            },
            "required": ["period"],
        },
    },
    {
        "name": "fetch_payments",
        "description": (
            "Retrieve payments received in the settlement window, across every method (ACH, wire, "
            "card). A payment carries the invoice id it was remitted against; payments whose "
            "invoice id is absent from the invoice set are unapplied cash and must be reported."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["current_month", "last_month", "last_quarter", "all"],
                    "description": "Relative window over the payment receipt date.",
                },
                "method": {
                    "type": "string",
                    "enum": ["ach", "wire", "card", "any"],
                    "description": "Restrict to one settlement method. Defaults to 'any'.",
                },
                "include_unapplied": {
                    "type": "boolean",
                    "description": "Include payments with no invoice reference. Defaults to true.",
                },
            },
            "required": ["period"],
        },
    },
    {
        "name": "get_customer_terms",
        "description": (
            "Look up the contractual billing terms behind an invoice: net payment days, settlement "
            "currency, the variance tolerance in cents below which a difference is written off "
            "automatically, and the account tier. Needed before judging any variance — an "
            "enterprise account with a 500-cent tolerance absorbs a difference that would be an "
            "exception on a zero-tolerance SMB account."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_ids": {
                    "type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Customer ids exactly as they appear on the invoices.",
                },
                "include_history": {
                    "type": "boolean",
                    "description": "Include the 12-month payment behaviour summary. Defaults to false.",
                },
            },
            "required": ["customer_ids"],
        },
    },
    {
        "name": "match_payments",
        "description": (
            "Match a batch of payments to a batch of invoices by invoice reference, returning the "
            "paid total per invoice and listing any payment that could not be applied. Accepts "
            "batches — match everything in one call rather than looping, which is both faster and "
            "cheaper."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_ids": {
                    "type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Invoice ids to reconcile.",
                },
                "strategy": {
                    "type": "string", "enum": ["reference", "amount", "fuzzy"],
                    "description": "Matching strategy. Defaults to 'reference'.",
                },
            },
            "required": ["invoice_ids"],
        },
    },
    {
        "name": "lookup_credit_notes",
        "description": (
            "Find credit notes issued against invoices. A credit note is an agreed reduction — a "
            "goodwill discount, a damaged-goods credit — and counts toward the invoice it names, "
            "so an invoice short-paid by exactly its credit note total is fully settled, not an "
            "exception. Always check before classifying a shortfall."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_ids": {
                    "type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Invoice ids to check for credits.",
                },
                "include_void": {
                    "type": "boolean",
                    "description": "Include voided credit notes. Defaults to false.",
                },
            },
            "required": ["invoice_ids"],
        },
    },
    {
        "name": "check_variance",
        "description": (
            "Compute the settlement variance for each invoice: paid total plus applicable credit "
            "notes minus the invoice amount, in cents, together with the customer tolerance that "
            "applies. A negative variance is a shortfall, a positive one an overpayment. Accepts a "
            "batch of invoice ids."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_ids": {
                    "type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Invoice ids to evaluate.",
                },
                "apply_credit_notes": {
                    "type": "boolean",
                    "description": "Count credit notes toward the paid total. Defaults to true.",
                },
                "as_of": {
                    "type": "string",
                    "description": "ISO-8601 evaluation time. Defaults to the fixture reference time.",
                },
            },
            "required": ["invoice_ids"],
        },
    },
    {
        "name": "classify_exception",
        "description": (
            "Assign a settlement status and the collections action that follows from it, for a "
            "batch of invoices whose variance has already been computed. Statuses are 'matched', "
            "'short_paid', 'over_paid' and 'unpaid'; actions are 'close', 'chase' and 'refund'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_ids": {
                    "type": "array", "items": {"type": "string"}, "minItems": 1,
                    "description": "Invoice ids to classify.",
                },
                "policy_version": {
                    "type": "string", "enum": ["v1", "v2", "latest"],
                    "description": "Collections policy revision. Defaults to 'latest'.",
                },
            },
            "required": ["invoice_ids"],
        },
    },
    {
        "name": "post_reconciliation",
        "description": (
            "Write the final disposition for a batch of invoices back to the billing ledger and "
            "return the posted summary. Call once, at the end, with every invoice — this is the "
            "step that closes the period."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dispositions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "invoice_id": {"type": "string"},
                            "status": {"type": "string"},
                            "action": {"type": "string"},
                        },
                        "required": ["invoice_id", "status", "action"],
                    },
                    "minItems": 1,
                    "description": "One entry per invoice.",
                },
                "period_label": {
                    "type": "string",
                    "description": "Human label for the closed period, e.g. '2026-07'.",
                },
            },
            "required": ["dispositions"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOLS]

SYSTEM = (
    "You are an accounts-receivable reconciliation agent. You have tools for reading invoices and "
    "payments, looking up customer terms and credit notes, computing variances, classifying "
    "exceptions, and posting the result.\n\n"
    "Procedure — call each tool at most once, batching all ids into a single call:\n"
    "1. fetch_invoices for the requested period.\n"
    "2. fetch_payments for the same period.\n"
    "3. lookup_credit_notes for every invoice.\n"
    "4. check_variance for every invoice, with credit notes applied.\n"
    "5. classify_exception for every invoice.\n"
    "6. Return the final reconciliation.\n\n"
    "Classification rules, applied per invoice with "
    "variance = paid_cents + credit_cents - amount_cents:\n"
    "  no payment received          -> status 'unpaid',     action 'chase'\n"
    "  abs(variance) <= tolerance   -> status 'matched',    action 'close'\n"
    "  variance < -tolerance        -> status 'short_paid', action 'chase'\n"
    "  variance > tolerance         -> status 'over_paid',  action 'refund'\n"
    "tolerance is that customer's tolerance_cents. Credit notes count toward the paid total.\n\n"
    "Your final message must start with '{' and be a single JSON object and nothing else — no "
    "prose, no code fence:\n"
    '{"task": "invoice_reconcile", "invoice_count": <int>, "lines": [\n'
    '  {"invoice_id": str, "status": "matched"|"short_paid"|"over_paid"|"unpaid", '
    '"variance_cents": <int>, "action": "close"|"chase"|"refund"}\n'
    '], "summary": {"matched": <int>, "exceptions": <int>, "total_variance_cents": <int>, '
    '"by_action": {<action>: <int>}}}\n'
    "Include every invoice exactly once, ordered by invoice_id ascending. Copy variance_cents "
    "verbatim from check_variance."
)

TASK_PROMPT = (
    "Reconcile all open invoices for the period against the payments received: apply any credit "
    "notes, compute the variance for every invoice, classify the exceptions, and tell me which "
    "ones to chase and which to refund."
)


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations — pure functions of the fixture
# ─────────────────────────────────────────────────────────────────────────────


def _invoice(invoice_id: str) -> dict[str, Any] | None:
    return next((i for i in INVOICES if i["invoice_id"] == invoice_id), None)


def _paid_cents(invoice_id: str) -> int | None:
    """Total remitted against an invoice, or None when nothing was received."""
    hits = [p["amount_cents"] for p in PAYMENTS if p["invoice_id"] == invoice_id]
    return sum(hits) if hits else None


def _credit_cents(invoice_id: str) -> int:
    return sum(c["amount_cents"] for c in CREDIT_NOTES if c["invoice_id"] == invoice_id)


def _tolerance(invoice: dict[str, Any]) -> int:
    return int(CUSTOMERS.get(invoice["customer_id"], {}).get("tolerance_cents", 0))


def _variance(invoice_id: str) -> tuple[int | None, int]:
    """(variance_cents, tolerance). variance is None when unpaid."""
    invoice = _invoice(invoice_id)
    if invoice is None:
        return None, 0
    paid = _paid_cents(invoice_id)
    tol = _tolerance(invoice)
    if paid is None:
        return None, tol
    return paid + _credit_cents(invoice_id) - int(invoice["amount_cents"]), tol


def _status_for(invoice_id: str) -> tuple[str, int]:
    """(status, variance_cents). An unpaid invoice reports the full amount owed."""
    variance, tol = _variance(invoice_id)
    if variance is None:
        invoice = _invoice(invoice_id)
        return "unpaid", -int(invoice["amount_cents"]) if invoice else 0
    if abs(variance) <= tol:
        return "matched", variance
    return ("short_paid" if variance < 0 else "over_paid"), variance


def execute_tool(name: str, args: dict[str, Any]) -> Any:
    """Run one mock tool. Deterministic; raises on an unknown tool."""
    if name == "fetch_invoices":
        status = args.get("status", "any")
        customer = args.get("customer_id")
        limit = int(args.get("limit", 100))
        rows = [
            i for i in INVOICES
            if (status in ("any", i["status"])) and (not customer or i["customer_id"] == customer)
        ]
        return {"period": args.get("period"), "count": len(rows[:limit]), "invoices": rows[:limit]}

    if name == "fetch_payments":
        method = args.get("method", "any")
        rows = [p for p in PAYMENTS if method in ("any", p["method"])]
        return {"period": args.get("period"), "count": len(rows), "payments": rows}

    if name == "get_customer_terms":
        out = []
        for cid in args["customer_ids"]:
            terms = CUSTOMERS.get(cid)
            if terms is None:
                out.append({"customer_id": cid, "error": "unknown customer"})
                continue
            entry = {"customer_id": cid, **terms}
            if not args.get("include_history"):
                entry.pop("tier", None)
            out.append(entry)
        return {"terms": out}

    if name == "match_payments":
        out = []
        for iid in args["invoice_ids"]:
            invoice = _invoice(iid)
            if invoice is None:
                out.append({"invoice_id": iid, "error": "unknown invoice"})
                continue
            applied = [p["payment_id"] for p in PAYMENTS if p["invoice_id"] == iid]
            out.append({
                "invoice_id": iid,
                "paid_cents": _paid_cents(iid),
                "payment_ids": applied,
                "matched": bool(applied),
            })
        unapplied = [
            p["payment_id"] for p in PAYMENTS
            if _invoice(p["invoice_id"]) is None
        ]
        return {
            "strategy": args.get("strategy", "reference"),
            "matches": out,
            "unapplied_payment_ids": unapplied,
        }

    if name == "lookup_credit_notes":
        out = [
            {"invoice_id": iid, "credit_cents": _credit_cents(iid),
             "note_ids": [c["note_id"] for c in CREDIT_NOTES if c["invoice_id"] == iid]}
            for iid in args["invoice_ids"]
        ]
        return {"credits": [row for row in out if row["credit_cents"]], "checked": len(out)}

    if name == "check_variance":
        apply_credits = args.get("apply_credit_notes", True)
        out = []
        for iid in args["invoice_ids"]:
            invoice = _invoice(iid)
            if invoice is None:
                out.append({"invoice_id": iid, "error": "unknown invoice"})
                continue
            paid = _paid_cents(iid)
            credit = _credit_cents(iid) if apply_credits else 0
            variance = None if paid is None else paid + credit - int(invoice["amount_cents"])
            out.append({
                "invoice_id": iid,
                "amount_cents": invoice["amount_cents"],
                "paid_cents": paid,
                "credit_cents": credit,
                "variance_cents": variance,
                "tolerance_cents": _tolerance(invoice),
            })
        return {"evaluated": len(out), "variances": out}

    if name == "classify_exception":
        out = []
        for iid in args["invoice_ids"]:
            if _invoice(iid) is None:
                out.append({"invoice_id": iid, "error": "unknown invoice"})
                continue
            status, variance = _status_for(iid)
            out.append({
                "invoice_id": iid, "status": status,
                "variance_cents": variance, "action": _ACTIONS[status],
            })
        return {"policy_version": args.get("policy_version", "latest"), "classifications": out}

    if name == "post_reconciliation":
        dispositions = args.get("dispositions") or []
        by_action: dict[str, int] = {}
        for entry in dispositions:
            action = str(entry.get("action", "unknown"))
            by_action[action] = by_action.get(action, 0) + 1
        return {
            "posted": len(dispositions),
            "period_label": args.get("period_label", "2026-07"),
            "by_action": by_action,
        }

    raise ValueError(f"unknown tool {name!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Ground truth
# ─────────────────────────────────────────────────────────────────────────────


def expected_report() -> dict[str, Any]:
    """The correct answer, computed from the fixture by the documented rules.

    This is what `grade_accuracy` compares a run against. It is derived here
    rather than committed as data so it can never drift from the tools.
    """
    lines = []
    for invoice in sorted(INVOICES, key=lambda i: i["invoice_id"]):
        status, variance = _status_for(invoice["invoice_id"])
        lines.append({
            "invoice_id": invoice["invoice_id"],
            "status": status,
            "variance_cents": variance,
            "action": _ACTIONS[status],
        })

    by_action: dict[str, int] = {}
    for line in lines:
        by_action[line["action"]] = by_action.get(line["action"], 0) + 1

    return {
        "task": TASK_NAME,
        "invoice_count": len(lines),
        "lines": lines,
        "summary": {
            "matched": sum(1 for line in lines if line["status"] == "matched"),
            "exceptions": sum(1 for line in lines if line["status"] != "matched"),
            "total_variance_cents": sum(int(line["variance_cents"]) for line in lines),
            "by_action": by_action,
        },
    }


def parse_report(text: str) -> dict[str, Any] | None:
    """Pull the JSON object out of a final message. Tolerant of a code fence."""
    if not text:
        return None
    body = text.strip()
    if body.startswith("```"):
        body = body.split("```")[1] if "```" in body[3:] else body[3:]
        body = body.removeprefix("json").strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# ─────────────────────────────────────────────────────────────────────────────
# Offline agent — scripted, no API key required
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
    system prompt + tool catalogue + the conversation so far. Token counts are
    estimated (`CHARS_PER_TOKEN`) and the recorder tags the run `simulated=True`,
    so no downstream surface can present these as measured.

    `lighten=True` charges for the Layer-1 stub catalogue instead of the full
    schemas — the same substitution the proxy performs on a live run, so the
    offline lane reflects Layer 1 rather than pretending it does not exist.
    """
    rec = recorder or RunRecorder(
        lane=lane, mode=mode, system=SYSTEM, user_msg=TASK_PROMPT,
        tool_names=TOOL_NAMES, model=model, simulated=True,
    )

    tool_payload: Any = TOOLS
    if lighten:
        from amort.proxy.lighten import build_stub_tool

        tool_payload = [build_stub_tool(TOOLS_OPENAI)]

    messages: list[dict[str, Any]] = [{"role": "user", "content": TASK_PROMPT}]

    def llm_turn(output_payload: Any) -> None:
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
            meta={"simulated": True},
        )
        emit(StepEvent(
            run_id=rec.run_id, lane=rec.lane, mode=rec.mode,
            task_fingerprint=rec.task_fingerprint, step_idx=step.step_idx, kind="llm",
            name=model, model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=step.cost_usd, wall_ms=wall_ms,
            meta={"simulated": True, "task": TASK_NAME},
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
        messages.append({"role": "assistant",
                         "content": [{"type": "tool_use", "name": name, "input": args}]})
        messages.append({"role": "user", "content": [{"type": "tool_result", "content": result}]})
        return result

    # The procedure the system prompt prescribes.
    llm_turn({"tool": "fetch_invoices"})
    fetched = tool_turn("fetch_invoices", {"period": "all_open", "status": "any", "limit": 100})
    ids = [i["invoice_id"] for i in fetched["invoices"]]

    llm_turn({"tool": "fetch_payments"})
    tool_turn("fetch_payments", {"period": "all", "method": "any", "include_unapplied": True})

    llm_turn({"tool": "lookup_credit_notes"})
    tool_turn("lookup_credit_notes", {"invoice_ids": ids})

    llm_turn({"tool": "check_variance"})
    tool_turn("check_variance", {"invoice_ids": ids, "apply_credit_notes": True})

    llm_turn({"tool": "classify_exception"})
    classified = tool_turn("classify_exception", {"invoice_ids": ids, "policy_version": "latest"})

    llm_turn({"tool": "post_reconciliation"})
    tool_turn("post_reconciliation", {
        "dispositions": [
            {"invoice_id": row["invoice_id"], "status": row["status"], "action": row["action"]}
            for row in classified["classifications"]
        ],
        "period_label": "2026-07",
    })

    report = expected_report()
    llm_turn(report)
    rec.finish(final_output=report)
    return report, rec


# ─────────────────────────────────────────────────────────────────────────────
# Live agent — OpenAI-compatible loop (Novita is the working demo upstream)
# ─────────────────────────────────────────────────────────────────────────────

# The same 8 tools in OpenAI function-calling form. One schema source (TOOLS),
# two wire formats — the demo must never reconcile against a different catalogue
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

    Same loop shape as `ticket_triage.run_live`: `tool_calls` carry JSON-*string*
    arguments, tool results are `role:"tool"` messages, and usage lives on
    `prompt_tokens`/`completion_tokens`. Assistant echoes are sanitized to
    `{role, content, tool_calls}` — deepseek via Novita can return extra fields
    (`reasoning_content`) that 400 when echoed back.
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
            model=model, max_tokens=8192, temperature=0,
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
            cost_usd=cost_usd(model_id, input_tokens, output_tokens, cache_read_tokens=cache_read),
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


__all__ = [
    "SYSTEM",
    "TASK_NAME",
    "TASK_PROMPT",
    "TOOLS",
    "TOOLS_OPENAI",
    "TOOL_NAMES",
    "execute_tool",
    "expected_report",
    "parse_report",
    "run_live",
    "run_offline",
]
