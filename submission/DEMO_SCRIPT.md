# Exact three-minute demo sequence

The product demonstration occupies 100 seconds inside `PITCH_SCRIPT.md`.

## Why the complete race is pre-run

The verified four-cell experiment takes roughly two minutes. Running it inside
a three-minute pitch would leave no time to explain the company or proof. Run it
immediately beforehand, keep its SHA/backend visible, and say it was pre-run.
The health check is live; the results and Snowflake rows are fresh evidence.

## Before speaking

```bash
uv run amort up
uv run amort doctor
uv run amort demo --task ticket_triage --live
```

Open and pin:

- the one-base-URL configuration with credentials hidden;
- the final 2×2 terminal result;
- the dashboard at `http://localhost:8501`;
- Snowflake rows filtered to the exact run IDs;
- a backup clip from the same commit.

## 0:36–0:50 — Live proxy proof

**Show:** `base_url=http://127.0.0.1:4000/v1`

**Run:**

```bash
curl -s http://127.0.0.1:4000/health
```

**Say:**

> This is live. The proxy is healthy, and the unchanged client is routed
> through it.

Leave after eight seconds even if the command stalls.

## 0:50–1:20 — Cold result

**Reveal:** the cold row from the fresh pre-run 2×2.

> Both sides triaged the same 30 tickets with the same model, tools, and grader.
> Direct sent every schema. Amortize discovered only what the model needed.

> **{{L1_SCHEMA_REDUCTION_PCT}} less schema context**,
> **{{L1_COST_REDUCTION_PCT}} lower cost**, and
> **{{COLD_PARITY_FIELDS}} identical fields**.

Do not celebrate before parity is visible.

## 1:20–1:50 — Repeat result

**Reveal:** the warm row from the same run.

> Direct paid for another full loop. Amortize reused a verified procedure and
> kept guards around the result.

> **{{L2_WARM_COST_REDUCTION_PCT}} cheaper**, with
> **{{WARM_PARITY_FIELDS}}-field parity. The cost drops. The answer doesn't.

Voice may trigger a rehearsed visual insert, but never imply the full pre-run
race is executing live.

## 1:50–2:15 — Snowflake receipt

**Show:** exact run IDs and their relevant step rows.

> Do not trust the percentage. Query it. These are the model calls, internal
> discovery calls, tools, replays, tokens, cost, and parity grade behind it.

Use a prewritten query. Do not edit SQL or scroll.

## 2:15–2:40 — Enterprise product

**Show:** open-source proxy → paid team control plane.

> Our user runs the agents. Our buyer owns the model bill. We start with
> measurable savings and expand into shared Skills, policy, budgets, and fleet
> analytics.

## Acceptance

- [ ] Full 2×2 run immediately before presenting
- [ ] Same SHA in result, script, screenshot, and backup
- [ ] `simulated: false`
- [ ] Cold and warm parity pass
- [ ] Ground-truth accuracy passes
- [ ] Backend and model labels visible
- [ ] Internal optimizer calls included in usage
- [ ] No target shown as achieved

## Failure ladder

1. Health check exceeds eight seconds: reveal the result.
2. Model/network fails before the pitch: use the truth-locked backup and saved
   Snowflake rows.
3. Snowflake fails: show the honest SQLite label and identify prior Snowflake
   evidence as prior.
4. Parity fails: do not claim the saving.

## Never show

- credentials, shell history, or environment files;
- an unverified Skill;
- scrolling logs;
- roadmap features as shipped;
- results from a different commit;
- language implying the pre-run 2×2 is executing live on stage.
