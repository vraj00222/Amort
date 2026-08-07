"""Layer 1 (LIGHTEN) — the primitives that make a request smaller.

Two independent savings, both pure functions of their input so they can be
tested without a network:

* **Tool-schema dieting.** A tool-heavy agent re-sends its full JSON Schema
  catalogue on *every* turn — 1,497 tokens for the demo's 8 tools, 24 schemas in
  83 KB for the Claude Code session captured in Phase 6. `build_stub_tool()`
  collapses the catalogue to one line per tool inside the description of a single
  synthetic `amort__search_tools` tool; `resolve_search_tools()` hands back the
  FULL schema for the handful the model actually asks for.

* **Result spill.** A 200 KB tool result occupies the context window for the rest
  of the run. `spill_result()` writes it to disk and substitutes a handle, a
  head/tail preview and an id digest; `resolve_read_spill()` reads it back on
  demand.

Both halves are resolved **proxy-side** — the client never sees a synthetic tool
and never has to implement one. That is what keeps "one env var, zero code
changes" true.

Load-bearing invariants:

* **`spill_result()` is re-entrant.** It returns its own replacement unchanged.
  Re-spilling a replacement would bury the handle the model needs, one layer
  deeper on every turn.
* **`resolve_search_tools()` returns full schemas, never stubs.** The whole point
  of the round trip is that the model gets the real parameter contract for the
  tools it selected; returning the summary again would make it guess arguments.
* **Nothing here raises on bad input.** `before_request` degrades to pass-through
  on any exception (`safe_before_request`), but a primitive that throws on an odd
  catalogue entry turns a saving into a silent no-op — so unparseable entries are
  skipped, not fatal.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from amort.config import get_settings

logger = logging.getLogger("amort.proxy.lighten")

SEARCH_TOOL_NAME = "amort__search_tools"
READ_SPILL_TOOL_NAME = "amort__read_spill"

# The marker that makes a replacement recognisable — to the model, to
# `resolve_read_spill`, and to `spill_result`'s own re-entrancy check.
SPILL_MARKER = "amort-spill:"

# Stub lines stay one line each. A tool whose first sentence runs longer than
# this is truncated: the stub only has to be enough for the model to decide
# whether to ask for the real schema.
STUB_SUMMARY_CHARS = 110

# Preview sizes for a spilled result, in characters.
SPILL_HEAD_CHARS = 700
SPILL_TAIL_CHARS = 300
SPILL_DIGEST_IDS = 40

# `resolve_search_tools` never returns the whole catalogue — that would undo the
# dieting it exists to support.
MAX_SEARCH_HITS = 4
MIN_SEARCH_SCORE = 2.0

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "by",
        "with", "from", "as", "is", "are", "was", "were", "be", "been", "it",
        "its", "this", "that", "these", "those", "please", "can", "you", "i",
        "we", "our", "my", "your", "all", "any", "each", "every", "me", "need",
    }
)

# `TKT-1042`, `CUS-003`, `KB-12` — the shape of an id worth surfacing in a digest.
_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,7}-[A-Za-z0-9_]{1,16}\b")
_WORD_RE = re.compile(r"[a-z0-9]+")


def estimate_tokens(payload: Any) -> int:
    """chars/4, the same estimator the demo and the acceptance test use.

    Deliberately not a real tokenizer: Layer 1's job is to report a *ratio*
    between two payloads measured the same way, and a ratio survives a crude
    estimator. Absolute costs come from the provider's own usage numbers.
    """
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return len(text) // 4


# ─────────────────────────────────────────────────────────────────────────────
# Catalogue shape helpers — OpenAI function-calling format
# ─────────────────────────────────────────────────────────────────────────────


def _fn(tool: Any) -> dict[str, Any] | None:
    """The `function` block of an OpenAI tool dict, or None if it isn't one."""
    if not isinstance(tool, dict):
        return None
    fn = tool.get("function")
    return fn if isinstance(fn, dict) and fn.get("name") else None


def tool_name(tool: Any) -> str:
    fn = _fn(tool)
    return str(fn.get("name", "")) if fn else ""


def is_synthetic(tool: Any) -> bool:
    return tool_name(tool).startswith("amort__")


def _summary(description: str) -> str:
    """First sentence, trimmed to one line."""
    text = " ".join(str(description).split())
    if not text:
        return "(no description)"
    head = text.split(". ")[0].rstrip(".")
    if len(head) > STUB_SUMMARY_CHARS:
        head = head[: STUB_SUMMARY_CHARS - 1].rsplit(" ", 1)[0] + "…"
    return head


def stub_lines(catalog: list[dict[str, Any]]) -> list[str]:
    """`name — first sentence` for every real tool in the catalogue."""
    lines = []
    for tool in catalog:
        fn = _fn(tool)
        if fn is None or is_synthetic(tool):
            continue
        lines.append(f"{fn['name']} — {_summary(fn.get('description', ''))}")
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# A1 — tool-schema dieting
# ─────────────────────────────────────────────────────────────────────────────


def build_stub_tool(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """The single synthetic tool that replaces the whole catalogue.

    The stub catalogue lives in this tool's **description**, not in the system
    prompt: Claude Code prepends an attribution block that the upstream strips
    *positionally*, so rewriting `system` would defeat the strip and land the
    block in the prompt and the cache key. Rewrite `tools`, never `system`.
    """
    lines = stub_lines(catalog)
    description = (
        "Look up the full parameter schema for tools you want to call. "
        f"{len(lines)} tools are available, listed below by name and purpose. "
        "Their full schemas are omitted to save context. Call this tool with a "
        "short description of what you need, and the complete schemas for the "
        "matching tools will be returned, after which you can call them "
        "normally. Request everything you need in one call.\n\n"
        "Available tools:\n" + "\n".join(lines)
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
                        "description": "What you need to do, or the tool names you want.",
                    }
                },
                "required": ["query"],
            },
        },
    }


def build_read_spill_tool() -> dict[str, Any]:
    """Offered only once something has actually spilled — it costs tokens too."""
    return {
        "type": "function",
        "function": {
            "name": READ_SPILL_TOOL_NAME,
            "description": (
                "Read a tool result that was too large to inline and was stored on "
                f"disk. Its handle appears in the placeholder as {SPILL_MARKER}<handle>."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "handle": {"type": "string", "description": "Handle from the placeholder."},
                    "mode": {
                        "type": "string",
                        "enum": ["head", "tail", "grep"],
                        "description": "head/tail read from an end; grep returns matching windows.",
                    },
                    "arg": {
                        "type": "string",
                        "description": "grep: the search string. head/tail: character count.",
                    },
                },
                "required": ["handle", "mode"],
            },
        },
    }


def _query_tokens(query: str) -> list[str]:
    return [w for w in _WORD_RE.findall(str(query).lower()) if w not in _STOPWORDS]


def _acronym_hit(token: str, words: list[str]) -> bool:
    """True when `token` is the acronym of a consecutive run of `words`.

    "service level agreement" → sla, so a query written out in full still finds
    `check_sla`. Cheap, and it is exactly how people phrase these queries.
    """
    n = len(token)
    if n < 2 or n > 5:
        return False
    return any(
        "".join(w[0] for w in words[i : i + n]) == token
        for i in range(len(words) - n + 1)
    )


def _score(tool: dict[str, Any], q_tokens: list[str]) -> float:
    """How well one tool answers a query. Name matches dominate description hits."""
    fn = _fn(tool)
    if fn is None:
        return 0.0
    name = str(fn["name"]).lower()
    name_words = _WORD_RE.findall(name)
    haystack = f"{name} {fn.get('description', '')}".lower()
    hay_words = _WORD_RE.findall(haystack)

    score = 0.0
    for token in q_tokens:
        acronym = _acronym_hit(token, hay_words) or any(   # sla ← service level agreement
            _acronym_hit(w, q_tokens) for w in name_words if len(w) <= 5
        )
        if token in name or acronym:                       # substring of the name
            score += 3.0
        elif token in haystack:                            # mentioned in the description
            score += 1.0
        elif name_words and max(
            difflib.SequenceMatcher(None, token, w).ratio() for w in name_words
        ) >= 0.8:                                          # typo / inflection
            score += 2.0
    return score


def resolve_search_tools(catalog: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Full schemas for the tools that match `query` — substring, acronym, fuzzy.

    Returns the FULL tool dicts, unmodified, so the model gets the real parameter
    contract rather than the summary it already had.
    """
    q_tokens = _query_tokens(query)
    if not q_tokens:
        return []

    scored = [
        (_score(tool, q_tokens), idx, tool)
        for idx, tool in enumerate(catalog)
        if _fn(tool) is not None and not is_synthetic(tool)
    ]
    hits = [(s, i, t) for s, i, t in scored if s >= MIN_SEARCH_SCORE]
    if not hits:  # never strand the model with nothing — give it the best guess
        hits = sorted(scored, key=lambda r: (-r[0], r[1]))[:1]
        hits = [h for h in hits if h[0] > 0]
    hits.sort(key=lambda r: (-r[0], r[1]))
    return [tool for _s, _i, tool in hits[:MAX_SEARCH_HITS]]


# ─────────────────────────────────────────────────────────────────────────────
# A2 — result spill
# ─────────────────────────────────────────────────────────────────────────────


def _spill_path(handle: str) -> Path:
    return get_settings().spill_dir / f"{handle}.txt"


def _digest_ids(content: str) -> str:
    """Ids found in the payload, so the model can reason about coverage.

    Without this a spilled 30-ticket fetch tells the model only that it was
    large; with it, the model still knows which tickets came back and can batch
    the next call without reading the file at all.
    """
    seen: list[str] = []
    for match in _ID_RE.findall(content):
        if match not in seen:
            seen.append(match)
        if len(seen) >= SPILL_DIGEST_IDS:
            break
    if not seen:
        return ""
    more = "" if len(seen) < SPILL_DIGEST_IDS else " …"
    return f"ids: {', '.join(seen)}{more}\n"


def spill_result(content: str) -> str:
    """Write an oversized tool result to disk; return a handle + preview.

    Returns `content` unchanged when it is under the threshold or already a
    replacement — the second case is what makes this safe to call on every
    tool_result of every turn.
    """
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    if SPILL_MARKER in text:
        return text  # re-entrancy: never spill a replacement
    threshold = get_settings().amort_spill_threshold
    if estimate_tokens(text) <= threshold:
        return text

    handle = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]
    path = _spill_path(handle)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        # Disk trouble must not cost the model its tool result.
        logger.warning("spill write failed (%s) — inlining the result instead", exc)
        return text

    head = text[:SPILL_HEAD_CHARS]
    tail = text[-SPILL_TAIL_CHARS:] if len(text) > SPILL_HEAD_CHARS + SPILL_TAIL_CHARS else ""
    return (
        f"[{SPILL_MARKER}{handle} bytes={len(text)} tokens~={estimate_tokens(text)}]\n"
        "This result was too large to inline and is stored on disk. Read it with "
        f'{READ_SPILL_TOOL_NAME}(handle="{handle}", mode="head"|"tail"|"grep", arg=…) '
        "only if the preview below is not enough.\n"
        f"{_digest_ids(text)}"
        f"--- head ---\n{head}\n"
        + (f"--- tail ---\n{tail}\n" if tail else "")
    )


def resolve_read_spill(handle: str, mode: str = "head", arg: str = "") -> str:
    """Read a spilled result back. Modes: `head`, `tail`, `grep`."""
    path = _spill_path(str(handle).strip())
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return f"error: no spilled result for handle {handle!r}"

    if mode == "grep":
        needle = str(arg)
        if not needle:
            return "error: grep needs a search string in `arg`"
        # Spilled payloads are usually one long JSON line, so line-oriented grep
        # would return the whole file. Return windows around each hit instead.
        windows, start = [], 0
        while len(windows) < 20:
            found = text.find(needle, start)
            if found == -1:
                break
            windows.append(text[max(0, found - 120) : found + 240])
            start = found + max(1, len(needle))
        if not windows:
            return f"no match for {needle!r} in {handle}"
        return f"{len(windows)} match(es) for {needle!r}:\n" + "\n---\n".join(windows)

    try:
        size = int(arg) if str(arg).strip() else 2000
    except ValueError:
        size = 2000
    size = max(1, min(size, 20_000))
    return text[-size:] if mode == "tail" else text[:size]


__all__ = [
    "MAX_SEARCH_HITS",
    "READ_SPILL_TOOL_NAME",
    "SEARCH_TOOL_NAME",
    "SPILL_MARKER",
    "build_read_spill_tool",
    "build_stub_tool",
    "estimate_tokens",
    "is_synthetic",
    "resolve_read_spill",
    "resolve_search_tools",
    "spill_result",
    "stub_lines",
    "tool_name",
]
