# amortize

**A local proxy that makes AI agents cheaper to run.** Point any client at it with one
environment variable — no code changes, no SDK swap, no wrapper — and Amortize *lightens* every
run by stripping context the model does not need, *amortizes* repeat runs by replaying work it has
already done correctly, and *proves* the difference with a per-step cost ledger you can query. In
normal use it is invisible: same client, same output, smaller bill.

> **Status: both optimizer layers are live and measured.** On the demo task against Novita
> (`deepseek/deepseek-v4-flash`), a cold run through Amortize cost **−28% tokens** with a
> field-exact identical output (Layer 1), and the repeat run replayed a verified skill for
> **−97% tokens · parity ✓** (Layer 2). Those numbers come from a real run's ledger rows
> (`demo_report.json`, `simulated: false`) — this README never quotes a number that wasn't
> measured. Per-phase evidence: [SETUP_REPORT.md](SETUP_REPORT.md), [BUILD_REPORT.md](BUILD_REPORT.md).

---

## Quickstart

Three commands and one environment variable.

```bash
uv sync                                        # 1. install
uv run amort up                                # 2. start the proxy on :4000
export ANTHROPIC_BASE_URL=http://localhost:4000   # 3. point your client at it
```

That's it. Your existing code, the Anthropic SDK, Claude Code — all keep working, and every call
now lands in the ledger.

<details>
<summary>Without <code>uv</code></summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
amort up
```
</details>

```bash
cp .env.example .env      # optional: only needed for Snowflake or a fallback API key
uv run amort doctor       # check config, ledger backend, memory backend, upstream
```

---

## Architecture

```
        your app / Claude Code / any SDK
                    │
                    │  ANTHROPIC_BASE_URL=http://localhost:4000
                    ▼
        ┌───────────────────────────────────────────────┐
        │                 amortize                      │
        │                                               │
        │  ① LIGHTEN   every run              [ACTIVE]  │
        │     • tool schemas → compact stubs +          │
        │       a synthetic search_tools tool           │
        │     • oversized tool results spill to disk,   │
        │       model gets a handle + preview           │
        │                                               │
        │  ② AMORTIZE  repeat runs            [ACTIVE]  │
        │     • record each run as a Case  ──────────►  │ ──► EverOS
        │     • distil repeats into a Skill (Markdown)  │     (memory)
        │     • replay the skill as code: 2 small LLM   │ ◄──
        │       calls (bind params, verify output)      │
        │     • any guard fails → full agent            │
        │                                               │
        │  ③ PROVE     always on              [ACTIVE]  │
        │     • a StepEvent per LLM/tool/replay/grade ► │ ──► Snowflake
        │     • parity grader: warm ≡ cold              │     (or SQLite)
        │     • dashboard: the amortization curve       │
        └───────────────────────────────────────────────┘
                    │
                    ▼
        api.anthropic.com  /  api.openai.com
```

Three claims, three layers, and the third one is what makes the first two believable.

---

## Connecting Claude Code

**Verified** against Claude Code **v2.1.224** routed through this proxy: it sent a streaming
request carrying 24 tool schemas in an 83 KB body, and the task completed. Steps follow the
official [gateway docs](https://code.claude.com/docs/en/llm-gateway-connect).

```bash
uv run amort up                                   # terminal 1

export ANTHROPIC_BASE_URL=http://localhost:4000   # terminal 2
export ANTHROPIC_AUTH_TOKEN=sk-ant-…              # your key, sent as `Authorization: Bearer`
claude
```

Use `ANTHROPIC_AUTH_TOKEN` (bearer) **or** `ANTHROPIC_API_KEY` (`x-api-key`) — Amortize accepts
either and forwards it untouched. If you weren't told which your upstream wants, start with
`ANTHROPIC_AUTH_TOKEN`; a `401` means switch to the other.

**Verify before opening Claude Code** — the documented one-token check:

```bash
curl -X POST "$ANTHROPIC_BASE_URL/v1/messages" \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model": "claude-sonnet-5", "max_tokens": 1, "messages": [{"role": "user", "content": "."}]}'
```

A response starting `{"id":"msg_` means the proxy and your credential both work.

**Confirm inside Claude Code:** run `/status`. On the **Status** tab you should see

* `Anthropic base URL` → `http://localhost:4000` (this line only appears when a gateway is set), and
* an `Auth token` or `API key` line naming the variable you set.

Then send any prompt; a normal reply means you are running through Amortize.

To make it stick across every session, put it in `~/.claude/settings.json` instead of your shell:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4000",
    "ANTHROPIC_AUTH_TOKEN": "sk-ant-…"
  }
}
```

<details>
<summary>Optional flags, and what Amortize does about them</summary>

| Variable | When you need it |
|---|---|
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` | Your network only allows egress to the proxy. Also disables auto-update and gateway model discovery. |
| `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` | Adds models from `GET /v1/models` to the `/model` picker. Amortize relays that endpoint. |
| `ANTHROPIC_CUSTOM_HEADERS="X-Team: platform"` | Extra routing headers. Forwarded verbatim. |

Amortize implements the endpoints Claude Code actually calls: `POST /v1/messages` (including the
`?beta=true` form it really uses), `POST /v1/messages/count_tokens`, `GET /v1/models`, and the
`HEAD /` startup probe — plus a catch-all for anything else under `/v1`. It forwards
`anthropic-version` and `anthropic-beta` **unchanged** (never allowlisted — the beta set grows with
every release), leaves the `system` array's shape alone so the attribution block is still stripped
positionally upstream, relays SSE `ping`/comment keep-alives (Claude Code aborts a stream that goes
silent for 300 s), and passes upstream error bodies through verbatim so its compact-and-retry logic
still matches on the upstream's wording.
</details>

---

## The demo

```bash
uv run amort up                     # terminal 1
uv run amort demo --task ticket_triage   # terminal 2
```

Runs one task — triage 30 support tickets with 8 tools — four times: direct and through Amortize,
cold and re-prompted. Prints the 2×2 and writes `demo_report.json`.

```
              amortize · ticket_triage · deepseek/deepseek-v4-flash
┌─────────────────┬─────────────────────┬─────────────────────┬────────────────┐
│                 │ DIRECT (no Amortize)│    THROUGH AMORTIZE │               Δ│
├─────────────────┼─────────────────────┼─────────────────────┼────────────────┤
│First request    │ 48,703 tok · $0.008 │ 34,975 tok · $0.006 │            -28%│
│                 │             · 36.5s │             · 39.8s │                │
│Re-prompt (same) │ 39,403 tok · $0.007 │ 1,099 tok · $0.0002 │ -97% · parity ✓│
│                 │             · 33.5s │              · 7.3s │                │
└─────────────────┴─────────────────────┴─────────────────────┴────────────────┘
```

*(A real run, live on Novita, 2026-08-07 — ledger `snowflake`, memory `everos`, all four cells
`simulated: false`. Run-to-run trajectory noise moves the cold Δ by roughly ±10 points; the warm
row is deterministic code and stays put.)*

**The Δ column is computed, never asserted** — the harness measures both lanes and prints whatever
the ledger recorded, `0%` included. Row 1 is Layer 1 (schema dieting + result spill, same output —
parity is field-exact). Row 2 is Layer 2: the repeat replays the verified skill as code with two
small LLM calls, then the grader proves the output identical.

Live runs drive **Novita** (OpenAI-compatible; set `NOVITA_API_KEY` and optionally `NOVITA_MODEL`
in `.env`). Without a key the demo runs offline: a scripted agent calls the same 8 tools and token
counts are **estimated** from the real payload size. Every such number is tagged `simulated: true`
through the recorder, the table, and `demo_report.json`.

> **Set `AMORT_UPSTREAM_OPENAI=https://api.novita.ai/openai` in `.env` before a live run.** Lane A
> calls Novita directly via `NOVITA_API_URL`, but lane B goes through the proxy, which routes
> `/v1/chat/completions` to `AMORT_UPSTREAM_OPENAI` — and that defaults to `api.openai.com`. Leave
> it and lane B sends a Novita key to OpenAI and 401s. The two acceptance scripts hit the same wall.

### A second task

```bash
uv run amort demo --task invoice_reconcile --offline
```

`invoice_reconcile` reconciles 30 invoices against 26 payments with its own 8-tool catalogue
(~1,540 tokens of schema, comparable to `ticket_triage`'s ~1,500), so the Layer-1 dieting claim is
measured against more than one catalogue shape. Two of its four short payments are fully explained
by a credit note, so an agent that skips `lookup_credit_notes` gets exactly two rows wrong — the
task has a wrong answer that looks plausible, which is what makes the accuracy grade worth reading.

Its output list is named `lines` rather than `report` on purpose: `grader.py` keys a `report` list
on `ticket_id`, so a second task reusing that name would be compared on a field it does not have
and score **parity ✓ having compared nothing**. Under `lines` the grader falls through to exact
whole-object comparison instead — which is why its parity line reads `1 field` rather than `120`.

### The stage view

```bash
uv run amort demo --task ticket_triage --stage        # projector page on :4700
uv run amort demo --replay demo_report.json           # replay a recorded run (offline fallback)
```

`--stage` serves a dark, projector-sized page (default port 4700, `--stage-port` to change): two
lanes — DIRECT vs THROUGH AMORTIZE — with live token/dollar meters, per-run stopwatches, a parity
stamp, and a final full-screen delta computed from the measured runs. Events stream over SSE from
the demo process. `--replay` synthesizes the same event sequence from a recorded
`demo_report.json`, so the stage works with no network at all; replayed runs are labelled as such
and simulated numbers keep their label on screen.

```bash
uv run amort stats            # ledger rollup: runs, per-task totals, SAVINGS view
uv run amort skills list      # compiled skills and their status
uv run amort skills show <id> # one skill: status, parity, version, tools, markdown
uv run amort dash             # the dashboard
```

---

## Snowflake (the ledger)

Amortize writes one row per LLM call, tool call, replay step, and grade. Snowflake is the
destination; **SQLite is the automatic fallback and the default dev experience** — same schema,
same column names, same `SAVINGS` view, so the dashboard and every query work against either.

```bash
# .env
SNOWFLAKE_ACCOUNT=xy12345.us-east-1
SNOWFLAKE_USER=…
SNOWFLAKE_PASSWORD=…
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=AMORTIZE
SNOWFLAKE_SCHEMA=LEDGER
```

```bash
uv run amort snowflake-init              # creates AMORTIZE.LEDGER (tables + SAVINGS view)
uv run amort snowflake-init --dry-run    # print the DDL without connecting
```

`AMORT_LEDGER=auto` (the default) tries Snowflake and falls back to `.amort/amort.db`; `snowflake`
and `sqlite` force one. Writes are batched (20 events or 2 s) with retry, and a connection that
dies mid-run degrades to SQLite **replaying the in-flight buffer** — a booth wifi drop costs you
the Snowflake rows, not the demo. `amort stats` and the dashboard always print which backend the
numbers actually came from.

Schema: `RUNS`, `STEPS`, `SKILLS`, and a `SAVINGS` view — see
[`scripts/snowflake_setup.sql`](scripts/snowflake_setup.sql).

---

## EverOS (the memory)

Layer 2 needs somewhere to keep Cases (what happened on a run) and Skills (the distilled
procedure). [EverOS](https://github.com/EverMind-AI/EverOS) models both as first-class memory
kinds, so Amortize adapts to it rather than reimplementing it.

EverOS is a **service**, not a library:

```bash
uv sync --extra everos
uv run everos init --root .amort/everos
#  → edit .amort/everos/everos.toml and fill in [llm], [embedding], [rerank] API keys
ulimit -n 4096
uv run everos server start --root .amort/everos
```

```bash
# .env
EVEROS_MODE=local
EVEROS_BASE_URL=http://127.0.0.1:8000
EVEROS_AGENT_ID=amortize
```

**EverOS will not start without LLM credentials** (verified: the lifespan aborts with
`LLMNotConfiguredError` and `/health` never binds). So Amortize is local-first: when no server
answers, it writes the *same markdown layout* under `AMORT_MEMORY_DIR` —
`<app>/<project>/agents/<id>/{.cases,skills}/`, EverOS's entry-id and frontmatter conventions — and
retrieves with a local lexical scorer. Those files are drop-in for an EverOS memory root, so you
can start a server later and index them. When a server *is* up, Amortize additionally pushes each
run's trajectory through `/api/v2/memory/add` + `/flush` and uses hybrid retrieval for lookup.

---

## Commands

| Command | What it does |
|---|---|
| `amort up` | Start the proxy (`--port`, `--host`, `--reload`); ends with the paste-ready connect snippet |
| `amort demo` | The 2×2 comparison harness (`--task`, `--lanes`, `--live/--offline`, `--stage`, `--replay`) |
| `amort stats` | Ledger rollup, per-task totals + the `SAVINGS` view |
| `amort skills list` / `show <id>` | Compiled skills from the markdown store |
| `amort dash` | Streamlit dashboard |
| `amort snowflake-init` | Apply the ledger DDL (`--dry-run`) |
| `amort doctor` | Config, ledger, memory, Novita + upstream reachability, proxy health |

---

## Layout

```
amort/
├── cli.py                  typer entry point
├── config.py               pydantic-settings; nothing is required
├── proxy/
│   ├── server.py           FastAPI routes
│   ├── passthrough.py      streaming relay + usage capture
│   └── interceptors.py     Layer 1/2 seams — pass-through today
├── skills/
│   ├── recorder.py         trajectory → Case
│   ├── compiler.py         Case → Skill            [ACTIVE]
│   ├── replayer.py         Skill → warm execution  [ACTIVE]
│   ├── grader.py           parity + accuracy grading
│   └── store_everos.py     EverOS adapter, local-first
├── ledger/
│   ├── events.py           StepEvent + emit()
│   ├── pricing.py          $/Mtok, cache-aware
│   ├── snowflake_writer.py batched, retried, degradable
│   └── sqlite_writer.py    same schema, no credentials
├── demo/                   demo-only: task, harness, report, stage view
└── dashboard/app.py        Streamlit
```

---

## Verifying it yourself

```bash
uv run python scripts/smoke_proxy.py        # identical output, streaming, ledger row
uv run python scripts/smoke_claude_code.py  # 8 gateway-protocol conformance checks
uv run python scripts/smoke_ledger.py       # 1 RUN + 3 STEPS written and counted back
uv run python scripts/smoke_everos.py       # Case recorded, recalled by paraphrase
uv run python scripts/smoke_dash.py         # every chart got a non-empty frame
uv run ruff check amort scripts
```

None of these need an API key: the proxy tests run against an in-process mock upstream that speaks
the real Anthropic wire format, which is also what makes "byte-identical output" testable at all
(a live model may legitimately return different bytes for the same prompt).

---

## Honest edges

Named plainly so nobody demos this build believing otherwise:

* **Layer 1 scopes to non-streaming OpenAI-format requests.** Streaming traffic (e.g. Claude Code)
  passes through byte-identical and is measured, not lightened — SSE splicing is future work.
* **PLAN REPLAY** (injecting a verified plan for clients whose tools we can't execute) is wired and
  logs `meta.layer2`, but no savings number is claimed for it: on the procedure-locked demo prompt
  there is no exploration to remove, and its exploration-arm benchmark isn't demo-grade yet.
  FULL REPLAY (the −97% row) is the measured path.
* **Cold-run Δ varies** ±~10 points run-to-run — that's upstream trajectory noise, and the table
  prints whatever it measures. One fixture ticket (TKT-4116) is an occasional cold-model
  transcription coin-flip; the warm path is deterministic code and immune.
* **Speculative dispatch, auth/multi-tenancy, packaging.** Out of scope for this build.

## Contributing

Start with [TEAM.md](TEAM.md) — where the build is, today's sprint board, and open
tracks (pitch script, video demo, extra demo tasks, docs) you can claim.
[CONTRACTS.md](CONTRACTS.md) has the frozen interfaces and file ownership;
[CHANGELOG-AGENTS.md](CHANGELOG-AGENTS.md) is the per-branch log of what changed and which files
were touched. Prior art and dependencies are credited in
[ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).

## License

MIT (see [LICENSE](LICENSE))
