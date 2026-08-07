"""EverOS adapter — the memory substrate behind Layer 2 (AMORTIZE).

Amortize needs three things from memory: write a finished run down as a **Case**,
distil repeated Cases into a **Skill**, and — on a new task — find the Skill that
already solves it. EverOS models all three natively (`agent_case` / `agent_skill`
are two of its four memory kinds), so this module is a thin adapter, not a
reimplementation.

## What EverOS actually is (read from the 1.2.x source, not from memory)

EverOS is a **service**: `everos server start`, then HTTP. There is no in-process
library mode. Business endpoints live under `/api/v2`:

| Endpoint | Used for |
|---|---|
| `POST /api/v2/memory/add` | push a run's trajectory as messages (`session_id` = our `run_id`) |
| `POST /api/v2/memory/flush` | force extraction instead of waiting for a topic shift |
| `POST /api/v2/memory/search` | hybrid (BM25 + vector + scalar) recall; returns `agent_cases` + `agent_skills` |
| `POST /api/v2/memory/get` | paginated listing by `memory_type` (`agent_case` or `agent_skill`) |
| `GET  /health` | liveness + capability probe |

Markdown is EverOS's source of truth, laid out as
`<root>/<app_dir>/<project_dir>/agents/<agent_id>/{.cases,skills}/`.

## Two backends, one interface

`EverosHttpBackend` talks to a live server. `LocalMarkdownBackend` writes the
*same* markdown layout under `AMORT_MEMORY_DIR` and retrieves with a local
lexical scorer. The local backend is not a toy stand-in for a missing dependency —
it is what makes Amortize demoable on a laptop with no EverOS keys, and its files
are byte-compatible with an EverOS memory root, so a booth machine can start a
server later and index them.

**Why the local backend always runs, even when the server is up:** EverOS's
extraction is LLM-driven and asynchronous — `POST /add` returns
`{"message_count": n, "status": "accumulated"|"extracted"}` and *no case id*. A
caller cannot learn the id of the Case its run produced without polling `/get` and
guessing by timestamp. Amortize needs a stable id synchronously (the ledger's
`RUNS.SKILL_ID` and the replay path both key off it), so `record_case()` mints a
deterministic id, writes the local markdown, and *additionally* pushes the
trajectory to EverOS for extraction + indexing. See the gap list in
SETUP_REPORT.md.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from amort.config import Settings, get_settings

logger = logging.getLogger("amort.skills.store")

# EverOS on-disk conventions, mirrored so our files are drop-in compatible.
_CASE_ENTRY_PREFIX = "ac"
_CASE_FILE_PREFIX = "agent_case"
_SEQ_DIGITS = 8
_SKILL_DIR_PREFIX = "skill_"
_SKILL_MAIN_FILENAME = "SKILL.md"

_HTTP_TIMEOUT = 10.0
# `flush` runs LLM extraction synchronously (~20s observed on a reasoning model),
# so the add path gets its own budget. The 10s default stays for health + search,
# which sit in the proxy's hot path.
_EXTRACT_TIMEOUT = 120.0
_STOPWORDS = frozenset(
    ["a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "by", "with", "from", "as", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that", "these", "those", "please", "can", "you", "i", "we", "our", "my", "your"]
)


# ─────────────────────────────────────────────────────────────────────────────
# Public data types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Skill:
    """A distilled, replayable procedure. Body is the Skill Markdown."""

    skill_id: str
    name: str
    description: str
    task_fingerprint: str
    status: Literal["candidate", "verified", "trusted"]
    body: str
    md_path: str | None = None
    source_case_ids: list[str] = field(default_factory=list)
    tools_required: list[str] = field(default_factory=list)
    parity_rate: float | None = None
    avg_warm_cost_usd: float | None = None
    confidence: float = 0.0
    maturity_score: float = 0.0

    @property
    def frontmatter(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "task_fingerprint": self.task_fingerprint,
            "status": self.status,
            "created_from_runs": self.source_case_ids,
            "tools_required": self.tools_required,
            "parity_rate": self.parity_rate,
            "avg_warm_cost_usd": self.avg_warm_cost_usd,
        }


@dataclass(frozen=True)
class SkillMatch:
    """A retrieval hit. `score` is 0..1; `exact_fingerprint` beats any score."""

    skill_id: str
    score: float
    skill: Skill
    source: Literal["everos", "local"]
    exact_fingerprint: bool = False

    @property
    def is_confident(self) -> bool:
        """Gate for the warm path. Fingerprint equality or a strong lexical hit.

        TODO(layer2): this threshold is a placeholder. Once replay + the parity
        grader exist, promote/demote on measured `parity_rate` instead of a
        constant, and require `skill.status != "candidate"` before replaying.
        """
        return self.exact_fingerprint or self.score >= 0.55


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprinting
# ─────────────────────────────────────────────────────────────────────────────


def fingerprint(system: str, user_msg: str, tool_names: list[str]) -> str:
    """Stable id for "the same task, asked again".

    Normalised hash over (system prompt, user message shape, tool catalogue).
    The user message is *shape*-normalised, not hashed verbatim: digits collapse
    to `0`, quoted literals to `""`, whitespace to single spaces, case folded.
    "triage tickets from 2026-08-01" and "triage tickets from 2026-08-05" must
    land on the same fingerprint or a Skill would never be reused across days.

    The embedding key (the human-readable half of "normalized hash + embedding
    key") is `fingerprint_query()`, which feeds EverOS's hybrid retrieval.
    """
    payload = "\n".join(
        [
            _normalize(system),
            _normalize(user_msg),
            ",".join(sorted(tool_names)),
        ]
    )
    return "fp_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def fingerprint_query(system: str, user_msg: str, tool_names: list[str]) -> str:
    """Natural-language retrieval key paired with `fingerprint()`.

    EverOS's hybrid search wants text, not a hash. Keep it short: the task ask
    plus the tool vocabulary is what discriminates one procedure from another.
    """
    tools = ", ".join(sorted(tool_names)[:12])
    return f"{user_msg.strip()[:400]} | tools: {tools}"


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[\"'`]{1,3}[^\"'`]*[\"'`]{1,3}", '""', text)
    text = re.sub(r"\d+", "0", text)
    return re.sub(r"\s+", " ", text)


# ─────────────────────────────────────────────────────────────────────────────
# Local markdown backend (EverOS-compatible layout)
# ─────────────────────────────────────────────────────────────────────────────


class LocalMarkdownBackend:
    """Markdown store under `AMORT_MEMORY_DIR`, laid out exactly like EverOS.

    Cases append to `.cases/agent_case-<YYYY-MM-DD>.md` as entry blocks delimited
    by `<!-- entry:ac_<YYYYMMDD>_<NNNNNNNN> -->`; Skills are whole-file writes to
    `skills/skill_<name>/SKILL.md`. Both carry YAML frontmatter with EverOS's
    field names, so `everos cascade` can index them without translation.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # -- cases ---------------------------------------------------------------

    def record_case(self, run: dict[str, Any]) -> str:
        cases_dir = self.settings.cases_dir
        cases_dir.mkdir(parents=True, exist_ok=True)
        today = _dt.datetime.now(_dt.UTC).date()
        path = cases_dir / f"{_CASE_FILE_PREFIX}-{today.isoformat()}.md"

        front, body = _split_markdown(path.read_text("utf-8")) if path.exists() else ({}, "")
        seq = int(front.get("entry_count", 0)) + 1
        case_id = f"{_CASE_ENTRY_PREFIX}_{today.strftime('%Y%m%d')}_{seq:0{_SEQ_DIGITS}d}"
        now = _dt.datetime.now(_dt.UTC)

        front.update(
            {
                "id": f"agent_case_log_{self.settings.everos_agent_id}_{today.isoformat()}",
                "type": "agent_case_daily",
                "file_type": "agent_case_daily",
                "schema_version": 1,
                "agent_id": self.settings.everos_agent_id,
                "app_id": self.settings.everos_app_id,
                "project_id": self.settings.everos_project_id,
                "track": "agent",
                "date": today.isoformat(),
                "entry_count": seq,
                "created_at": front.get("created_at", _iso(now)),
                "last_appended_at": _iso(now),
            }
        )
        entry = _render_entry(
            entry_id=case_id,
            inline={
                "owner_id": self.settings.everos_agent_id,
                "session_id": run.get("run_id", ""),
                "timestamp": _iso(now),
                "quality_score": run.get("quality_score", 1.0),
                "task_fingerprint": run.get("task_fingerprint", ""),
                "lane": run.get("lane", ""),
                "mode": run.get("mode", ""),
                "llm_calls": run.get("llm_calls", 0),
                "tool_calls": run.get("tool_calls", 0),
                "cost_usd": run.get("cost_usd", 0.0),
                "tools_used": run.get("tool_names", []),
            },
            sections={
                "TaskIntent": str(run.get("task_intent") or run.get("user_msg") or "").strip(),
                "Approach": _render_approach(run),
                "KeyInsight": str(run.get("key_insight") or "").strip(),
            },
        )
        path.write_text(_join_markdown(front, (body.rstrip() + "\n\n" + entry).strip() + "\n"))
        logger.debug("case.recorded", extra={"case_id": case_id, "path": str(path)})
        return case_id

    def list_cases(self) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for path in sorted(self.settings.cases_dir.glob(f"{_CASE_FILE_PREFIX}-*.md")):
            _, body = _split_markdown(path.read_text("utf-8"))
            cases.extend(_parse_entries(body))
        return cases

    # -- skills --------------------------------------------------------------

    def write_skill(self, skill: Skill) -> str:
        name = _sanitize_skill_name(skill.name)
        skill_dir = self.settings.skills_dir / f"{_SKILL_DIR_PREFIX}{name}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / _SKILL_MAIN_FILENAME
        now = _iso(_dt.datetime.now(_dt.UTC))
        front = {
            # EverOS AgentSkillFrontmatter fields
            "id": skill.skill_id,
            "type": "agent_skill",
            "schema_version": 1,
            "agent_id": self.settings.everos_agent_id,
            "app_id": self.settings.everos_app_id,
            "project_id": self.settings.everos_project_id,
            "track": "agent",
            "name": name,
            "description": skill.description,
            "confidence": skill.confidence,
            "maturity_score": skill.maturity_score,
            "source_case_ids": skill.source_case_ids,
            "created_at": now,
            "updated_at": now,
            # Amortize additions (ignored by EverOS, load-bearing for replay)
            **skill.frontmatter,
        }
        path.write_text(_join_markdown(front, skill.body.strip() + "\n"))
        return str(path)

    def iter_skills(self) -> list[Skill]:
        skills: list[Skill] = []
        for path in sorted(self.settings.skills_dir.glob(f"{_SKILL_DIR_PREFIX}*/{_SKILL_MAIN_FILENAME}")):
            front, body = _split_markdown(path.read_text("utf-8"))
            skills.append(
                Skill(
                    skill_id=str(front.get("skill_id") or front.get("id") or path.parent.name),
                    name=str(front.get("name") or path.parent.name),
                    description=str(front.get("description") or ""),
                    task_fingerprint=str(front.get("task_fingerprint") or ""),
                    status=front.get("status", "candidate"),
                    body=body,
                    md_path=str(path),
                    source_case_ids=list(front.get("created_from_runs") or front.get("source_case_ids") or []),
                    tools_required=list(front.get("tools_required") or []),
                    parity_rate=front.get("parity_rate"),
                    avg_warm_cost_usd=front.get("avg_warm_cost_usd"),
                    confidence=float(front.get("confidence") or 0.0),
                    maturity_score=float(front.get("maturity_score") or 0.0),
                )
            )
        return skills

    def search_skill(self, task_fingerprint: str, query: str) -> SkillMatch | None:
        best: SkillMatch | None = None
        for skill in self.iter_skills():
            if task_fingerprint and skill.task_fingerprint == task_fingerprint:
                return SkillMatch(skill.skill_id, 1.0, skill, "local", exact_fingerprint=True)
            score = _lexical_score(query, f"{skill.name} {skill.description} {skill.body}")
            if best is None or score > best.score:
                best = SkillMatch(skill.skill_id, score, skill, "local")
        return best if best and best.score > 0 else None

    def search_case(self, query: str) -> tuple[dict[str, Any], float] | None:
        """Nearest recorded Case. Used by the Phase-4 smoke test and by
        `distill_skill()` to gather a cluster of similar runs."""
        best: tuple[dict[str, Any], float] | None = None
        for case in self.list_cases():
            haystack = " ".join(
                [
                    case.get("sections", {}).get("TaskIntent", ""),
                    case.get("sections", {}).get("KeyInsight", ""),
                    case.get("inline", {}).get("tools_used", ""),
                ]
            )
            score = _lexical_score(query, haystack)
            if best is None or score > best[1]:
                best = (case, score)
        return best if best and best[1] > 0 else None

    def load_skill(self, skill_id: str) -> Skill | None:
        for skill in self.iter_skills():
            if skill.skill_id == skill_id:
                return skill
        return None


# ─────────────────────────────────────────────────────────────────────────────
# EverOS HTTP backend
# ─────────────────────────────────────────────────────────────────────────────


class EverosHttpBackend:
    """Client for a running EverOS server (`local` or `cloud` mode)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        headers = {"Content-Type": "application/json"}
        if self.settings.everos_api_key:
            headers["Authorization"] = f"Bearer {self.settings.everos_api_key}"
        self._client = httpx.Client(
            base_url=self.settings.everos_base_url.rstrip("/"),
            timeout=_HTTP_TIMEOUT,
            headers=headers,
        )

    def health(self) -> dict[str, Any] | None:
        try:
            resp = self._client.get("/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 — liveness probe, any failure = down
            logger.debug("everos.health.failed", extra={"error": str(exc)})
            return None

    def add_trajectory(self, run: dict[str, Any]) -> dict[str, Any] | None:
        """`POST /api/v2/memory/add` + `flush`, so extraction runs now.

        Messages are the run's own trajectory. Timestamps are epoch **ms** — the
        v2 contract; sending seconds silently changes bucketing.
        """
        messages = _run_to_messages(run, agent_id=self.settings.everos_agent_id)
        if not messages:
            return None
        body = {
            "session_id": str(run.get("run_id", ""))[:128],
            "app_id": self.settings.everos_app_id,
            "project_id": self.settings.everos_project_id,
            "messages": messages,
        }
        try:
            resp = self._client.post(
                "/api/v2/memory/add", json=body, timeout=_EXTRACT_TIMEOUT
            )
            resp.raise_for_status()
            added = resp.json()
            flush = self._client.post(
                "/api/v2/memory/flush",
                json={
                    "session_id": body["session_id"],
                    "app_id": body["app_id"],
                    "project_id": body["project_id"],
                },
                timeout=_EXTRACT_TIMEOUT,
            )
            flush.raise_for_status()
            return {"add": added.get("data", added), "flush": flush.json().get("data", {})}
        except Exception as exc:  # noqa: BLE001 — memory is best-effort, never fail a run
            logger.warning("everos.add.failed: %s", exc)
            return None

    def search(self, query: str, *, top_k: int = 5) -> dict[str, Any] | None:
        """`POST /api/v2/memory/search`, agent-scoped → cases + skills."""
        body = {
            "agent_id": self.settings.everos_agent_id,
            "app_id": self.settings.everos_app_id,
            "project_id": self.settings.everos_project_id,
            "query": query,
            "method": "hybrid",
            "top_k": top_k,
        }
        try:
            resp = self._client.post("/api/v2/memory/search", json=body)
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("everos.search.failed: %s", exc)
            return None

    def get(self, memory_type: str, *, page_size: int = 50) -> list[dict[str, Any]]:
        """`POST /api/v2/memory/get` — listing by kind (`agent_case`/`agent_skill`)."""
        body = {
            "agent_id": self.settings.everos_agent_id,
            "app_id": self.settings.everos_app_id,
            "project_id": self.settings.everos_project_id,
            "memory_type": memory_type,
            "page": 1,
            "page_size": page_size,
        }
        try:
            resp = self._client.post("/api/v2/memory/get", json=body)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return data.get(f"{memory_type}s", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("everos.get.failed: %s", exc)
            return []


# ─────────────────────────────────────────────────────────────────────────────
# Facade — the interface the rest of Amortize calls
# ─────────────────────────────────────────────────────────────────────────────


class SkillStore:
    """Local-first store that opportunistically mirrors into EverOS.

    Backend selection happens once, lazily, via `GET /health`. A server that
    disappears mid-session degrades to local-only with a single warning rather
    than raising into the request path — memory is never allowed to fail a run.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.local = LocalMarkdownBackend(self.settings)
        self._http: EverosHttpBackend | None = None
        self._probed = False
        self._health: dict[str, Any] | None = None

    @property
    def everos(self) -> EverosHttpBackend | None:
        if not self._probed:
            self._probed = True
            candidate = EverosHttpBackend(self.settings)
            self._health = candidate.health()
            if self._health is not None:
                self._http = candidate
                logger.info("everos.connected: %s", self.settings.everos_base_url)
            else:
                logger.info(
                    "everos unreachable at %s — using local markdown store at %s",
                    self.settings.everos_base_url,
                    self.settings.memory_dir,
                )
        return self._http

    @property
    def backend_name(self) -> str:
        return "everos" if self.everos is not None else "local-markdown"

    def record_case(self, run: dict[str, Any]) -> str:
        """Persist a finished run as a Case. Returns the case id.

        Always writes local markdown (synchronous, stable id) and additionally
        pushes the trajectory to EverOS for LLM extraction + hybrid indexing.
        """
        case_id = self.local.record_case(run)
        if (client := self.everos) is not None:
            result = client.add_trajectory(run)
            if result:
                logger.debug("everos.case.pushed", extra={"case_id": case_id, "result": result})
        return case_id

    def distill_skill(self, case_ids: list[str]) -> str | None:
        """Cluster Cases into a reusable Skill.

        TODO(layer2): STUB. The real implementation reads the named Cases, asks
        an LLM to abstract the shared procedure into Skill Markdown (trigger,
        parameters, ordered steps, output template, guards), writes it via
        `write_skill()`, and returns the new skill id with `status: candidate`.
        Promotion to `verified`/`trusted` is driven by the parity grader, not
        by this call. EverOS also does this natively (`extract_agent_skill` /
        `trigger_skill_clustering`) once its LLM providers are configured —
        preferring its output over ours is the intended end state.
        """
        logger.info("distill_skill stub called for %d case(s) — Layer 2 not built", len(case_ids))
        return None

    def search_skill(self, task_fingerprint: str, query: str) -> SkillMatch | None:
        """Find a Skill for this task. Exact fingerprint wins; else best hit.

        Local first (free, deterministic, and the only path that knows about
        `task_fingerprint` — EverOS has no scalar filter for a field it does not
        model), then EverOS hybrid retrieval for paraphrase-level recall.
        """
        local_match = self.local.search_skill(task_fingerprint, query)
        if local_match and local_match.exact_fingerprint:
            return local_match

        if (client := self.everos) is not None:
            data = client.search(query, top_k=5) or {}
            hits = data.get("agent_skills") or []
            if hits:
                hit = hits[0]
                skill = self.local.load_skill(str(hit.get("id"))) or Skill(
                    skill_id=str(hit.get("id")),
                    name=str(hit.get("name", "")),
                    description=str(hit.get("description", "")),
                    task_fingerprint="",
                    status="candidate",
                    body=str(hit.get("content", "")),
                    source_case_ids=list(hit.get("source_case_ids") or []),
                    confidence=float(hit.get("confidence") or 0.0),
                    maturity_score=float(hit.get("maturity_score") or 0.0),
                )
                everos_match = SkillMatch(skill.skill_id, float(hit.get("score") or 0.0), skill, "everos")
                if local_match is None or everos_match.score > local_match.score:
                    return everos_match
        return local_match

    def load_skill(self, skill_id: str) -> Skill:
        skill = self.local.load_skill(skill_id)
        if skill is None:
            raise KeyError(f"skill not found: {skill_id!r} (looked in {self.settings.skills_dir})")
        return skill

    def write_skill(self, skill: Skill) -> str:
        return self.local.write_skill(skill)

    def search_case(self, query: str) -> tuple[dict[str, Any], float] | None:
        """Nearest Case — local lexical, or EverOS hybrid when connected."""
        if (client := self.everos) is not None:
            data = client.search(query, top_k=5) or {}
            hits = data.get("agent_cases") or []
            if hits:
                return hits[0], float(hits[0].get("score") or 0.0)
        return self.local.search_case(query)


_STORE: SkillStore | None = None


def get_store() -> SkillStore:
    global _STORE
    if _STORE is None:
        _STORE = SkillStore()
    return _STORE


# --- module-level functions: the interface named in the Phase 4 spec --------


def record_case(run: dict[str, Any]) -> str:
    """Persist one finished run as a Case; returns `case_id`."""
    return get_store().record_case(run)


def distill_skill(case_ids: list[str]) -> str | None:
    """TODO(layer2): distil Cases into a Skill; returns `skill_id` or None."""
    return get_store().distill_skill(case_ids)


def search_skill(task_fingerprint: str, query: str) -> SkillMatch | None:
    """Retrieve the Skill that already solves this task, if one exists."""
    return get_store().search_skill(task_fingerprint, query)


def load_skill(skill_id: str) -> Skill:
    """Load a Skill by id. Raises `KeyError` when unknown."""
    return get_store().load_skill(skill_id)


# ─────────────────────────────────────────────────────────────────────────────
# Markdown + scoring helpers
# ─────────────────────────────────────────────────────────────────────────────


def _iso(value: _dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _split_markdown(text: str) -> tuple[dict[str, Any], str]:
    """Split `---\\nyaml\\n---\\nbody`. YAML is the flat subset EverOS emits."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    return _parse_yaml_flat(parts[1]), parts[2].lstrip("\n")


def _join_markdown(front: dict[str, Any], body: str) -> str:
    return f"---\n{_dump_yaml_flat(front)}---\n\n{body}"


def _parse_yaml_flat(text: str) -> dict[str, Any]:
    """Parse the flat `key: value` YAML subset (scalars + inline lists).

    Deliberately not PyYAML: frontmatter here is machine-written and flat, and
    a hand-rolled 20-line parser keeps `pyyaml` out of the proxy's import path.
    """
    out: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = _coerce(value.strip())
    return out


def _coerce(value: str) -> Any:
    if value in ("", "null", "~"):
        return None
    if value in ("true", "false"):
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_coerce(v.strip()) for v in inner.split(",")] if inner else []
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _dump_yaml_flat(data: dict[str, Any]) -> str:
    lines = []
    for key, value in data.items():
        if value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (list, tuple)):
            lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        elif isinstance(value, str) and (":" in value or value.strip() != value or not value):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _render_entry(
    *, entry_id: str, inline: dict[str, Any], sections: dict[str, str]
) -> str:
    """EverOS audit-form entry: marker, H2 id, `**key**: value`, `### Section`."""
    lines = [f"<!-- entry:{entry_id} -->", f"## {entry_id}", ""]
    for key, value in inline.items():
        rendered = (
            f"[{', '.join(str(v) for v in value)}]" if isinstance(value, (list, tuple)) else value
        )
        lines.append(f"**{key}**: {rendered}")
    for title, body in sections.items():
        if not body:
            continue
        lines.extend(["", f"### {title}", body.rstrip()])
    lines.append(f"<!-- /entry:{entry_id} -->")
    return "\n".join(lines)


_ENTRY_RE = re.compile(r"<!-- entry:([A-Za-z0-9_.-]+) -->(.*?)<!-- /entry:\1 -->", re.S)


def _parse_entries(body: str) -> list[dict[str, Any]]:
    entries = []
    for match in _ENTRY_RE.finditer(body):
        entry_id, block = match.group(1), match.group(2)
        inline: dict[str, str] = {}
        sections: dict[str, str] = {}
        current: str | None = None
        buffer: list[str] = []
        for line in block.splitlines():
            if line.startswith("### "):
                if current:
                    sections[current] = "\n".join(buffer).strip()
                current, buffer = line[4:].strip(), []
            elif current is not None:
                buffer.append(line)
            elif line.startswith("**") and "**: " in line:
                key, _, value = line.partition("**: ")
                inline[key.strip("*")] = value.strip()
        if current:
            sections[current] = "\n".join(buffer).strip()
        entries.append({"case_id": entry_id, "inline": inline, "sections": sections})
    return entries


def _render_approach(run: dict[str, Any]) -> str:
    """Verbatim trajectory: what the agent did, step by step."""
    steps = run.get("steps") or []
    if not steps:
        return json.dumps(run.get("trajectory", {}), indent=2)[:4000]
    lines = []
    for i, step in enumerate(steps, 1):
        kind = step.get("kind", "?")
        name = step.get("name", "?")
        args = step.get("args")
        line = f"{i}. {kind}: {name}"
        if args:
            line += f"  args: {json.dumps(args, default=str)[:300]}"
        lines.append(line)
    return "\n".join(lines)


def _run_to_messages(run: dict[str, Any], *, agent_id: str) -> list[dict[str, Any]]:
    """Trajectory → EverOS `MessageItemDTO`s (timestamps in epoch **ms**)."""
    base_ms = int(_dt.datetime.now(_dt.UTC).timestamp() * 1000)
    messages: list[dict[str, Any]] = []
    user_msg = str(run.get("user_msg") or run.get("task_intent") or "").strip()
    if user_msg:
        messages.append(
            {
                "sender_id": _sanitize_sender(run.get("user_id", "amort_user")),
                "role": "user",
                "timestamp": base_ms,
                "content": user_msg,
            }
        )
    approach = _render_approach(run)
    summary = (
        f"Completed task with {run.get('llm_calls', 0)} LLM call(s) and "
        f"{run.get('tool_calls', 0)} tool call(s) for ${run.get('cost_usd', 0.0):.4f}.\n\n"
        f"Procedure:\n{approach}"
    )
    messages.append(
        {
            "sender_id": _sanitize_sender(agent_id),
            "role": "assistant",
            "timestamp": base_ms + 1000,
            "content": summary,
        }
    )
    return messages


_SENDER_OK = re.compile(r"[^a-zA-Z0-9_.@+-]")


def _sanitize_sender(value: object) -> str:
    """EverOS enforces `^[a-zA-Z0-9_.@+-]+$` on `sender_id`."""
    cleaned = _SENDER_OK.sub("_", str(value))[:128]
    return cleaned or "amort"


def _sanitize_skill_name(name: str) -> str:
    """Snake_case, path-separator free — EverOS rejects separators in `name`."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_")
    return cleaned[:64] or "skill"


_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _tokens(text: str) -> list[str]:
    """Lower, split identifiers, drop stopwords, crudely singularise.

    Identifier splitting matters more than it looks: without it the tool name
    `fetch_tickets` is one opaque token and a query saying "tickets" scores 0
    against a Case whose whole vocabulary is tool names. camelCase is split too
    (`fetchTickets`), since tool catalogues use both conventions.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    out: list[str] = []
    for token in _SPLIT_RE.split(spaced.lower()):
        if len(token) > 1 and token not in _STOPWORDS:
            out.append(_stem(token))
    return out


def _stem(token: str) -> str:
    """Suffix-strip so `tickets`/`ticket` and `queues`/`queue` collide.

    Deliberately tiny — plural and gerund only. A full Porter stemmer would
    over-stem domain nouns (`billing` → `bill`) for no retrieval gain here.
    """
    for suffix, keep in (("ies", 3), ("ses", 2), ("s", 1), ("ing", 3), ("ed", 2)):
        if len(token) > keep + 3 and token.endswith(suffix):
            return token[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return token


def _lexical_score(query: str, document: str) -> float:
    """Length-normalised weighted overlap in 0..1.

    Stands in for EverOS's BM25 + vector + rerank fusion when no server is
    reachable. Rare terms are worth more (a crude idf via log-damped in-document
    frequency), so "triage" outweighs "tickets" appearing ten times.

    **Known limit, by construction:** this is lexical. A paraphrase that shares
    *no* content words with the Case ("sort complaints by urgency" vs "triage
    tickets into queues") scores 0 and always will — matching that needs the
    embedding + reranker half of EverOS's hybrid retrieval, which requires a
    running server with providers configured. See SETUP_REPORT.md.
    """
    q, d = _tokens(query), _tokens(document)
    if not q or not d:
        return 0.0
    doc_counts = Counter(d)
    matched = sum(1.0 / (1.0 + math.log(1 + doc_counts[t])) for t in set(q) if t in doc_counts)
    # Normalise by query length, not sqrt(query length): sqrt damping made a
    # 1-of-6-terms hit (0.41) outrank a 3-of-9-terms hit (0.39), i.e. it rewarded
    # short vague queries. Coverage keeps the ordering honest.
    return min(1.0, matched / len(set(q)))


__all__ = [
    "EverosHttpBackend",
    "LocalMarkdownBackend",
    "Skill",
    "SkillMatch",
    "SkillStore",
    "distill_skill",
    "fingerprint",
    "fingerprint_query",
    "get_store",
    "load_skill",
    "record_case",
    "search_skill",
]
