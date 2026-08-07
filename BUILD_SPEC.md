# AMORTIZE — Day-One Build Prompt

> **Human pre-flight (do these 3 things, then paste everything below):**
> 1. Open the repo where the setup prompt finished with all phases PASS.
> 2. In Claude Code, pick your strongest available model with `/model`, and press Shift+Tab into **plan mode** for the first response.
> 3. Paste this whole file as one message.

---

ultrathink.
## DELTA — READ FIRST (status has moved; trust SETUP_REPORT.md + git log)

- Setup is COMPLETE and verified end-to-end: EverOS live on :8000 (hybrid retrieval
  smoke PASS), proxy streaming + non-streaming against upstream, Snowflake PAT auth
  working, AMORTIZE.LEDGER (RUNS/STEPS/SKILLS/SAVINGS) live with META VARIANT
  queryable, real traffic already logged, ruff clean.
- UPSTREAM CHANGE: the working upstream is Novita (OpenAI-compatible), NOT Anthropic.
  Every demo run must work on Novita. Keep the Anthropic /v1/messages path intact but
  nothing in today's demo may depend on it.
- FIRST TASK (main session, before spawning any workstream): make `amort demo --live`
  run on Novita (~30 lines, currently Anthropic-only). Verify, commit. This unblocks
  everything.
- DO NOT REGRESS the two fixed Snowflake quirks: STEPS insert must stay in the
  SELECT … FROM VALUES multi-row form with PARSE_JSON (executemany → 252001), and
  snowflake-init must keep skipping already-existing container statements. The
  ledger's "BACKEND USED" honest-reporting line is load-bearing — never remove it.
- PAT expires Aug 8 — fine for today, spend zero time on auth.
- STRETCH ONLY, inside Workstream C, and only after all integration gates pass:
  Cortex Agent semantic view + agent:run wiring. It does not start before the 2×2
  demo table and stage view are green.
- Everything else below stands unchanged: same contracts, workstreams, gates,
  cut lines, and the no-fabricated-numbers rule.
## ROLE

You are the lead engineer + integrator for **AMORTIZE**. The scaffold, transparent proxy passthrough, EverOS adapter, Snowflake/SQLite ledger, demo harness skeleton, and dashboard stub already exist and passed smoke tests — read `SETUP_REPORT.md`, `README.md`, and skim every file under `amort/` **before writing any code**. Today you turn the stubs into a demo-ready product.

## MISSION & PRIORITY ORDER

Hard priority, in order — if time runs out, everything above the line must work:

1. **Layer 1 (LIGHTEN)** live in the proxy, with measured token deltas.
2. **Layer 2 (AMORTIZE)** live: record → compile → replay → verify, with measured deltas + parity.
3. **Demo**: `amort demo` produces the honest 2×2 table AND a projector-ready stage view.
4. **Dashboard** polished; `amort stats`; README final.
5. (stretch) niceties: banner, colors, extra tasks.

**Iron rule: no fabricated numbers, ever.** Every percentage shown anywhere must come from a real run logged in the ledger. If a layer underperforms, the demo shows the real number.

## OPERATING MODE — plan, then parallelize

**Step 1 — PLANNING PROTOCOL (plan mode, ultrathink). The plan must contain all five parts before any code is written:**
1. **Comprehension gate:** restate, in your own words, the three layers, the frozen contracts, and how a request flows through the proxy in cold vs warm mode. If any restatement conflicts with the repo's actual code, flag it now.
2. **Pre-mortem:** the five likeliest ways today fails, each with a mitigation. Seed list (extend it): modifying requests breaks SSE streaming passthrough; usage tokens missing/misparsed in streaming responses; EverOS API differs from the adapter's assumptions; subagents collide on shared files; the live demo flakes on stage. Mitigations become tasks.
3. **Test-first on the headline claims:** before implementation, write the two acceptance tests that encode the demo's claims — (a) Layer 1 ON vs OFF: equal output, ≥60% schema-token reduction; (b) warm vs cold: ≥85% cheaper, parity ✓. Subagents build until these pass.
4. **Task breakdown + merge order** per workstream, with explicit file ownership.
5. **Checkpoint plan:** integration gate every ~45 minutes.

Then exit plan mode and execute.

**Discipline during execution:**
- **Context hygiene:** subagents return a diff + a ≤20-line summary only — never raw logs or file dumps into the main context. Delegate research/exploration to throwaway subagents.
- **Thinking budget:** ultrathink for planning and for integration debugging only; standard effort during routine implementation loops — speed matters today.
- **Escalation rule:** blocked >20 minutes on any third-party surface (EverOS, Snowflake) → implement the documented fallback, note it in BUILD_REPORT.md, move on. No rabbit holes.
- **Checkpoint cadence:** every ~45 min the integrator merges ready work, runs the gates, commits. Any workstream that slips two consecutive checkpoints gets its cut line applied immediately.
- **Final rehearsal (non-negotiable):** from a clean state, run the three demo commands end-to-end twice; record the second run to `demo_report.json` as the offline replay.

**Step 2 — freeze contracts BEFORE spawning agents.** These interfaces are law; no agent may change them without integrator sign-off:
- `interceptors.before_request(ctx, req) -> req` / `after_response(ctx, resp) -> resp` and the proxy's internal loop hook `on_tool_use(ctx, block) -> handled|passthrough`
- `StepEvent` schema (ledger/events.py) — extend only via `meta`
- Skill markdown schema (as in setup prompt) — extend only via new frontmatter keys
- `store_everos.py` function signatures

**Step 3 — spawn three subagents in parallel, each with worktree isolation, each owning ONLY its directories.** Do not let any agent touch files outside its ownership; shared files (`events.py`, `config.py`, `pricing.py`) are integrator-only. Maximum 3 implementation agents. Each returns a diff + a test log; the integrator (you, main session) merges in dependency order (A → B, C anytime), runs the full smoke suite after every merge, and commits per merge.

| Agent | Owns | Delivers |
|---|---|---|
| **A — Lighten** | `amort/proxy/` | Layer 1 in interceptors + proxy loop |
| **B — Amortize** | `amort/skills/` | Layer 2 pipeline end-to-end |
| **C — Showtime** | `amort/demo/`, `amort/dashboard/`, `amort/cli.py`, `README.md` | demo, stage view, dashboard, DX |

---

## WORKSTREAM A — Layer 1: LIGHTEN

**A1. Tool-schema dieting (the 46.9% pattern).** In `before_request`: if the request carries > `AMORT_TOOL_STUB_THRESHOLD` (default 4) tools, stash the full catalog in the run context, strip it from the outbound request, and replace with (a) one-line stubs `name — first sentence of description` embedded in a system note, plus (b) a synthetic `search_tools(query)` tool. **The search loop is handled entirely proxy-side:** when the model emits a `search_tools` tool_use, the proxy intercepts it (never forwarded to the client), resolves matches against the stashed catalog (substring + fuzzy), returns a tool_result with the **full schemas of only the matched tools**, adds those tools to the active set, and continues the upstream conversation. The client sees none of this — it receives a normal final response.

**A2. Result spill.** In the proxy loop: any tool_result larger than `AMORT_SPILL_THRESHOLD` tokens (default 1,500) is written to `.amort/spill/<run>/<step>.txt`; the model receives a handle + head/tail preview (~200 tokens) + a synthetic `read_spill(handle, mode=head|tail|grep, arg)` tool, also resolved proxy-side.

**A3. Measurement.** Every intercepted request logs `meta.layer1 = {schema_tokens_before, schema_tokens_after, spilled_tokens}` on its StepEvent.

**A4. Tests (must pass):** fixture request with the 8 verbose demo tools → schema tokens reduced ≥60%; a scripted end-to-end task through the proxy with Layer 1 ON vs OFF yields **equal final outputs** and lower total tokens; `search_tools` and `read_spill` loops each covered by a unit test; unknown/simple requests (≤ threshold tools) pass through untouched — zero regression to Phase-6 passthrough behavior.

## WORKSTREAM B — Layer 2: AMORTIZE

**B1. Recorder.** Tap the proxy loop to assemble the full trajectory per `run_id` (llm calls, tool calls, args, results, final output); on run completion, `record_case()` into EverOS.

**B2. Compiler.** One LLM call transforms a Case into a Skill markdown exactly per the frozen schema: separate constants from `{{params}}`, list `tools_required` (this is Layer 1's tool subset for warm runs), write per-step guards, write the output template. Status: `candidate`.

**B3. Replay — implement BOTH modes:**
- **FULL REPLAY (demo path):** for tasks whose tools are registered proxy-side (the demo's mock tools), execute the skill's steps directly in the proxy; LLM is called exactly twice — bind `{{params}}` from the incoming message, and verify/format the final output.
- **PLAN REPLAY (universal path & fallback):** when the proxy cannot execute the tools (real clients like Claude Code own their tools), inject the compiled plan + **only** `tools_required` schemas into the outbound request as a system directive ("a verified prior solution to this exact task; follow it, deviate only if a guard fails"). Still a large saving: no exploration, no full catalog. **Injection budget cap:** the injected plan + schemas may never exceed `AMORT_INJECT_BUDGET` tokens (default 2,000) — truncate the plan to step titles + guards if over budget. Even our memory is metered.

**B4. Matching & safety.** `fingerprint()` on every incoming request; EverOS `search_skill` above a similarity threshold triggers warm mode. Any guard failure mid-replay → abandon, fall back to the full cold path, record a fresh Case, and log the fallback.

**B5. Grader & ladder.** Field-exact JSON comparison for structured outputs (LLM-judge fallback for prose). Parity pass → increment `runs_observed`/`parity_rate`, promote `candidate → verified` after 2 passes; any fail → demote and quarantine. Update SKILLS table + `avg_warm_cost`, `total_saved_usd`.

**B6. Tests (must pass):** on the fixture task — warm FULL REPLAY ≥85% cheaper than that run's own cold baseline; parity ✓; a deliberately-broken guard triggers clean fallback and the run still completes cold; PLAN REPLAY measurably cheaper than cold (report the real %).

## WORKSTREAM C — SHOWTIME

**C1. `amort demo --task ticket_triage`** runs the full sequence — A-cold, B-cold, A-repeat, B-repeat — and renders the 2×2 rich table (tokens · $ · wall-time per cell, Δ% column, parity badge), writing `demo_report.json` and ledger rows for every run.

**C2. Stage view — `amort demo --stage`:** a local web page (serve static from the proxy or a tiny FastAPI route) designed for a projector: two lanes with **live-animating token/dollar meters** during runs, elapsed-time stopwatches, a parity ✓ that stamps in, and a final full-screen number ("−93% · output verified identical"). Dark background, huge type. Reads run events over SSE/websocket from the harness. If a run is in progress it animates; `--replay demo_report.json` replays a recorded run for the **offline fallback** — record one good run to JSON as soon as everything passes.

**C3. Dashboard:** amortization curve (cost-per-run vs run #, colored by lane/mode), cumulative $ saved counter, per-tool cost bar, skills table with status + parity rate. Snowflake first, SQLite fallback, one env var switch.

**C4. DX:** `amort stats` (per-task totals + savings from the SAVINGS view), `amort skills list|show`, startup banner, README final pass with the exact Claude Code connect steps and demo instructions. **`amort up` must end by printing the paste-ready connect snippet** (the exact `export ANTHROPIC_BASE_URL=…` / `ANTHROPIC_AUTH_TOKEN=…` lines and the settings.json equivalent) so connecting any client is copy-paste. Add `version` to the Skill frontmatter and bump it on every re-distillation. If any external pattern or code is borrowed (e.g., MIT-licensed projects), create `ACKNOWLEDGEMENTS.md` and credit it explicitly.

---

## INTEGRATION GATES (run after every merge, all must pass before the next merge)

1. Phase-6 passthrough smokes still green (identical output, streaming intact, Claude Code routes).
2. `amort demo --task ticket_triage` completes and the table's numbers are internally consistent with ledger rows.
3. `ruff check` clean; no secrets in diff; no test marked skip without a note.

## END-TO-END ACCEPTANCE (the demo, as commands)

```bash
amort up                                   # terminal 1
amort demo --task ticket_triage --stage    # terminal 2 → browser on projector
amort dash                                 # terminal 3, after the run
```
Expected on stage: cold-vs-cold shows the Layer-1 delta; repeat-vs-repeat shows the Layer-2 delta with parity ✓; dashboard curve renders from the same ledger rows; `amort stats` prints totals. Then the universality beat: `/status` inside Claude Code showing the Amortize base URL — proof this is one env var for any AI app.

## CUT LINES (apply in order only if behind)

1. Drop FULL REPLAY → ship PLAN REPLAY only (smaller % but universal; demo the real number).
2. Compiler LLM call flaky → hand-written template Skill for the demo task, compiler marked experimental.
3. Snowflake slow/unreachable → run on SQLite, bulk-load rows to Snowflake once before demo so the dashboard reads Snowflake live.
4. Stage web view → rich table full-screened in the terminal (still legible on a projector).

## REPORT

Maintain `BUILD_REPORT.md`: per workstream — what shipped, measured deltas (with run_ids), gaps, and the exact demo-day runbook. Final commit: `day-one: demo-ready`.