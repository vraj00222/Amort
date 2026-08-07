# AMORTIZE — Setup Report

Local proxy that makes AI agents cheaper to run.
Setup run started: **2026-08-07T06:29:12Z**
Host: darwin (macOS 25.5.0, arm64) · Repo: `/Users/vrajpatel/Developer/amort`

Scope of this run: scaffold + EverOS (memory) + Snowflake (ledger) + transparent passthrough
proxy + demo comparison harness. **No optimization layers** — Layer 1 (LIGHTEN) and Layer 2
(AMORTIZE) are typed stubs with `TODO(layer1)` / `TODO(layer2)` markers only.

---

## Phase log

<!-- one PASS/FAIL line appended per phase, with notes -->

### Phase 0 — Preflight — **PASS** (2026-08-07T06:29Z)
- `python3` = **3.14.6** (Homebrew) — ≥3.11 ✓. Also present: 3.11.15, 3.9.6.
- `git` = 2.47.1 ✓ · `uv` = 0.10.4 (already installed, no install needed) ✓
- Network: `https://pypi.org/simple/` → HTTP 200 ✓
- `git init` in `/Users/vrajpatel/Developer/amort` ✓ ; `SETUP_REPORT.md` created ✓
- **Decision:** project venv pinned to **CPython 3.12** (not the system 3.14) — `snowflake-connector-python`,
  `pyarrow` and `streamlit` do not all publish 3.14 wheels yet. `requires-python = ">=3.11"` in
  `pyproject.toml` keeps the package itself broad.

### Phase 1 — Repo layout — **PASS** (2026-08-07T06:31Z)
- Tree created exactly as specified: `amort/{cli,config}.py`, `amort/proxy/{server,passthrough,interceptors}.py`,
  `amort/skills/{recorder,compiler,replayer,grader,store_everos}.py`,
  `amort/ledger/{events,pricing,snowflake_writer,sqlite_writer}.py`,
  `amort/demo/{harness,report}.py` + `amort/demo/tasks/ticket_triage.py`, `amort/dashboard/app.py`,
  `scripts/{snowflake_setup.sql,smoke_proxy.py}`, `.amort/{memory,spill,skills}/`.
- `__init__.py` present in all 7 packages ✓
- `.gitignore` covers `.env`, `.amort/`, `vendor/`, `__pycache__/`, `*.pyc`, `.venv/`, `demo_report.json` ✓
- `pyproject.toml` written with deps, `[project.scripts] amort = "amort.cli:main"`, ruff config ✓
- Extra dir not in the spec: `vendor/` (holds the EverOS clone, gitignored).

### Phase 2 — Dependencies — **PASS** (2026-08-07T06:38Z)
- `uv venv --python 3.12` → CPython 3.12.12; `uv sync` installed all core deps.
- Versions: fastapi 0.141.1 · uvicorn 0.52.1 · httpx 0.28.1 · pydantic 2.13.4 · pydantic-settings 2.14.2 ·
  typer 0.27.1 · rich 15.0.0 · python-dotenv 1.2.2 · streamlit 1.61.1 · **snowflake-connector-python 4.7.1** ·
  anthropic 0.120.2 · openai 2.53.0 · tenacity 9.1.4 · ruff 0.16.1 (dev group).
- Smoke: `import fastapi, httpx, snowflake.connector, …` → **OK**.

**EverOS — install method (read from source, not memory):**
- Cloned `https://github.com/EverMind-AI/EverOS` → `vendor/everos` (repo `openapi.json` reports **1.2.3**).
- Read `QUICKSTART.md`, `CLAUDE.md`, `docs/storage_layout.md`, `docs/openapi.json` before integrating.
- Documented install methods are `pip install everos` (users) or `uv sync` from a source clone (contributors).
  **Chosen: PyPI**, installed as an *optional extra* so the base proxy stays light:
  `uv add --optional everos "everos>=1.2.2; python_version>='3.12'"` → **everos 1.2.2**.
  The `python_version` marker is required: EverOS declares `requires-python >=3.12`, and a bare
  `uv add` fails to resolve against amortize's `requires-python = ">=3.11"`. Install with
  `uv sync --extra everos`.
- Smoke: `import everos` ✓ · `from everos.entrypoints.api import *` ✓ · `uv run everos --help` lists
  `init | demo | server | cascade | config` ✓.
- **Key architectural finding:** EverOS has **no in-process library mode** — it is a service. Amortize talks to
  it over HTTP (`httpx`), so `everos` is only needed in the venv to *run* the server locally.

### Phase 3 — Env & secrets — **PASS** (2026-08-07T06:47Z)
- `.env.example` written (annotated, every key from the spec + `EVEROS_BASE_URL/AGENT_ID/APP_ID/PROJECT_ID`,
  `AMORT_DEMO_MODEL`); copied to `.env` (gitignored).
- `config.py`: `Settings(BaseSettings)` — env-var-named fields, `env_file` resolved from the repo root so
  `amort up` works from any CWD; `AMORT_ENV_FILE` overrides for tests.
- Smoke: **config loads with completely empty Snowflake creds and does not crash** ✓
  (`snowflake_configured == False`, ledger falls back to SQLite).
- **Bug found and fixed during the smoke test:** dotenv keeps a trailing comment as the *value* when the
  assignment is otherwise empty, so `ANTHROPIC_API_KEY=   # or leave empty` parsed as the literal string
  `"# or leave empty; proxy also forwards client-sent keys"`. Left unfixed, the proxy would have forwarded
  that string upstream as a credential. Two-sided fix: comments moved onto their own lines in
  `.env.example`, plus a `_blank_to_none` validator that maps blank/`#`-leading secrets to `None`.
  Verified a genuinely filled key still survives the validator.

**Values a human must fill for the booth demo:**
| Key | Needed for | If left empty |
|---|---|---|
| `SNOWFLAKE_ACCOUNT` / `_USER` / `_PASSWORD` | Snowflake ledger | auto-falls back to SQLite `.amort/amort.db` |
| `ANTHROPIC_API_KEY` | `amort demo`, proxy smoke | proxy still works when the *client* sends its own key |
| `EVEROS_API_KEY` | only when `EVEROS_MODE=cloud` | local EverOS server / local markdown store used instead |

### Phase 4 — EverOS integration — **PASS** (2026-08-07T06:45Z)
Smoke: `uv run python scripts/smoke_everos.py` → **PASS** (tier B skipped, see below).

```
memory backend : local-markdown
[1] record_case                -> ac_20260807_00000001
    markdown: amortize/default_project/agents/amortize/.cases/agent_case-2026-08-07.md
[2] search_case(near paraphrase)-> ac_20260807_00000001 score=0.224
[3] write_skill                -> skills/skill_triage_support_tickets/SKILL.md  (+ decoy skill)
[4] search_skill(paraphrase)   -> skl_smoke_triage score=0.129  (rejected the decoy ✓)
[5] search_skill(fingerprint)  -> skl_smoke_triage exact=True confident=True
[6] load_skill                 -> frontmatter round-trips task_fingerprint + tools_required
[7] fingerprint stable across a date shift ✓ / distinct for a different task ✓
[8] tier B distant paraphrase  -> SKIP — needs a live EverOS server (embeddings)
```

**EverOS APIs used** (all read from `vendor/everos/docs/openapi.json` + source, none from memory):
| API | Amortize use |
|---|---|
| `POST /api/v2/memory/add` | push a run's trajectory (`session_id` = `run_id`, timestamps epoch **ms**) |
| `POST /api/v2/memory/flush` | force extraction instead of waiting for a topic shift |
| `POST /api/v2/memory/search` | hybrid recall, `agent_id`-scoped → `agent_cases` + `agent_skills` |
| `POST /api/v2/memory/get` | listing by `memory_type` (`agent_case` / `agent_skill`) |
| `GET /health` | backend selection probe |
| on-disk markdown contract | `<app_dir>/<project_dir>/agents/<id>/{.cases,skills}/`, entry ids `ac_<YYYYMMDD>_<8-digit>`, entry markers `<!-- entry:… -->`, `**key**: value` inline + `### Section` bodies, `skills/skill_<name>/SKILL.md` |

EverOS models Cases and Skills as first-class memory kinds (`AgentCaseDailyFrontmatter`,
`AgentSkillFrontmatter`, plus `memory/strategies/extract_agent_skill.py` and
`trigger_skill_clustering.py`) — a very close fit for Layer 2. `store_everos.py` mirrors its
directory layout and frontmatter field names exactly, so files Amortize writes locally can be
indexed by an EverOS server later without translation.

**Gaps found — questions for the EverMind booth engineers:**
1. **The server will not start without LLM credentials.** Verified empirically: `everos init` +
   `everos server start` aborts in the lifespan with
   `LLMNotConfiguredError: LLM api_key and base_url is not configured` — `/health` never binds.
   There is no read-only / no-extraction mode, so *any* EverOS integration is hard-gated on a chat
   LLM + embedding + reranker key. Is a no-LLM read/index-only mode possible? This is what forced
   the local-markdown fallback.
2. **`POST /add` returns no case id** — only `{message_count, status}`. A caller cannot learn the id
   of the Case its own run produced without polling `/get` and matching on timestamp. Is there a
   supported way to get the extracted ids back (return them, or accept a client-supplied id)?
3. **Cases and Skills are read-only over HTTP.** `/get` and `/search` expose them, but there is no
   write endpoint — they only appear via LLM extraction. Amortize wants to *author* a Skill
   (compiled, verified, with guards). Is direct authoring supported, or is writing the markdown into
   the memory root and letting the cascade index it the sanctioned path?
4. **No scalar filter for a custom field.** Skill retrieval by our `task_fingerprint` has to happen
   locally; `FilterNode` covers EverOS's own fields. Can extra frontmatter keys be made filterable?
5. **Extraction is asynchronous and topic-shift-driven**, so "record a run, immediately replay it" has
   no defined latency bound. What is the expected `flush` → indexed delay?

**Known limitation (Phase 4, ours — documented not hidden):** the local backend's retrieval is
lexical (identifier-splitting + light stemming + idf-damped coverage). It correctly ranks a near
paraphrase above a decoy skill, but a paraphrase with *zero* shared content words scores ~0 — that
case needs the embedding + reranker half of EverOS's hybrid retrieval. The smoke test reports it as
SKIP rather than counting it as a pass.

### Phase 5 — Snowflake / ledger — **PASS (backend used: SQLite)** (2026-08-07T07:05Z)
Smoke: `uv run python scripts/smoke_ledger.py` → **PASS**

```
resolved claude-haiku-4-5-20251001 -> claude-haiku-4-5  $1.0/$5.0 per Mtok (cache read $0.10, write $1.25)
pricing math    : input/output/unknown-model cases OK
ledger backend  : sqlite → /Users/vrajpatel/Developer/amort/.amort/amort.db
wrote           : 1 RUN + 3 STEPS  (cost $0.0329)
SELECT COUNT(*) : RUNS=1  STEPS=3          ← the required assertion
SAVINGS view    : [('fp_smoke_ledger', 0.0329, 1)]
```

- **Backend actually used: SQLite**, because no Snowflake credentials are set. `AMORT_LEDGER=auto`
  probes `snowflake_configured` first, logs once, and falls back. Fill the three
  `SNOWFLAKE_*` values in `.env` and re-run to exercise the Snowflake path; nothing else changes.
- `scripts/snowflake_setup.sql` written verbatim from the authoritative DDL (7 statements).
  `amort snowflake-init` executes it (`--dry-run` verified: parses and lists all 7 without creds).
- `snowflake_writer.py`: batches (flush at **20 events or 2s**, whichever first), `tenacity` retry
  (3 attempts, exponential 0.5→4s) on both connect and batch execute, and on exhaustion logs **once**
  and delegates to `sqlite_writer` — *replaying the in-flight buffer* so a mid-demo wifi drop loses
  no rows. `writer.name` follows the switch so the report can never claim Snowflake dishonestly.
  `META` is inserted via `INSERT … SELECT …, PARSE_JSON(%s)` (VARIANT can't be bound in `VALUES`).
- `sqlite_writer.py`: identical column names/order to the Snowflake DDL, incl. a `SAVINGS` view
  rewritten from `IFF()` to `CASE WHEN` — the dashboard runs one query set against either backend.
- `pricing.py` + `pricing.json`: rates read from the Claude API reference at build time, **not from
  memory** — Haiku 4.5 $1/$5, Sonnet 5 $2/$10 intro (list $3/$15, intro ends 2026-08-31),
  Opus 5 / Opus 4.8 $5/$25, Fable 5 $10/$50, all per Mtok. Cache reads (0.1×) and writes
  (1.25× 5m / 2× 1h) are priced separately, so a cached prefix isn't over-billed — which matters
  because that is exactly the number Amortize claims to reduce.
  **An unknown model costs `$0.00`, never a guessed rate**, and is surfaced via `unknown_models()`
  so the dashboard says "unpriced" instead of silently under-reporting. OpenAI rates are
  deliberately left blank with a TODO (the demo drives no OpenAI model).
- Also shipped this phase: `amort/cli.py` (`up | demo | stats | skills | dash | snowflake-init |
  doctor`), all heavy imports deferred per-command.

### Phase 6 — Transparent proxy — **PASS (all three acceptance checks)** (2026-08-07T07:40Z)

**6a. Identical output** — `uv run python scripts/smoke_proxy.py` → **PASS**
```
[1] non-streaming   direct == proxied, byte-identical ✓ (same model, stop_reason, usage)
[2] streaming       4 deltas; first at 123ms, last at 488ms → incremental ✓
[3] ledger (sqlite) STEPS 6 → 8; in=41 out=23 $0.000156 492ms streamed=True sse_events=9
```
The smoke test runs against a **deterministic mock upstream speaking the real Anthropic wire
format**, and that is deliberate: against the live API the model may legitimately return different
bytes for the same prompt, so "byte-identical" would be untestable. `--live` switches to
`api.anthropic.com` and asserts structural equality instead. The streaming assertion is not just
"more than one chunk" — it requires the first and last delta to be ≥50ms apart, which a
buffer-then-replay proxy fails.

**6b. Streaming** — covered above, and separately verified with SSE `ping` events and `:` comment
lines, which Claude Code counts as liveness (it aborts a stream silent for 300s).

**6c. Real client — Claude Code v2.1.224 routed through the proxy** ✓
```
$ CLAUDE_CONFIG_DIR=… ANTHROPIC_BASE_URL=http://127.0.0.1:4100 \
  ANTHROPIC_AUTH_TOKEN=… CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
  claude -p "Reply with exactly the word: hello"
AMORTIZE_PROXY_ROUTE_OK                       ← the fixture's reply, relayed by the proxy (exit 0)
```
The request the proxy actually relayed, and the ledger row it produced:
```
model=claude-opus-5 stream=true n_tools=24 system_blocks=3 has_auth=true
anthropic-beta=claude-code-20250219,context-1m-2025-08-07,interleaved-thinking-2025-05-14,
  thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,
  mid-conversation-system-2026-04-07,effort-2025-11-24,fallback-credit-2026-06-01

run_id=27cdce2a-1a0b-4d97-a1de-04d918657110   ← Claude Code's own session id
  kind=llm model=claude-opus-5 in=100 out=5 cost=$0.000625 wall=6ms
  client=claude-code streamed=True sse_events=6 tools_offered=24 request_bytes=82,825
```
An isolated `CLAUDE_CONFIG_DIR` was used so the operator's own `~/.claude` was untouched, and the
upstream was a local fixture so the run cost nothing. **82,825 request bytes carrying 24 tool
schemas is the Layer-1 payload, measured** — that is the thing dynamic tool discovery removes.

**Protocol conformance** — `uv run python scripts/smoke_claude_code.py` → **PASS** (8 checks),
written against the two official docs, which I read rather than assumed
([llm-gateway-connect](https://code.claude.com/docs/en/llm-gateway-connect),
[llm-gateway-protocol](https://code.claude.com/docs/en/llm-gateway-protocol)):

| # | Check | Result |
|---|---|---|
| A | The docs' exact `curl` verification (`Authorization: Bearer` + `anthropic-version`) | 200, token reached upstream unchanged |
| B | `x-api-key` credential variant | 200 |
| C | `HEAD /` startup connectivity probe | 200 |
| D | `POST /v1/messages?beta=true` — the real inference path | query string preserved; `anthropic-beta` (9 values) and `anthropic-version` forwarded **unchanged** |
| D2 | `system` array shape preserved, attribution block still first | ✓ |
| E | `/v1/messages/count_tokens`, `GET /v1/models?limit=1000` (model discovery) | 200 |
| F | SSE `ping` + `:` comment keep-alives survive the relay | ✓ |
| G | `x-claude-code-session-id` → ledger `run_id` | ✓ (`client=claude-code`, `agent_id` captured) |
| H | Upstream 400 body relayed **verbatim** | ✓ (`"prompt is too long"` preserved) |

Three of those exist only because the protocol doc was read: **(D2)** the attribution block is
stripped *positionally* by `api.anthropic.com`, so a proxy that reorders or collapses the `system`
array pushes it into the prompt and the cache key — a hazard now documented in `interceptors.py`
as a hard constraint on Layer 1; **(F)** keep-alives are the only traffic during long thinking
pauses, so swallowing them makes Claude Code abort mid-answer; **(H)** Claude Code's
compact-and-retry matches on the upstream's error *wording*, so re-wrapping errors silently breaks
its recovery path.

**Not verified (needs a human at a terminal + a real key):** the interactive `/status` screen
showing the `Anthropic base URL` line. Exact steps are in README.md → *Connecting Claude Code*.

**Design notes worth carrying forward:**
- Header handling forwards **wholesale** minus hop-by-hop, never an allowlist. The protocol doc is
  explicit that `anthropic-beta` values grow every release; an allowlisting gateway breaks on the
  release that introduces the next capability.
- `content-encoding`/`content-length` are dropped from responses because httpx has already decoded
  the body — forwarding them yields truncated or garbled responses.
- Chunks are **forwarded before** they are tapped for usage, so observability can never add latency.
- Read timeout is `None`: a thinking-heavy turn can legitimately stream for minutes.
- `interceptors.py` hooks are wrapped in `safe_*` variants: an optimizer bug degrades to
  pass-through instead of 500-ing the caller.

### Phase 7 — Demo task + comparison harness — **PASS** (2026-08-07T08:05Z)
`uv run amort demo` (offline; no API key present) →

```
  A_cold  baseline/cold    29,403 tok  $0.0333  0.1s  5 llm / 4 tool
  B_cold  amortize/cold    29,403 tok  $0.0333  0.1s  5 llm / 4 tool
  A_warm  baseline/warm    29,403 tok  $0.0333  0.1s  5 llm / 4 tool
  B_warm  amortize/warm    29,403 tok  $0.0333  0.1s  5 llm / 4 tool

              amortize · ticket_triage · claude-haiku-4-5-20251001
┌─────────────────┬─────────────────────────────┬─────────────────────────────┬──────────────┐
│                 │        DIRECT (no Amortize) │            THROUGH AMORTIZE │             Δ│
├─────────────────┼─────────────────────────────┼─────────────────────────────┼──────────────┤
│First request    │ 29,403 tok · $0.033 · 126ms │ 29,403 tok · $0.033 · 129ms │            0%│
│Re-prompt (same) │ 29,403 tok · $0.033 · 130ms │ 29,403 tok · $0.033 · 125ms │ 0% · parity ✓│
└─────────────────┴─────────────────────────────┴─────────────────────────────┴──────────────┘
A cold vs B cold: parity ✓ — 120 field(s) identical
B cold vs B warm: parity ✓ — 120 field(s) identical
accuracy vs ground truth: all runs correct ✓
Warm lane fell back to the full agent: no confident skill match (Layer 2 compiles none yet)
```

**Phase 7's acceptance is the honest 0%** — Layers 1 and 2 are stubs, so routing through Amortize
must change nothing, and it doesn't. The Δ column is *computed from the measurements*, never
asserted; the harness has no code path that can produce a favourable number it did not measure.

- `demo/tasks/ticket_triage.py` — 8 tools (`fetch_tickets`, `get_customer`, `search_kb`,
  `classify`, `check_sla`, `assign_queue`, `draft_reply`, `log_resolution`) with production-shaped
  JSON Schemas (~7KB, re-sent every turn — the Layer-1 payload), over a committed 30-ticket fixture
  (`tickets.json`, seed 20260807). Every tool is a pure function of the fixture, so a difference
  between runs is a real difference and not flakiness. Final output is a structured JSON triage
  report, which is what makes parity field-exact (120 fields compared per pair).
- `demo/harness.py` — runs A-cold, B-cold, A-warm, B-warm **interleaved** (not A,A,B,B) so a warming
  network or a rate-limit backoff can't land entirely on one lane. Logs each run to the ledger with
  `lane`/`mode` set, and records each as an EverOS Case.
- `demo/report.py` — the 2×2 rich table + `demo_report.json`.
- `skills/grader.py` — real, not a stub: field-exact comparison of the structured report with three
  verdicts. **`n/a` is distinct from `✓`** — "we did not run the thing that could have broken it"
  must not read as "we verified equivalence". It also grades *accuracy* against ground truth
  separately, because two runs can agree with each other and both be wrong.
- `skills/compiler.py`, `skills/replayer.py` — typed `TODO(layer2)` stubs with the interface fixed.
  `replay()` returns a fallback rather than raising, and refuses outright to replay a `candidate`
  skill.
- **Offline mode is labelled, not hidden.** With no API key the harness runs a scripted agent over
  the same 8 tools and estimates tokens from the real serialized payload (chars/4). `simulated:
  true` is carried through the recorder, the rich panel, and `demo_report.json` — an unlabelled
  estimate on a cost dashboard is indistinguishable from a measurement. With a key set,
  `amort demo` drives the real model and Lane B routes through `amort up`.

Ledger after the demo runs: `baseline/cold 5 · baseline/warm 3 · amortize/cold 3 · amortize/warm 3`
runs; 74 `llm` + 50 `tool` steps.

### Phase 8 — Dashboard — **PASS** (2026-08-07T08:20Z)
`amort dash` → Streamlit on :8511, `HTTP 200`, `/_stcore/health` → `ok`.

Smoke: `uv run python scripts/smoke_dash.py` → **PASS**
```
metric       4 / 6 / 5 / 6 / 6 / 9 row(s)     ← runs, tokens, spend, ledger, memory, net-saved
line_chart   14 row(s) x 4 col(s)             ← the amortization curve, one series per lane/mode
bar_chart    2 row(s)                         ← cost by step kind
bar_chart    4 row(s)                         ← tool-call distribution
dataframe    x4                               ← lane rollup, SAVINGS view, step kinds, tools
charts: 3 · tables: 4 · metrics: 6 · non-empty: 3/3
```
A green HTTP 200 was **not** accepted as proof: Streamlit executes the page script per session over
a websocket, so a script that raises still serves 200. The smoke test therefore runs the real page
script and patches `DeltaGenerator` (not `st.*` — the page renders into columns, which never touch
the module) to assert every chart was handed a **non-empty** frame.

Panels: (1) cost-per-run line chart grouped by lane — the amortization curve, with a cost/tokens
toggle; (2) cumulative $ saved, read from the `SAVINGS` view; (3) cost by step kind + tool-call
distribution; (4) skills table. Every panel states *why* it is empty rather than rendering a bare
zero — an empty chart beside a "$0.00 saved" tile reads as "it saved nothing" instead of "Layer 2
is a stub, so no warm runs exist". The page also carries a standing banner saying both optimizer
layers are stubs, and surfaces any model costed at $0.00 for lack of a published rate.

*Attempted and abandoned:* a browser screenshot of the rendered page — the Chrome extension is not
connected in this environment. The headless assertion above is the substitute, and it is a stronger
check than a screenshot for "the charts have data".

### Phase 9 — README + wrap-up — **PASS** (2026-08-07T08:35Z)
`README.md` written with: one-paragraph pitch · Quickstart (3 commands + 1 env var) · ASCII
architecture diagram of the three layers · **Connecting Claude Code** (the verified steps from
Phase 6, incl. the docs' `curl` check and the `/status` lines to look for) · `amort demo` ·
Snowflake setup · EverOS setup · command table · repo layout · how to re-run every smoke test ·
and an explicit **"What is not built yet"** section.

---

## Final results

Re-ran everything from a clean shell at 2026-08-07T08:40Z:

```
smoke_everos           PASS   [tier B skipped — needs a live EverOS server]
smoke_ledger           PASS
smoke_proxy            PASS
smoke_claude_code      PASS
smoke_dash             PASS
ruff check             PASS
amort demo             PASS
```

| # | Phase | Result | Notes |
|---|---|---|---|
| 0 | Preflight | **PASS** | python 3.14.6 present; venv pinned to 3.12 for wheel coverage |
| 1 | Scaffold | **PASS** | tree exactly as specified (+ gitignored `vendor/`) |
| 2 | Deps incl. EverOS import | **PASS** | everos 1.2.2 from PyPI as an optional extra (`python_version>='3.12'` marker required) |
| 3 | Env loads | **PASS** | loads with empty Snowflake creds; dotenv comment-as-value bug found and fixed |
| 4 | EverOS record/search | **PASS** | Case recorded, recalled by near paraphrase, decoy rejected; distant paraphrase reported SKIP, not PASS |
| 5 | Ledger insert | **PASS** | **backend used: SQLite** (no Snowflake creds); 1 RUN + 3 STEPS written and counted back |
| 6 | Proxy identical-output | **PASS** | byte-identical vs direct, same model/stop_reason/usage |
| 6 | Proxy streaming | **PASS** | 4 deltas spread over 365 ms — not buffered-and-replayed |
| 6 | Claude Code routed | **PASS** | real `claude` v2.1.224 completed a task through the proxy; 8 gateway-protocol checks pass. `/status` screen unverified (needs a human + a real key) |
| 7 | `amort demo` 2×2 table | **PASS** | prints honest `0%`; parity ✓ (120 fields), accuracy ✓ |
| 8 | `amort dash` renders charts | **PASS** | 3 charts / 4 tables / 6 metrics, all non-empty |
| 9 | README complete | **PASS** | |
| — | All phases committed | **PASS** | 8 commits, `phase-N: …` |

**Backend reality check for anyone reading a number in this repo:** the ledger ran on **SQLite**,
memory ran on the **local markdown store**, and the demo ran **offline with estimated tokens** —
because no Snowflake, EverOS, or Anthropic credentials were available. Every one of those is
surfaced at runtime (`amort doctor`, the `/health` endpoint, the demo panel, `demo_report.json`,
the dashboard footer) rather than being implied away.

---

## Gaps & questions for the booth engineers

**EverMind / EverOS**
1. **The server won't start without LLM credentials** — `everos server start` aborts in the
   lifespan with `LLMNotConfiguredError`; `/health` never binds. Is a read/index-only mode possible?
   This is what forced the local-markdown fallback.
2. **`POST /api/v2/memory/add` returns no case id** (only `{message_count, status}`), so a caller
   cannot learn the id of the Case its own run produced without polling `/get` and matching on
   timestamp. Can ids be returned, or client-supplied?
3. **Cases and Skills are read-only over HTTP** — exposed by `/get` and `/search`, but only created
   by LLM extraction. Amortize wants to *author* a verified Skill with guards. Is writing markdown
   into the memory root and letting the cascade index it the sanctioned path?
4. **No scalar filter for a custom frontmatter field**, so `task_fingerprint` lookup has to happen
   locally. Can extra frontmatter keys be made filterable via `FilterNode`?
5. **Extraction is async and topic-shift-driven** — what is the expected `flush` → indexed latency?
   "Record a run, immediately look it up" currently has no defined bound.

**Snowflake**
6. Booth credentials to exercise the Snowflake path end-to-end — everything is written and
   `--dry-run` verified, but the live insert has only been exercised against SQLite.
7. Is `INSERT … SELECT …, PARSE_JSON(%s)` still the recommended way to write a `VARIANT` column
   from the Python connector under `executemany`, or is there a faster bulk path worth using at
   proxy volumes?

**Anthropic / Claude Code**
8. Everything needed was in the public gateway docs; no blockers. The one check that cannot be
   automated is the interactive `/status` screen — worth a booth demo on a laptop with a real key.

**Ours, not theirs**
9. The local retrieval fallback is lexical, so a zero-overlap paraphrase cannot match. Closing that
   needs either a live EverOS server or a local embedding model — a dependency decision, not a bug.
10. Offline demo token counts are `chars/4` estimates. With a key, `messages.count_tokens()` would
    make even the offline lane exact; worth doing before the booth.

