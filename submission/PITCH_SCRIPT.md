# The legendary three-minute pitch

## Title

**AMORTIZE — Compound intelligence, not token bills.**

Target delivery: 2:50–3:00, calm and deliberate. The speaker should not narrate
terminal mechanics. Let the visual prove the mechanics while the words explain
why they matter.

## Truth lock before speaking

Replace these tokens only from the final verified `demo_report.json` and
Snowflake rows:

```text
{{L1_SCHEMA_REDUCTION_PCT}}
{{L1_END_TO_END_COST_DELTA_PCT}}
{{L2_WARM_COST_REDUCTION_PCT}}
{{COLD_PARITY_FIELDS}}
{{WARM_PARITY_FIELDS}}
{{FINAL_MODEL}}
{{LEDGER_BACKEND}}
```

Never turn the acceptance targets—60% and 85%—into achieved numbers unless the
final gates pass.

## Script

### 0:00–0:20 — Hook

**Screen:** Black title slide. One line appears: **AI agents have amnesia. Your
cloud bill does not.**

**Say:**

> Every time an AI agent wakes up, it pays to reread the same tool manuals,
> swallow the same results, and rediscover work it already completed. We pay
> frontier-model prices for digital amnesia.

Pause for half a beat.

> This is Amortize. It makes intelligence compound instead of starting from
> zero on every request.

### 0:20–0:42 — One-switch product reveal

**Screen:** Slide 2, then terminal with the proxy already healthy. Highlight
only `base_url=http://127.0.0.1:4000/v1`.

**Say:**

> Amortize is a transparent local proxy. Change one base URL—no SDK swap, no
> agent rewrite—and every request gets LIGHTEN, AMORTIZE, and PROVE.

> LIGHTEN removes context the model does not need. AMORTIZE turns successful
> repeats into guarded Skills. PROVE writes every token, dollar, and parity
> grade into Snowflake.

### 0:42–1:22 — Demo beat one: LIGHTEN

**Screen:** Start or reveal the cold race: direct versus through Amortize.

**Say:**

> The same real task runs on both sides: triage 30 tickets with eight verbose
> tools and return a 120-field report.

> The left agent receives every tool schema up front. Amortize gives the right
> agent a compact map and hydrates only the tools it asks for. Large results stay
> behind readable handles instead of being repurchased every turn.

**Screen:** Freeze on the cold result and parity check.

> In this run, schema context fell by **{{L1_SCHEMA_REDUCTION_PCT}}**, end-to-end
> cost changed by **{{L1_END_TO_END_COST_DELTA_PCT}}**, and the answer still
> matched **{{COLD_PARITY_FIELDS}} fields**. The cost drops. The answer doesn't.

### 1:22–1:58 — Demo beat two: AMORTIZE

**Screen:** Trigger the same request again. Optional: use Voice Cursor only if
the route has been rehearsed—“Amortize, triage those tickets again.”

**Say:**

> Now we ask again. Normal agents pay again. Amortize turns agreeing successful
> Cases into a verified Skill, binds new parameters, runs the tools as code, and
> verifies the result. If a guard fails, it falls back to the full agent—never a
> confidently wrong shortcut.

**Screen:** Warm result and parity stamp.

> The repeated run was **{{L2_WARM_COST_REDUCTION_PCT}} cheaper**, with
> **{{WARM_PARITY_FIELDS}}-field parity**.

### 1:58–2:25 — Proof, not theatre

**Screen:** Snowflake-backed dashboard. Click one result to show its run and
step rows. Keep the backend label visible.

**Say:**

> Hackathon demos love percentages. Do not trust ours—query it. The Snowflake
> ledger behind this screen records every internal call, token, tool, replay,
> and parity grade.

> Snowflake is our economic control plane: it makes savings auditable and opens
> the door to budgets, chargeback, routing, and verified Skill markets.

### 2:25–2:46 — Product and market

**Screen:** Product ladder: Local proxy → Team control plane → Skill economy.

**Say:**

> The open-source proxy is the wedge. Teams add shared Skills, policy, budgets,
> and chargeback without changing their agents. The buyer is anyone running
> repetitive agent workflows in support, coding, operations, or finance.

### 2:46–3:00 — Close

**Screen:** Final result card: savings, parity, Snowflake receipt. Then the logo
and repository QR code.

**Say:**

> Models will get smarter. Agents will use more tools. Context will get bigger.
> The winning infrastructure will make all of that intelligence reusable.

> Amortize: **compound intelligence, not token bills.**

Stop. Do not add “thank you” over the applause beat.

## Honest fallback if an optimization gate is not green

If either layer misses its threshold, do not fake the headline. Say:

> Our final run measured **{{ACTUAL_PCT}}** with exact parity. The gate was
> **{{TARGET_PCT}}**, so we are showing the result as measured, not as hoped.
> The architecture and ledger make that miss visible—and make the next iteration
> falsifiable.

Then emphasize the passing layer and Snowflake proof. Credibility is the brand.

## Delivery notes

- Speak at roughly 135 words per minute.
- Pause after the hook, after each percentage, and after “the answer doesn't.”
- Never say “basically free,” “zero cost,” or “100% accurate.”
- Do not read commands aloud.
- If the live run takes longer than rehearsed, continue the product explanation
  and cut to the pre-recorded result at the 12-second mark.
