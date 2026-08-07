"""Layer 1 LIGHTEN — pure functions for tool-schema dieting and result spill.

Four public functions, frozen in CONTRACTS.md (used by `scripts/accept_layer1.py`
and by workstream C's offline lane):

    build_stub_tool(catalog)              -> the `amort__search_tools` tool
    resolve_search_tools(catalog, query)  -> full tool dicts matching the query
    spill_result(content)                 -> content, or a handle+preview replacement
    resolve_read_spill(handle, mode, arg) -> head|tail|grep over a spill file

No module state. All catalogue dicts are OpenAI function-calling format
(`{"type": "function", "function": {"name", "description", "parameters"}}`).
Spill files are deterministic by content (sha256 of the original string), so the
same tool result re-sent on every turn of a conversation maps to the same handle
and the same replacement text — a hard requirement, since the client re-sends
its full history each turn and the history must stay stable.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from typing import Any

from amort.config import get_settings

SEARCH_TOOL_NAME = "amort__search_tools"
READ_SPILL_TOOL_NAME = "amort__read_spill"
SYNTHETIC_TOOL_NAMES = (SEARCH_TOOL_NAME, READ_SPILL_TOOL_NAME)
SPILL_MARKER = "amort-spill"

_ID_PATTERN = re.compile(r"[A-Z]{2,5}-\d+")
_PREVIEW_CHARS = 800  # ~200 tokens each for head and tail
_MAX_LINES = 200
_MAX_CHARS = 4096


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", str(text).strip(), maxsplit=1)[0]


def _param_hint(fn: dict[str, Any]) -> str:
    """`[params: a, b?]` for flat schemas; a load-schema-first flag for nested ones.

    Flat parameters are guessable from name + context, so direct calls succeed;
    nested object/array-of-object parameters are not — a blind call fails and
    costs the client a full extra turn — so those tools are marked.
    """
    schema = fn.get("parameters") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    nested = any(
        isinstance(p, dict)
        and (
            p.get("type") == "object"
            or (
                p.get("type") == "array"
                and isinstance(p.get("items"), dict)
                and p["items"].get("type") == "object"
            )
        )
        for p in props.values()
    )
    if nested:
        # A names-only sketch of the nesting: enough shape to call directly
        # (the one discovery round-trip it avoids costs more than every stub
        # line combined — measured on the demo task), still no descriptions,
        # enums, or constraints.
        return " [params: " + ", ".join(
            _sketch(k, p, k in required) for k, p in props.items()
        ) + "]"
    if not props:
        return ""
    return " [params: " + ", ".join(k if k in required else f"{k}?" for k in props) + "]"


def _sketch(name: str, prop: dict[str, Any], required: bool) -> str:
    """`assignments(list of {ticket_id, queue, priority})` — key names only."""
    label = name if required else f"{name}?"
    if not isinstance(prop, dict):
        return label
    if prop.get("type") == "object" and prop.get("properties"):
        return f"{label}({{{', '.join(prop['properties'])}}})"
    items = prop.get("items")
    if prop.get("type") == "array" and isinstance(items, dict):
        if items.get("type") == "object" and items.get("properties"):
            return f"{label}(list of {{{', '.join(items['properties'])}}})"
        return f"{label}(list)"
    return label


def build_stub_tool(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """The `amort__search_tools` tool. The stub catalogue lives in its description."""
    lines = []
    names = []
    for tool in catalog:
        fn = tool.get("function") or {}
        names.append(str(fn.get("name", "")))
        lines.append(
            f"{names[-1]} — {_first_sentence(fn.get('description', ''))}{_param_hint(fn)}"
        )
    example = ", ".join(names[:2]) or "tool_a, tool_b"
    description = (
        "The full tool catalogue was compacted to save context. These tools exist and "
        "are directly callable by name:\n"
        + "\n".join(lines)
        + "\n\nPREFER calling a listed tool directly — do not search first when its "
        "params are flat and clear from context or your instructions. For tools "
        "marked [structured params], and whenever you are unsure, call this to load "
        "the full schema of any tool you need; you can request several at once (one "
        f'query may name multiple tools, e.g. "{example}"). Matched tools are added '
        "to your tool list."
    )
    return {
        "type": "function",
        "function": {
            "name": SEARCH_TOOL_NAME,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Tool names or a description of the capability you need.",
                    }
                },
                "required": ["query"],
            },
        },
    }


def build_read_spill_tool() -> dict[str, Any]:
    """The `amort__read_spill` tool, offered whenever a spill marker is outbound."""
    return {
        "type": "function",
        "function": {
            "name": READ_SPILL_TOOL_NAME,
            "description": (
                "Read more of a large result that was stored out of context, referenced "
                "by an amort-spill:<handle> marker. Prefer ONE grep with an alternation "
                'regex (mode="grep", arg="field_a|field_b") to pull every related field '
                "in a single call — do NOT page through the file with repeated head/tail "
                "calls. head/tail (arg = line count, default 100) are for a quick look "
                "only. Output is bounded."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "handle": {
                        "type": "string",
                        "description": "The handle from the amort-spill:<handle> marker.",
                    },
                    "mode": {"type": "string", "enum": ["head", "tail", "grep"]},
                    "arg": {
                        "type": "string",
                        "description": "Line count for head/tail; regex for grep.",
                    },
                },
                "required": ["handle", "mode"],
            },
        },
    }


def resolve_search_tools(catalog: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Substring + fuzzy match over names and descriptions; FULL tool dicts back.

    Scoring per tool: exact name-token hits weigh most, then acronym hits
    ("service level agreement" -> "sla") and difflib fuzzy name hits, then plain
    word overlap with the description. Over-matching is safe (extra schemas cost
    tokens, never correctness), so the bar is deliberately low.
    """
    q = str(query).lower()
    all_q_tokens = re.findall(r"[a-z0-9]+", q)
    q_tokens = [t for t in all_q_tokens if len(t) > 2]
    acronym = "".join(t[0] for t in all_q_tokens)

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for idx, tool in enumerate(catalog):
        fn = tool.get("function") or {}
        name = str(fn.get("name", "")).lower()
        desc_tokens = set(re.findall(r"[a-z0-9]+", str(fn.get("description", "")).lower()))
        score = 0
        if name and (name in q or name.replace("_", " ") in q):
            score += 10
        for nt in filter(None, name.split("_")):
            if nt in q_tokens:
                score += 3
            elif (len(nt) >= 3 and nt in acronym) or difflib.get_close_matches(
                nt, q_tokens, n=1, cutoff=0.8
            ):
                score += 2
        score += sum(1 for qt in q_tokens if len(qt) > 3 and qt in desc_tokens)
        if score >= 2:
            scored.append((-score, idx, tool))
    return [tool for _, _, tool in sorted(scored, key=lambda item: item[:2])]


def _short_records(content: str) -> str:
    """Compact one-line-per-record digest of a JSON array of dicts.

    Keeps only short scalar values (ids, enums, flags, small numbers) and drops
    long strings (bodies, descriptions), so a spilled list keeps its identifying
    skeleton in context and most reads of the full file become unnecessary.
    Deterministic; empty string when the content is not a list of records.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return ""
    items = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        lists = [
            v for v in data.values()
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)
        ]
        if lists:
            items = max(lists, key=len)
    if not items or len(items) < 3 or not all(isinstance(x, dict) for x in items):
        return ""
    lines = []
    for item in items:
        parts = []
        for key, value in item.items():
            rendered = json.dumps(value, default=str)
            # 26 keeps quoted ISO-8601 timestamps (22 chars) — dropping those
            # forces the model to page the spill for date-dependent fields.
            if len(rendered) <= 26:
                parts.append(f"{key}={rendered}")
        lines.append(" ".join(parts))
    out = "\n".join(lines)
    # A truncated digest defeats its purpose (the model pages the file for the
    # missing rows) — the cap is a safety net for pathological inputs only.
    if len(out) > 12000:
        out = out[:12000] + "\n… [record digest truncated]"
    return out


def _prettify(content: str) -> str:
    """Pretty-print one-line JSON so line-oriented head/tail/grep are useful."""
    if content.count("\n") >= 3:
        return content
    try:
        return json.dumps(json.loads(content), indent=1, default=str)
    except (json.JSONDecodeError, TypeError):
        return content


def spill_result(content: str) -> str:
    """Replace an oversized result with a handle + preview + id digest.

    Under the threshold, or already carrying the marker (a replacement must
    never be re-spilled): returned unchanged, same object.
    """
    settings = get_settings()
    if len(content) // 4 <= settings.amort_spill_threshold or SPILL_MARKER in content:
        return content

    handle = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    path = settings.spill_dir / f"{handle}.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_prettify(content), encoding="utf-8")

    stored = path.read_text(encoding="utf-8")
    ids = list(dict.fromkeys(_ID_PATTERN.findall(content)))
    records = _short_records(content)
    records_section = f"--- all records, long fields omitted ---\n{records}\n" if records else ""
    return (
        f"[{SPILL_MARKER}:{handle}] Large result ({len(content):,} chars, "
        f"~{len(content) // 4:,} tokens) stored out of context.\n"
        f"--- head ---\n{stored[:_PREVIEW_CHARS]}\n"
        f"--- tail ---\n{stored[-_PREVIEW_CHARS:]}\n"
        f"{records_section}"
        f"--- complete id list ---\n{' '.join(ids)}\n"
        f'Only the long fields are missing above. If you need one, prefer a single '
        f'{READ_SPILL_TOOL_NAME}(handle="{handle}", mode="grep", arg="field_a|field_b") '
        "call over paging with head/tail."
    )


def resolve_read_spill(handle: str, mode: str, arg: str) -> str:
    """head | tail | grep over a spill file. Output bounded to ~200 lines / 4KB."""
    clean = re.sub(r"[^0-9a-f]", "", str(handle).lower())[:16]  # also a path-traversal guard
    path = get_settings().spill_dir / f"{clean}.txt"
    if not clean or not path.is_file():
        return f"error: unknown spill handle {handle!r}"
    lines = path.read_text(encoding="utf-8").splitlines()

    if mode == "head":
        picked = lines[: _line_count(arg)]
    elif mode == "tail":
        picked = lines[-_line_count(arg):]
    elif mode == "grep":
        try:
            pattern = re.compile(str(arg))
        except re.error:
            pattern = re.compile(re.escape(str(arg)))
        picked = [ln for ln in lines if pattern.search(ln)][:_MAX_LINES]
        if not picked:
            return f"no lines match {arg!r} ({len(lines)} lines total)"
    else:
        return f"error: unknown mode {mode!r} (use head|tail|grep)"

    out = "\n".join(picked)
    if len(out) > _MAX_CHARS:
        out = out[:_MAX_CHARS] + "\n… [truncated — narrow the read]"
    return out


def _line_count(arg: str) -> int:
    try:
        n = int(str(arg).strip() or 100)
    except ValueError:
        n = 100
    return max(1, min(n, _MAX_LINES))


__all__ = [
    "READ_SPILL_TOOL_NAME",
    "SEARCH_TOOL_NAME",
    "SPILL_MARKER",
    "SYNTHETIC_TOOL_NAMES",
    "build_read_spill_tool",
    "build_stub_tool",
    "resolve_read_spill",
    "resolve_search_tools",
    "spill_result",
]
