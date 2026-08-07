# AMORTIZE — Day-One Build Report

Build day: 2026-08-07. Upstream: **Novita** (`https://api.novita.ai/openai`, OpenAI-compatible), model `deepseek/deepseek-v4-flash` ($0.14/$0.28 per Mtok, priced in `pricing.json`). Anthropic `/v1/messages` path kept intact; nothing in today's demo depends on it.

Plan of record: `CONTRACTS.md` (frozen interfaces) + the approved day plan. Acceptance tests written before implementation: `scripts/accept_layer1.py`, `scripts/accept_layer2.py`, gate runner `scripts/gate.sh`.

---

## T0 — Integrator foundation (complete)

**Novita port of `amort demo --live`** — commit `af77cb2`. `config.py` gained `novita_*` fields + the Layer-1/2 knobs (`AMORT_LIGHTEN`, `AMORT_TOOL_STUB_THRESHOLD`, `AMORT_SPILL_THRESHOLD`, `AMORT_INJECT_BUDGET`); `ticket_triage.py` gained an OpenAI-format `run_live` (Anthropic loop kept as `run_live_anthropic`); harness lanes route `{novita_api_url}/v1` (A) and `{proxy}/v1` (B).

**First live 2×2 on Novita — worked end-to-end, and the honest harness caught two real problems** (run ~13:0x local, ledger=snowflake, memory=everos, `demo_report.json` written):

```
A_cold 140,642 tok · $0.023 · 2m11s    B_cold 148,747 tok · $0.024 (Δ +6%)
A_warm 131,486 tok · $0.022 · 2m56s    B_warm 139,262 tok · $0.024 (parity ✓ vs B_cold)
A cold vs B cold: parity ✗ — 12 priority mismatches (P2 vs P1)
accuracy vs ground truth: all four runs incorrect
~10 llm / 71 tool calls per run
```

Diagnosis: the fixture's priority rule was never stated in the prompt, so deepseek guessed (differently per run), and `get_customer` (single-id) forced ~30 per-ticket calls — trajectory divergence + 140k tokens + 2-3 min per run. **Fix (commit `a8c19db`): the task is now fully specified** — explicit P0-P3 rubric in SYSTEM, strict batching ("each tool at most once, all ids batched"), `check_sla` returns the customer `plan` tier, `seed=20260807`. Parity/accuracy now measure the layers, not model noise. Second verification run: *(pending — recorded below when complete)*.

Also this phase: GitHub remote wired (`vraj00222/Amort`), TEAM.md for contributors, license aligned to the repo's MIT LICENSE.

## Workstream A — LIGHTEN

*(pending merge)*

## Workstream B — AMORTIZE

*(pending merge)*

## Workstream C — SHOWTIME

*(pending merge)*

## Gates

| Gate | When | Result |
|---|---|---|
| G0 smokes + ruff + quirk-greps | after T0 | accept tests fail-by-design (test-first); smokes green at T0 commits |

## Demo-day runbook

*(written at G4)*
