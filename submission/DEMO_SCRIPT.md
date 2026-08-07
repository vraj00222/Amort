# Exact three-minute demo sequence

The complete direct/Amortize × new/repeat race is run immediately before the
pitch. The presentation reveals that fresh result; it never pretends a
two-minute experiment is completing inside a three-minute talk.

## Before speaking

**Terminal A — leave running**

```bash
uv run amort up
```

**Terminal B — run and leave the stage open**

```bash
uv run amort demo --task ticket_triage --live --stage
```

Open and pin:

- stage: `http://127.0.0.1:4700`;
- one-line base URL diff;
- cold and repeat result states;
- Snowflake rows for the exact run ID;
- matching report quality fields;
- final enterprise/close slide;
- backup clip from the same SHA.

## 0:00–0:15 — Repeat-cost reset

**Show:** `30 tickets complete`, then the same direct task beginning again.

**Say:**

> This agent just triaged 30 support tickets. Ask it to repeat tomorrow, and
> the company pays it to reload every tool and rediscover the same procedure.
> Agents learn. Their economics don't.

## 0:15–0:31 — Product reveal

**Show:** agent → Amortize → model.

**Say:**

> Amortize is the cost-control plane for enterprise AI agents. We reduce
> avoidable context on new work, reuse guarded procedures on repeats, and
> measure cost per successful task.

## 0:31–0:44 — One endpoint

**Show:**

```diff
- base_url = provider
+ base_url = http://127.0.0.1:4000/v1
```

**Say:**

> This is the entire integration. Same client. Same model interface. Same eight
> tools. One base URL now routes the workflow through Amortize.

Do not show `/health` until it no longer advertises stub layers.

## 0:44–0:58 — Fair-race contract

**Show:** direct vs Amortize, new vs repeat.

**Say:**

> We ran this comparison moments ago: same model, same 30 tickets, same tools,
> same prompt, and the same 120-field ground-truth grader.

## 0:58–1:26 — New-task result

**Reveal in order:** Direct cost → Amortize cost → reduction → parity →
accuracy.

```text
Direct      {{DIRECT_COLD_COST_USD}}
Amortize    {{AMORTIZE_COLD_COST_USD}}
Cost        {{L1_COST_REDUCTION_PCT}} lower
Context     {{L1_SCHEMA_REDUCTION_PCT}} less schema context
Parity      {{COLD_PARITY_FIELDS}} / 120 identical
Accuracy    {{COLD_ACCURACY_FIELDS}} / 120 correct
```

Do not celebrate before the accuracy line appears.

## 1:26–1:54 — Repeat result

**Reveal in order:** Direct cost reset → verified Skill + guard state →
Amortize cost → reduction → quality seal.

```text
Direct      {{DIRECT_WARM_COST_USD}}
Amortize    {{AMORTIZE_WARM_COST_USD}}
Cost        {{L2_WARM_COST_REDUCTION_PCT}} lower
Parity      {{WARM_PARITY_FIELDS}} / 120 identical
Accuracy    {{WARM_ACCURACY_FIELDS}} / 120 correct
```

Only show a verified Skill label if the final run produced a real Skill ID.

**If REPLAY is still pending:** do not show the repeat-cost template. Keep the
verified LIGHTEN frame onscreen and say:

> The current gate is 1,497 to 518 estimated schema tokens—65.4% less. One live
> pair used 41,058 versus 34,820 input tokens—15.2% fewer—with field-exact
> parity. Repeat replay is next; its 85% target is not a result.

## 1:54–2:18 — Agent Economics Receipt

**Show:** `{{RUN_ID}}` in Snowflake and the same ID in the signed report.

**Say:**

> Don't trust the percentage. Query it. Snowflake records the calls, tools,
> tokens, dollars, and backend behind this run. The signed report records parity
> and accuracy. Together they turn model spend into cost per successful task.

Highlight; do not edit SQL or scroll.

## 2:18–2:42 — Enterprise motion

**Show:** one workflow → one platform team → enterprise agent fleet.

**Say:**

> We land with one repetitive workflow and one AI platform engineer. Once the
> economics are proven, the paid control plane expands into shared Skills,
> policy, budgets, chargeback, and fleet analytics.

Label the expansion features `PRODUCT DIRECTION`.

## 2:42–3:00 — Close

**Show:** winning cost result, `120/120 correct`, Amortize, repository URL.

**Say:**

> Companies don't buy tokens. They buy completed work. AI agents should have a
> learning curve—and finance should have the receipt. Amortize. The cost drops.
> The graded output doesn't.

Stop speaking at 3:00.

## Acceptance

- [ ] Full live four-cell race completed immediately before presenting
- [ ] Same SHA in report, script, screenshot, deck, and backup
- [ ] `simulated: false`
- [ ] Correct model and backend visible
- [ ] Cold and repeat parity pass
- [ ] Ground-truth accuracy passes
- [ ] Internal optimizer usage is included
- [ ] No acceptance target is displayed as an achieved result

## Never show

- credentials, shell history, `.env`, PATs, or account identifiers;
- `/health` while it advertises stub layers;
- an unverified Skill;
- scrolling logs or SQL editing;
- roadmap features as shipped;
- results from a different commit;
- language implying the pre-run race is executing live on stage.
