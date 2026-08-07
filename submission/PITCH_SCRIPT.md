# Three-minute YC-style demo pitch

The full four-cell experiment takes roughly two minutes by itself. Run it
immediately before presenting. On stage, perform one fast live proxy check,
reveal that fresh truth-locked result, and query its Snowflake rows. Say this
plainly; never imply the pre-run experiment is executing live.

## Truth lock

Replace only from the final live `demo_report.json` and ledger:

```text
{{L1_SCHEMA_REDUCTION_PCT}}
{{L1_COST_REDUCTION_PCT}}
{{L2_WARM_COST_REDUCTION_PCT}}
{{COLD_PARITY_FIELDS}}
{{WARM_PARITY_FIELDS}}
{{MODEL}}
{{LEDGER_BACKEND}}
{{FINAL_SHA}}
```

## Script

### 0:00–0:18 — Problem

**Screen:** “Every agent run should get cheaper with experience.”

> Enterprises are hiring AI agents faster than they can control their model
> bill. Every run resends tool manuals, reprocesses large results, and
> rediscovers workflows the company already paid to solve.

### 0:18–0:36 — Company

**Screen:** Agent → Amortize → Model. Highlight one base URL.

> Amortize is the cost-control plane for enterprise AI agents. Change one base
> URL—no agent rewrite—and we reduce avoidable context, turn successful repeats
> into guarded Skills, and prove the saving in Snowflake.

### 0:36–0:50 — Live proof

**Screen:** Run `curl -s http://127.0.0.1:4000/health`.

> This is live. The proxy is healthy, and the unchanged client uses the same
> model interface it used before Amortize.

### 0:50–1:20 — New-task result

**Screen:** Reveal the fresh pre-run cold row with SHA and backend visible.

> We ran the complete comparison immediately before coming on stage. Both sides
> triaged the same 30 tickets with the same model, eight tools, and 120-field
> grader. Direct sent every schema. Amortize discovered only what the model
> needed.

> Tool context fell **{{L1_SCHEMA_REDUCTION_PCT}}**. Cost fell
> **{{L1_COST_REDUCTION_PCT}}**. The answer still matched
> **{{COLD_PARITY_FIELDS}} fields**.

### 1:20–1:50 — Repeated-task result

**Screen:** Reveal the warm row from the same run.

> On the repeat, Direct paid for another agent loop. Amortize reused a verified
> procedure, ran the tools as code, and checked the result. If a guard fails, it
> falls back to the full agent.

> The repeat was **{{L2_WARM_COST_REDUCTION_PCT}} cheaper**, with
> **{{WARM_PARITY_FIELDS}}-field parity. The cost drops. The answer doesn't.

### 1:50–2:15 — Snowflake receipt

**Screen:** The exact run and step rows.

> Do not trust our percentage. Query it. Snowflake records every external and
> internal model call, tool, replay, token, dollar, and parity grade. That turns
> model spend into cost per successful task.

### 2:15–2:40 — Enterprise product

**Screen:** Local proxy → Team control plane → Agent economics.

> Our user is the AI platform engineer. Our buyer owns the model bill. The
> open-source proxy is the wedge; the enterprise product adds shared Skill
> governance, policy, budgets, and fleet analytics.

### 2:40–3:00 — Close

**Screen:** Final result, parity, Snowflake receipt, QR code.

> The first generation of agents gets smarter by calling bigger models. The
> next gets more valuable by reusing what the company already knows.

> Amortize. **Every agent run should get cheaper with experience.**

Stop at 3:00.

## If a gate misses

> Our final run measured **{{ACTUAL_PCT}}** against a
> **{{TARGET_PCT}}** gate, with exact parity. We are showing what happened, not
> what we hoped.

## Delivery rules

- Leave the health check after eight seconds whether it returns or not.
- Do not read commands, architecture labels, or future feature lists.
- Pause after each measured percentage.
- At 1:50 open Snowflake; at 2:15 stop technical detail; at 2:40 close.
- Never say “zero hallucinations,” “guaranteed savings,” or “enterprise-ready”
  for roadmap features.
