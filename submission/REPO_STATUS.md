# Repository and launch status

Audit date: **2026-08-07**  
Submission branch: **`sameer`**  
Implementation source: **`origin/main`**  
Latest main integrated during this launch pass: **`09e4396`**  
Submission owner: **Sameer Nagar · `sameernagar-hub`**

## Executive verdict

The idea is hackathon-win-worthy: it attacks the Cost of Intelligence track
with a direct-versus-optimized experiment, treats quality as a gate, and uses
Snowflake as the economic evidence layer rather than a decorative integration.

The current build is a strong finalist story, not yet the full winning demo.
LIGHTEN is merged and acceptance-green. Guarded REPLAY—the repeat-cost moment
that can deliver the largest dollar reduction—is still pending. The honest
launch state should show the real LIGHTEN result and identify REPLAY as the
remaining gate.

## What is built

| Area | Evidence | Status |
|---|---|---|
| Compatible proxy | OpenAI Chat Completions, Anthropic Messages, streaming/non-streaming, catch-all relay | Shipped and smoke-tested |
| One-endpoint adoption | Anthropic `ANTHROPIC_BASE_URL`; OpenAI-compatible `/v1` base URL | Shipped |
| PROVE ledger | Snowflake writer with SQLite fallback; run/step economics and pricing | Shipped |
| Memory foundation | local Markdown + EverOS adapter; Cases and Skill record shape | Shipped |
| Four-cell harness | direct/Amortize × new/repeat, deterministic 30-ticket task, 120-field grading | Shipped |
| LIGHTEN | on-demand tool discovery, schema dieting, result spill/read, fail-open loop | **Merged; current unit gate −65.4% schema tokens** |
| LIGHTEN live evidence | 41,058 → 34,820 live input tokens, field-exact parity | **−15.2% in one recorded pair** |
| Projector stage | SSE stage, live run events, report replay | Shipped at `:4700` |
| Dashboard | Streamlit economics view | Shipped at `:8501` |
| Submission kit | README, scripts, runbook, video plan, Q&A, launch deck, preview | Shipped on `sameer` |

## What remains

### Critical path to the winning demo

1. Merge guarded Skill compilation/replay from Workstream B.
2. Pass `scripts/accept_layer2.py` with all internal model calls included.
3. Run the final live four-cell race from a clean presentation SHA.
4. Confirm `simulated:false`, field-exact parity, ground-truth accuracy, model,
   backend, and verified Skill ID.
5. Replace pitch/deck/video truth tokens with raw dollars and the measured
   repeat-cost reduction.
6. Capture the Snowflake economics row and matching signed report by run ID.
7. Export the 75-second film and three-minute backup from that same evidence.

### Known documentation/product seams

- `GET /health` still labels LIGHTEN as `stub (TODO layer1)` even though the
  implementation and gate are merged. Do not show that response until main
  updates it.
- The offline report explanation still says both layers are stubs and may say
  the columns are equal even after LIGHTEN changes them. Update that copy on the
  implementation branch before using the offline fallback publicly.
- `BUILD_REPORT.md` still lists Workstream C as pending even though the stage
  code is merged.
- The root `README.md` and `TEAM.md` retain foundation-day status language.
  Treat `BUILD_REPORT.md` plus executable tests as the current source of truth.
- Parity and accuracy are computed after the initial run flush. Snowflake stores
  run/step economics; `demo_report.json` is currently authoritative for the
  quality verdict. Persist post-grade events before claiming all quality proof
  lives in Snowflake.
- The current live LIGHTEN result is one A/B pair. Run multiple repeats for a
  distribution if time permits; do not imply a mean.

## Verified current numbers

| Result | Value | Qualification |
|---|---:|---|
| Current eight-tool schema reduction | **65.4%** | local `accept_layer1.py`: 1,497 → 518 estimated tokens |
| Recorded live input-token reduction | **15.2%** | `BUILD_REPORT.md`: 41,058 → 34,820, one pair |
| Live final-report parity | **Pass** | field-exact in the recorded pair |
| Control quality | **120/120 identical; all cells correct** | pre-optimizer control at `f4fca99` |
| Guarded repeat-cost reduction | **Pending** | never substitute the ≥85% acceptance target |

## Demo routes

| Surface | Route / command |
|---|---|
| Proxy | `uv run amort up` → `http://127.0.0.1:4000` |
| OpenAI path | `POST http://127.0.0.1:4000/v1/chat/completions` |
| Anthropic path | `POST http://127.0.0.1:4000/v1/messages` |
| Health | `GET http://127.0.0.1:4000/health` *(do not project until stale status is fixed)* |
| Statistics | `GET http://127.0.0.1:4000/stats` |
| Live race + stage | `uv run amort demo --task ticket_triage --live --stage` |
| Projector stage | `http://127.0.0.1:4700` |
| Stage SSE | `GET http://127.0.0.1:4700/events` |
| Recorded replay | `uv run amort demo --replay demo_report.json` |
| Dashboard | `uv run amort dash --port 8501` → `http://127.0.0.1:8501` |

## Launch assets created

- [Editable six-slide PowerPoint](AMORTIZE_LAUNCH_DECK.pptx)
- [Deck preview](AMORTIZE_LAUNCH_DECK-preview.webp)
- [Three-minute product-launch pitch](PITCH_SCRIPT.md)
- [One-page timing card](THREE_MINUTE_CUE_CARD.md)
- [75-second video edit plan](VIDEO_PLAN.md)
- [75-second current-state caption track](amortize-product-75s-current.srt)
- [Exact demo script](DEMO_SCRIPT.md)
- [Operator runbook](DEMO_RUNBOOK.md)
- [Voice cursor integration](VOICE_CURSOR_INTEGRATION.md)
- [Enterprise one-pager](ENTERPRISE_ONE_PAGER.md)
- [Judge Q&A](JUDGE_QA.md)

## Win probability, candidly

| Dimension | Current state | What moves it to launch-grade |
|---|---|---|
| Track fit | Excellent | Show end-to-end dollar reduction, not only schema/input tokens |
| Product clarity | Excellent | Keep the one-endpoint → receipt story |
| Technical proof | Strong | Merge REPLAY and persist/join quality evidence cleanly |
| Enterprise value | Strong | Add one design-partner workflow and a break-even calculation |
| Demo polish | Strong | Record the actual stage/Snowflake film from final SHA |
| Credibility | Excellent | Preserve the no-fabricated-numbers discipline |

The winning close is:

> AI agents should have a learning curve—and finance should have the receipt.
