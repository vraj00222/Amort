# Product-launch video plan

Create two cuts from one truth-locked live run:

1. **75-second launch film** for judges, social, and the repository hero.
2. **Three-minute demo backup** cut to the exact beats in
   [PITCH_SCRIPT.md](PITCH_SCRIPT.md).

The creative rule: show a product state change every 8–12 seconds. This should
feel like a launch film with proof, not a screen recording with narration.

The ready-to-import caption track for the current LIGHTEN-only state is
[amortize-product-75s-current.srt](amortize-product-75s-current.srt). Replace it
with the post-REPLAY truth-locked captions only after that gate passes.

## 75-second edit decision list

| Time | Shot | On-screen copy / voice |
|---:|---|---|
| 0:00–0:04 | Actual stage result: `30 tickets complete` | `ONE WORKFLOW. COMPLETED.` |
| 0:04–0:09 | The same direct task starts again; its cost meter resets | `SAME TASK. FULL PRICE AGAIN.` |
| 0:09–0:15 | One-line config diff routes the client to Amortize | “Change one base URL.” |
| 0:15–0:25 | Eight verbose tool schemas collapse into on-demand discovery | `LIGHTEN · PAY ONLY FOR NEEDED CONTEXT` |
| 0:25–0:36 | Two agreeing Cases promote to `VERIFIED`; guards surround replay | `REPLAY · REUSE THE PROCEDURE, NOT THE PROMPT` |
| 0:36–0:50 | Raw cold and repeat dollars land, then measured reductions | Display only final truth-locked values |
| 0:46–0:50 | Quality seal locks in last | `PARITY {{WARM_PARITY_FIELDS}}/120 · CORRECT {{WARM_ACCURACY_FIELDS}}/120` |
| 0:50–1:02 | Matching run ID highlights in Snowflake, then in the signed report | “Don't trust the percentage. Query it.” |
| 1:02–1:10 | One workflow expands into a platform team and enterprise fleet | `SKILLS · POLICY · BUDGETS · CHARGEBACK` · label `PRODUCT DIRECTION` |
| 1:10–1:15 | Product name and repository URL | `THE COST DROPS. THE GRADED OUTPUT DOESN'T.` |

Only show Case-to-Skill promotion if the final report proves a real verified
Skill. Otherwise replace 0:25–0:36 with the fail-open contract and label REPLAY
as `IN FINAL VALIDATION`.

## Opening and closing frames

Do not begin with a logo animation. Begin inside the completed task.

Close on:

```text
AMORTIZE
The cost-control plane for enterprise AI agents

Repeated agent work should get cheaper with experience.
github.com/vraj00222/Amort
```

Hold the final frame for four seconds. No additional voice after the closing
line.

## Truth-locked shot list

- Stage at `http://127.0.0.1:4700` showing the final four-cell result.
- The actual one-line base URL change; all credentials cropped.
- Cold Direct and Amortize raw dollar values.
- Repeat Direct and Amortize raw dollar values.
- Both quality checks: parity **and** ground-truth accuracy.
- Verified Skill ID and guard/fallback state, only if produced by the final run.
- Snowflake row with `RUN_ID`, token fields, `COST_USD`, backend, and model.
- Matching `demo_report.json` fields for parity, accuracy, `simulated`, and SHA.
- Dashboard with the actual backend label visible.
- Repository close frame.

## Product-launch motion language

- Use direct cuts, short 120–180 ms ease-outs, and one restrained highlight
  sweep across the Snowflake row.
- Animate dollars first and percentages second. The viewer should see the
  denominator before the claim.
- Lock the quality seal only after the saving appears. Caption:
  `SAVINGS INVALID UNLESS QUALITY PASSES`.
- Give LIGHTEN one soft compression sound and the quality seal one low,
  confident success tone. Avoid trailer booms and glitch effects.
- Use the deck palette: obsidian, ice blue, electric lime, steel, and amber.
- Never show fake chat typing, stock robots, generic data-center footage, or
  fabricated customer logos.

## Capture setup

- Record at 2560×1440 or higher; deliver 1920×1080, 30 fps.
- Use a 16:9 safe area and 150% terminal zoom.
- Capture clean UI and pointer passes separately from voice.
- Burn in captions; assume the first watch is muted.
- Keep the stage, Snowflake worksheet, report, and final slide in fixed browser
  tabs or numbered OBS scenes. Avoid visible Alt-Tab navigation.
- Show no `.env`, browser password manager, shell history, API key, PAT,
  account identifier, email, or notification.
- Keep raw recordings outside git. Commit only compressed, approved exports.

## Voiceover script for the 75-second cut

> This agent just completed 30 support tickets. Run the same workflow again,
> and the company pays it to rediscover the procedure. Amortize changes one base
> URL. On new work, it reveals only the tool context the model needs. On a
> repeat, it can reuse a verified procedure behind guards and fallback. In our
> controlled race, the same model, tickets, tools, and grader produced these
> measured costs. The saving counts only because all 120 fields stayed correct.
> Snowflake records the run economics; the signed report records the quality
> verdict. Amortize gives enterprise AI teams cost per successful task—and a
> path to Skills, budgets, policy, and chargeback. The cost drops. The graded
> output doesn't.

Replace “can reuse” with “reused” only after the final Skill gate passes.

## Three-minute backup

Use the same screen order, timing, SHA, model, backend, and values as
[PITCH_SCRIPT.md](PITCH_SCRIPT.md). Export with the first frame already loaded
so a teammate can cut to it after 8–12 seconds without an apology or reset.

If guarded REPLAY is still pending, use the verified LIGHTEN state: 1,497 → 518
estimated schema tokens (−65.4%) plus the recorded live pair, 41,058 → 34,820
input tokens (−15.2%) at field-exact parity. Label the live result `ONE PAIR ·
NOT A MEAN OR DOLLAR-COST CLAIM`. Never use an older successful run against a
newer code SHA.

## Thumbnail

Use one result, not a collage:

```text
THE COST DROPS.
THE OUTPUT DOESN'T.

{{L2_WARM_COST_REDUCTION_PCT}} LOWER REPEAT COST
120 / 120 CORRECT
```

If the repeat gate has not passed, use:

```text
120 / 120 CORRECT
THE AGENT ECONOMICS RECEIPT
```

## Export manifest

```text
amortize-product-75s-1080p.mp4
amortize-demo-backup-3m-1080p.mp4
amortize-thumbnail-enterprise.png
amortize-results-final.png
amortize-snowflake-receipt.png
```

Every export filename should be copied into the SHA-named evidence folder in
the runbook.
