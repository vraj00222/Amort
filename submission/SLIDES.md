# Eight-slide deck — three minutes, one story

## Visual system

**Mood:** financial terminal meets agent runtime; precise, dark, and fast—not a
generic purple AI gradient.

| Token | Direction |
|---|---|
| Canvas | Obsidian `#070A0F` |
| Snowflake/proof | Ice blue `#29B5E8` |
| Savings | Electric lime `#B8FF5A` |
| Baseline | Cool gray `#8B95A7` |
| Warning/fallback | Amber `#FFB84D` |
| Type | Space Grotesk or Sora for headlines; Inter for body; JetBrains Mono for metrics |

Rules:

- 16:9, 1920×1080.
- One sentence or one visual idea per slide.
- Headlines ≥54 pt; result numbers ≥96 pt.
- No stock robots, floating brains, handshakes, code walls, or fake dashboards.
- Animate only state changes: full context → light context; cold → warm; claim →
  Snowflake receipt.
- Keep source text under each measured number: `demo_report.json · commit <sha>`.

## Slide 1 — The villain

**On screen:**

> # AI agents have amnesia.
> ## Your cloud bill does not.

Bottom-right: a small counter showing the same context block being charged on
Run 1, Run 2, Run 3.

**Purpose:** Make the problem memorable before naming the company.

## Slide 2 — The one-switch reveal

**On screen:**

```text
YOUR AGENT  ── one base URL ──▶  AMORTIZE  ──▶  ANY MODEL
```

Under it:

> No SDK swap. No agent rewrite. Fail-open by design.

**Live transition:** Zoom into `http://127.0.0.1:4000/v1` and switch to the
terminal.

## Slide 3 — Three verbs

Use three large horizontal panels:

| LIGHTEN | AMORTIZE | PROVE |
|---|---|---|
| Reveal tool context only when needed | Turn repeats into guarded Skills | Put every token, dollar, and parity grade in Snowflake |

Footer:

> New work gets lighter. Repeated work gets reusable. Every claim gets a receipt.

## Slide 4 — The fair race

**On screen:** A 2×2 grid with two axes.

```text
                 DIRECT          AMORTIZE
COLD             control         LIGHTEN
REPEAT           control         SKILL REPLAY
```

Right edge: **Same model · Same task · Same tools · Same 120-field grader**

**Purpose:** Explain experimental fairness in five seconds, then run the demo.

## Slide 5 — The result

This slide is generated only after the final truth lock.

```text
{{L1_SCHEMA_REDUCTION_PCT}}       {{L2_WARM_COST_REDUCTION_PCT}}
less schema context              cheaper repeated run

                 PARITY  ✓  {{WARM_PARITY_FIELDS}} fields
```

Small footer:

```text
{{FINAL_MODEL}} · {{LEDGER_BACKEND}} · demo_report.json · commit {{FINAL_SHA}}
```

Do not show target percentages as results.

## Slide 6 — The Snowflake receipt

**On screen:** A simplified trace:

```text
RUN → LLM → search_tools → LLM → tool → grade
      tokens   internal    tokens        parity ✓
```

Alongside it, show one real Snowflake result table with four highlighted
columns: `RUN_ID`, `INPUT_TOKENS`, `COST_USD`, `PARITY`.

Headline:

> # Don't trust the percentage. Query it.

## Slide 7 — From proxy to economic layer

Three ascending product cards:

1. **Local** — transparent proxy, SQLite fallback, developer dashboard.
2. **Team** — shared verified Skills, budgets, policy, fleet analytics,
   chargeback.
3. **Economy** — reusable Skills, model brokerage, cost-aware agent routing.

Mark tiers 2 and 3 **Product direction**, not shipped.

## Slide 8 — The closing frame

**On screen:**

> # Compound intelligence.
> # Not token bills.

Below: final verified result card, repository QR, team names, Snowflake × Beta
Fund lockup.

No feature list. End on the product belief.

## Optional backup slides

### A — Why this is not prompt caching

- Caching discounts repeated bytes; Amortize changes what needs to be sent and
  can replace an agent loop with guarded code execution.
- Cache benefits depend on provider and prefix stability; Skills are explicit,
  inspectable, versioned procedures.
- Amortize records provider cache reads separately and can benefit from both.

### B — Safety and failure behavior

- Candidate Skills never replay.
- Verified Skills still enforce guards.
- Tool output stays out of the binding/verification model context.
- Any optimization exception falls back to the original full request.
- Parity and accuracy are recorded separately from cost.

### C — Current build boundaries

Use the live status from `BUILD_REPORT.md`; never claim multi-tenancy,
production auth, or speculative dispatch.
