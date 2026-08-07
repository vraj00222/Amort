# Three-minute product-launch pitch

This is a launch demo, not a narrated document. Run the complete four-cell race
immediately before presenting, then reveal its result from the exact same git
SHA. The stage, report, Snowflake rows, screenshots, and spoken numbers must all
agree.

Target delivery: **278 spoken words**, leaving time for three-second
metric holds and screen transitions. Hard stop at **3:00**.

## Truth lock

Replace these tokens only from the final live `demo_report.json`, matching
ledger rows, and `git rev-parse --short HEAD`:

```text
{{DIRECT_COLD_COST_USD}}
{{AMORTIZE_COLD_COST_USD}}
{{L1_SCHEMA_REDUCTION_PCT}}
{{L1_COST_REDUCTION_PCT}}
{{DIRECT_WARM_COST_USD}}
{{AMORTIZE_WARM_COST_USD}}
{{L2_WARM_COST_REDUCTION_PCT}}
{{COLD_PARITY_FIELDS}}
{{COLD_ACCURACY_FIELDS}}
{{WARM_PARITY_FIELDS}}
{{WARM_ACCURACY_FIELDS}}
{{RUN_ID}}
{{MODEL}}
{{LEDGER_BACKEND}}
{{FINAL_SHA}}
```

Do not replace a token with a target. If LIGHTEN or REPLAY misses its gate, use
the honest fallback at the end of this file.

## Script

### 0:00–0:15 — Start inside the product

**Screen:** Projector stage shows `30 tickets complete`. The same task appears
again and the direct cost meter resets.

> This agent just triaged 30 support tickets. Ask it to repeat tomorrow, and
> the company pays it to reload every tool and rediscover the same procedure.
> Agents learn. Their economics don't.

### 0:15–0:31 — Introduce Amortize

**Screen:** Product name appears between the agent and model.

> Amortize is the cost-control plane for enterprise AI agents. We reduce
> avoidable context on new work, reuse guarded procedures on repeats, and
> measure cost per successful task.

### 0:31–0:44 — The switch

**Screen:** Before/after configuration diff. Only `base_url` changes.

> This is the entire integration. Same client. Same model interface. Same eight
> tools. One base URL now routes the workflow through Amortize.

### 0:44–0:58 — The contract

**Screen:** Four-cell fair-race frame.

> We ran this comparison moments ago: same model, same 30 tickets, same tools,
> same prompt, and the same 120-field ground-truth grader.

### 0:58–1:26 — New-task reveal

**Screen:** Reveal raw cold dollars first, then reduction, parity, and accuracy.

> On the new task, Direct cost **{{DIRECT_COLD_COST_USD}}**. Amortize cost
> **{{AMORTIZE_COLD_COST_USD}}**—down **{{L1_COST_REDUCTION_PCT}}**, with
> **{{L1_SCHEMA_REDUCTION_PCT}}** less tool-schema context. All
> **{{COLD_PARITY_FIELDS}}** fields matched, and all
> **{{COLD_ACCURACY_FIELDS}}** matched ground truth.

### 1:26–1:54 — Repeat reveal

**Screen:** Direct pays for another loop; Amortize takes the guarded Skill path.

> On the repeat, Direct cost **{{DIRECT_WARM_COST_USD}}**. Amortize reused a
> verified procedure with guards and fallback: **{{AMORTIZE_WARM_COST_USD}}**,
> down **{{L2_WARM_COST_REDUCTION_PCT}}**. Again:
> **{{WARM_PARITY_FIELDS}}** identical and **{{WARM_ACCURACY_FIELDS}}** correct.

### 1:54–2:18 — The Agent Economics Receipt

**Screen:** Snowflake row for `{{RUN_ID}}`; then the matching signed report.

> Don't trust the percentage. Query it. Snowflake records the calls, tools,
> tokens, dollars, and backend behind this run. The signed report records parity
> and accuracy. Together they turn model spend into cost per successful task.

### 2:18–2:42 — Enterprise motion

**Screen:** `one workflow → one platform team → enterprise agent fleet`.

> We land with one repetitive workflow and one AI platform engineer. Once the
> economics are proven, the paid control plane expands into shared Skills,
> policy, budgets, chargeback, and fleet analytics.

### 2:42–3:00 — Close

**Screen:** Return to the winning cost number, `120/120 correct`, product name,
and repository URL.

> Companies don't buy tokens. They buy completed work. AI agents should have a
> learning curve—and finance should have the receipt. Amortize. The cost drops.
> The graded output doesn't.

Stop speaking. Leave the repository URL visible.

## Honest fallback if a gate misses

### Current LIGHTEN-only launch state

If guarded REPLAY has not passed, replace the 0:58–1:54 result section with:

> LIGHTEN is already through its gate. On the current checkout, the eight-tool
> schema fell from 1,497 to 518 estimated tokens—**65.4% less context**. In one
> live A/B pair, input tokens fell from 41,058 to 34,820—**15.2% fewer**—with a
> field-exact final report.

> That live result is one pair, not a mean or a dollar-cost claim. Guarded
> repeat replay is our next gate, and we will not present its 85% target as a
> result. What is live today is the proxy, LIGHTEN, the fair-race harness, the
> stage, and the economics receipt.

Then continue at **1:54** with the Agent Economics Receipt. This remains under
three minutes.

### Generic miss

Use this result state instead of a savings headline:

> Our final run measured **{{ACTUAL_PCT}}** against a **{{TARGET_PCT}}**
> acceptance gate. All **{{ACTUAL_CORRECT_FIELDS}}** graded fields were correct.
> We are showing what happened, not what we hoped. The control plane and receipt
> are live; the optimizer remains in validation.

## Delivery rules

- Do not expose `/health` while it advertises stub layers. After the optimizer
  merge updates that response, an optional two-second HEAD check may replace
  part of the config beat.
- Reveal raw dollars before percentages; pause three seconds after the repeat
  result.
- Never say the two-minute race is running live on stage. Say “moments ago from
  this exact commit.”
- Never say “zero hallucinations,” “guaranteed savings,” or “enterprise-ready.”
- At 1:54 open Snowflake. At 2:18 stop technical detail. At 2:42 close.
