# Six-slide product-launch deck

The editable deck is [AMORTIZE_LAUNCH_DECK.pptx](AMORTIZE_LAUNCH_DECK.pptx).
It is designed for a three-minute product reveal: product by 0:15, evidence by
0:58, enterprise value by 2:18, hard close at 3:00.

## Audience and communication job

Audience: hackathon judges first, enterprise AI platform buyers second.

By the end, they should believe Amortize can become the enterprise agent
cost-control plane because it integrates at one endpoint, measures a fair race,
rejects savings when quality fails, and produces an auditable economics
receipt.

## Visual system

| Role | Treatment |
|---|---|
| Canvas | Obsidian `#070A0F` |
| Snowflake / proof | Ice blue `#29B5E8` |
| Saving / success | Electric lime `#B8FF5A` |
| Baseline | Steel `#8B95A7` |
| Guard / fallback | Amber `#FFB84D` |
| Type | Aptos Display headlines · Aptos body · Consolas evidence |

Rules: 16:9, one composition per slide, no stock robots, no fake customer
logos, no unverified percentage, no production instructions on screen, and no
claim without a report + backend + commit evidence trail.

## Slide 1 — Start with the reset

```text
THE WORKFLOW REPEATS.
THE COST RESETS.

AMORTIZE
The cost-control plane for enterprise AI agents
```

Visual: one completed ticket-triage run, then a second direct run whose meter
starts at full cost again. Bring the product wordmark in over the reset.

Speaker job: deliver the concrete 30-ticket opener in 15 seconds.

## Slide 2 — The accumulating invoice

One invoice line grows across the slide:

```text
TOOL CONTEXT  +  REPEATED REASONING  +  NO TASK-LEVEL RECEIPT
```

Footer:

```text
THE COMPANY PAYS FOR REASONING IT ALREADY OWNS.
```

Avoid three equal cards. The visual should feel like one compounding enterprise
problem.

## Slide 3 — One switch, three product acts

Show a real configuration diff:

```diff
- base_url = provider
+ base_url = http://127.0.0.1:4000/v1
```

Then one horizontal flow:

```text
SUPPORTED AGENT → LIGHTEN → REPLAY → PROVE → COMPATIBLE MODEL
```

Footer:

```text
FAIL-OPEN · SAME CLIENT · NO PROPRIETARY SDK
```

Use `REPLAY` visually to avoid using AMORTIZE as both the company and a verb.

## Slide 4 — LIGHTEN clears its gate

The current editable deck uses the newly merged Workstream A evidence:

```text
65.4%                     15.2%
LESS TOOL-SCHEMA CONTEXT  FEWER LIVE INPUT TOKENS

PARITY PASS · FIELD-EXACT FINAL REPORT
```

Evidence strip:

```text
UNIT GATE 1,497 → 518 EST. SCHEMA TOKENS · CURRENT CHECKOUT
LIVE PAIR 41,058 → 34,820 INPUT TOKENS · 09e4396 · not a mean or dollar claim
```

Keep the caveat visible: the model showed ±10–20% trajectory variance across
single pairs. After guarded REPLAY passes, extend this slide—or create the
launch-day result state—with a progressive repeat-cost reveal:

```text
NEW TASK
Direct {{DIRECT_COLD_COST_USD}} → Amortize {{AMORTIZE_COLD_COST_USD}}
{{L1_COST_REDUCTION_PCT}} LOWER COST

REPEAT
Direct {{DIRECT_WARM_COST_USD}} → Amortize {{AMORTIZE_WARM_COST_USD}}
{{L2_WARM_COST_REDUCTION_PCT}} LOWER COST

PARITY {{WARM_PARITY_FIELDS}} / 120 · CORRECT {{WARM_ACCURACY_FIELDS}} / 120
```

Never use `≥60%` or `≥85%` as a hero result. Those remain acceptance criteria.

## Slide 5 — The Agent Economics Receipt

Headline:

```text
DON'T TRUST THE PERCENTAGE. QUERY IT.
```

Show the relationship, not a wall of SQL:

```text
SNOWFLAKE ECONOMICS         SIGNED DEMO REPORT
RUN_ID                      same RUN_ID
INPUT / OUTPUT TOKENS       simulated: false
COST_USD                    parity: pass
MODEL / BACKEND             accuracy: pass
```

Bottom statement:

```text
COST PER SUCCESSFUL TASK—not merely cost per million tokens.
```

This wording is accurate for the current implementation: quality is calculated
by the harness/report and should not be described as a persisted Snowflake
grade row until that code exists.

## Slide 6 — Land, prove, expand

```text
ONE WORKFLOW  →  ONE PLATFORM TEAM  →  ENTERPRISE AGENT FLEET

open-source proxy       shared Skills       policy · budgets · chargeback
```

Label the right-hand capabilities `PRODUCT DIRECTION`.

Close full-screen:

```text
AI AGENTS SHOULD HAVE A LEARNING CURVE.
FINANCE SHOULD HAVE THE RECEIPT.

AMORTIZE
THE COST DROPS. THE GRADED OUTPUT DOESN'T.
```

Leave `github.com/vraj00222/Amort` visible after the presenter stops speaking.

## Backup slides to prepare only if time permits

### Why not prompt caching?

- Caching discounts repeated provider-recognized prefixes.
- LIGHTEN changes what enters context.
- REPLAY is designed to replace a full agent loop with guarded execution.
- PROVE counts internal optimizer work and measures cost per successful task.

### Safety boundary

- Candidate Skills never replay.
- Verified Skills still run guards.
- Failed optimization falls back to the original request.
- Savings fail when parity or ground-truth accuracy fails.
- Side-effecting workflows require idempotency, approval, and action policy.

### Category

```text
GATEWAY        routes model traffic
MEMORY / RAG   restores information
AMORTIZE       improves and audits task economics
```
