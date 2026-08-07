# Six-slide enterprise deck

This is a demo deck, not a document. Six slides, three minutes, and the product
is visible before the first minute.

## Visual system

| Role | Treatment |
|---|---|
| Canvas | Obsidian `#070A0F` |
| Proof / Snowflake | Ice blue `#29B5E8` |
| Savings | Electric lime `#B8FF5A` |
| Baseline | Steel `#8B95A7` |
| Guard / fallback | Amber `#FFB84D` |
| Type | Sora or Space Grotesk headlines; Inter body; JetBrains Mono metrics |

Rules: 16:9, no stock robots, no paragraph text, no fake customer logos, no
unverified percentage, and no metric without `demo_report.json · <commit>`.

## Slide 1 — Company and promise

```text
AMORTIZE
The cost-control plane for enterprise AI agents

Every agent run should get cheaper with experience.
```

Visual: the same agent run repeats three times while cost stops resetting after
Amortize appears.

## Slide 2 — The enterprise cost problem

Three columns, one line each:

```text
CONTEXT TAX       REPETITION TAX       ACCOUNTABILITY GAP
Pay for every     Rediscover solved    A bill without task,
tool every turn   workflows            step, or parity proof
```

Footer:

```text
The company pays for reasoning it already owns.
```

## Slide 3 — One switch, three verbs

```text
ANY AGENT ── one base URL ──▶ AMORTIZE ──▶ ANY COMPATIBLE MODEL

LIGHTEN              AMORTIZE               PROVE
less context         verified reuse         Snowflake receipt
```

Footer: `Fail-open · same client · no SDK swap`

Transition directly into the live demo.

## Slide 4 — The fair race

```text
                    DIRECT               AMORTIZE
NEW TASK            full agent           LIGHTEN
REPEAT              full agent again     Skill replay

Same model · Same task · Same tools · Same 120-field grader
```

This slide becomes the live result card:

```text
{{L1_SCHEMA_REDUCTION_PCT}}       {{L2_WARM_COST_REDUCTION_PCT}}
less schema context              cheaper repeated run

PARITY ✓ {{WARM_PARITY_FIELDS}} fields
```

Source line: `{{MODEL}} · {{LEDGER_BACKEND}} · {{FINAL_SHA}}`

## Slide 5 — The Snowflake receipt

Headline:

```text
DON'T TRUST THE PERCENTAGE. QUERY IT.
```

Show one real query result with only these highlighted fields:

```text
RUN_ID · TASK · INPUT_TOKENS · COST_USD · PARITY
```

Bottom row:

```text
Today: cost per successful task
Next: budgets · routing · policy · chargeback
```

Label the second line “product direction.”

## Slide 6 — Business and close

```text
USER                         BUYER
AI platform engineer         VP Engineering / Head of AI / FinOps

WEDGE                        ENTERPRISE CONTROL PLANE
open-source local proxy      shared Skills · policy · budgets · analytics
```

Close full-screen:

```text
Every agent run should get cheaper with experience.
```

Repository QR and team names only.

## Backup slide A — Why not prompt caching?

- Caching discounts repeated bytes.
- LIGHTEN changes what enters context.
- AMORTIZE can replace a full agent loop with guarded execution.
- PROVE measures cache reads and Amortize savings separately.

## Backup slide B — Safety

- Candidate Skills never replay.
- Verified Skills still run guards.
- Failed optimization falls back to the original request.
- Savings fail if parity or accuracy fails.

## Backup slide C — Category

```text
Gateway        routes model traffic
Memory / RAG   restores information
Amortize       improves and audits task economics
```
