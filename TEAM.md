# AMORTIZE — Team Guide

*Who this is for: teammates joining the repo to contribute code, docs, demo material, or their own agents. Read this first; it tells you where the project is, where it's going today, and what's open for you to pick up.*

---

## The end goal (the pitch)

**A local proxy that makes AI agents cheaper to run.** Point any client at it with one environment variable — no code changes, no SDK swap — and Amortize:

1. **LIGHTENs** every run: strips verbose tool schemas the model doesn't need yet (dynamic tool discovery), spills oversized tool results to disk with a readable handle.
2. **AMORTIZEs** repeat runs: records every run as a Case, distils repeats into a verified Skill, and replays the skill as code — two small LLM calls instead of a full agent loop.
3. **PROVEs** it: every LLM/tool/replay/grade step lands in a Snowflake ledger (SQLite fallback) so every % we show is a measured number. **Iron rule: no fabricated numbers, ever.** If a layer underperforms, the demo shows the real number.

**Demo-day acceptance** (what "done" looks like):

```bash
amort up                                   # terminal 1 — the proxy
amort demo --task ticket_triage --stage    # terminal 2 — 2×2 comparison + projector stage view
amort dash                                 # terminal 3 — dashboard on the same ledger rows
```

Cold-vs-cold shows the Layer-1 delta; repeat-vs-repeat shows the Layer-2 delta with a parity ✓ (field-exact identical output). Then the universality beat: any client (e.g. Claude Code `/status`) pointed at the proxy with one env var.

## Where we are right now

| Piece | Status |
|---|---|
| Transparent passthrough proxy (:4000, streaming + non-streaming, Claude Code verified) | ✅ done, smoke-tested |
| Ledger: Snowflake `AMORTIZE.LEDGER` (PAT auth) with SQLite auto-fallback, pricing, SAVINGS view | ✅ done |
| Memory: EverOS server (:8000) + local markdown store, Cases + Skills, hybrid retrieval | ✅ done |
| Demo harness: 2×2 (A/B lanes × cold/warm), parity + accuracy grader, `demo_report.json` | ✅ done (honest 0% until layers land) |
| **Upstream: Novita (OpenAI-compatible), model `deepseek/deepseek-v4-flash`** | ✅ demo `--live` ported (being verified) |
| **Layer 1 (LIGHTEN)** | 🔨 in build today |
| **Layer 2 (AMORTIZE)** | 🔨 in build today |
| Stage view, dashboard polish, DX | 🔨 in build today |

Evidence for everything marked done: `SETUP_REPORT.md`. The full day plan and specs: `BUILD_SPEC.md`.

## Today's sprint (the board)

Three parallel workstreams with **strict file ownership** — do not edit outside your lane; `amort/ledger/events.py`, `amort/config.py`, `amort/ledger/pricing.py` and the ledger writers are integrator-only:

| Workstream | Owns | Delivers |
|---|---|---|
| **A — Lighten** | `amort/proxy/` | Tool-schema dieting + proxy-side `amort__search_tools` loop + result spill, measured via `meta.layer1` |
| **B — Amortize** | `amort/skills/` | Case→Skill compiler (1 LLM call), FULL REPLAY (2 LLM calls) + PLAN REPLAY, guard fallback, promotion ladder |
| **C — Showtime** | `amort/demo/`, `amort/dashboard/`, `amort/cli.py`, `README.md` | 2×2 table, projector stage view (SSE), dashboard, `amort stats`/`skills`, README |

Gates every ~45 min: passthrough smokes green → demo table consistent with ledger rows → `ruff check` clean. Acceptance tests (`scripts/accept_layer1.py`, `scripts/accept_layer2.py`) encode the headline claims: **≥60% schema-token reduction with equal output** (L1) and **≥85% cheaper warm runs with parity ✓** (L2). Cut lines if behind: PLAN-REPLAY-only → template skill → SQLite+bulk-load → terminal table.

## What YOU can pick up (open tracks, unclaimed)

Nobody owns these yet — claim one in your PR/commit message:

- **🎤 Booth speech / pitch script** — a 3-minute script that walks the three demo commands: the problem (agents re-pay for the same work every run), the cold-vs-cold beat (Layer 1), the repeat beat (Layer 2 + parity stamp), the universality beat (one env var, any client). Constraint: every number quoted must come from a real `demo_report.json` — the honest-numbers rule is the brand.
- **🎬 Video demo** — screen recording of the three terminals + the stage view; a 60–90s cut for social and a full-length backup in case live wifi dies at the booth. Record AFTER the layers merge (watch for the `day-one: demo-ready` commit).
- **🧪 A second demo task** — copy the `amort/demo/tasks/ticket_triage.py` pattern (deterministic tools over a committed fixture, verbose schemas, structured JSON output, `expected_report()` ground truth). Ideas: invoice reconciliation, log triage, PR review checklist. Register it in `TASKS` in `amort/demo/harness.py`.
- **🤖 Route YOUR agent through Amortize** — point any OpenAI-compatible client at `http://127.0.0.1:4000/v1` (or Anthropic client at `http://127.0.0.1:4000`) and report what the ledger says about your token profile. This is exactly the universality story; real third-party traffic makes the dashboard interesting.
- **📚 Docs** — README architecture diagram polish, an `ACKNOWLEDGEMENTS.md` for anything we borrow, quickstart friction reports (clone → run in under 5 minutes: file issues where it isn't).
- **📊 Dashboard / stage design** — the projector page (dark, huge type, two lanes racing) and Streamlit dashboard both welcome design passes once C's skeleton lands.

## Ground rules

1. **No fabricated numbers.** Every % anywhere must trace to ledger rows. `simulated: true` labels are load-bearing; never remove the ledger's "BACKEND USED" line.
2. **Don't touch the Snowflake quirks:** the STEPS insert stays in `SELECT … FROM VALUES` + `PARSE_JSON` form (executemany → error 252001), and `snowflake-init` keeps skipping already-existing container statements.
3. **Frozen contracts** (see `CONTRACTS.md` once committed): interceptor signatures, `StepEvent` (extend only via `meta`), Skill markdown frontmatter (extend only via new keys), `store_everos.py` signatures.
4. **Secrets stay out of git.** `.env`, `.amort/`, `vendor/`, `demo_report.json` are gitignored — keep them that way. Copy `.env.example` → `.env` and fill your own keys (Novita key for live runs; Snowflake PAT expires Aug 8).
5. `uv run ruff check amort scripts` must pass before you push. Push to `main` promptly so others can build on your work; never force-push.

## Getting started (5 minutes)

```bash
git clone git@github.com:vraj00222/Amort.git && cd Amort
uv sync                      # Python 3.12 venv + deps
cp .env.example .env         # fill NOVITA_API_KEY at minimum for live runs
uv run amort up              # proxy on :4000
uv run amort demo --task ticket_triage    # the 2×2 (offline+labelled if no key)
uv run amort doctor          # config / ledger / memory / upstream health
uv run ruff check amort scripts && uv run python scripts/smoke_proxy.py   # before you push
```

Repo map and per-command docs: `README.md`. Per-phase build evidence: `SETUP_REPORT.md`. Today's full spec: `BUILD_SPEC.md`. Build log with measured deltas: `BUILD_REPORT.md` (appears as today's merges land).

## License

MIT (see `LICENSE`).
