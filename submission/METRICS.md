# Verified metrics — submission truth lock

This file separates **measured**, **target**, and **proposed** claims. The pitch,
slides, README hero, thumbnail, video, Snowflake worksheet, and signed report
must all use the same final run IDs and SHA.

## Current committed live baseline

Source: `BUILD_REPORT.md`, third Novita verification run, commit `f4fca99`.
Backend reported by the run: Snowflake. Memory: EverOS.

| Metric | Direct cold | Amortize cold | Direct warm | Amortize warm |
|---|---:|---:|---:|---:|
| Tokens | 47,523 | 46,866 | 48,150 | 45,491 |
| Cost | $0.008 | $0.008 | $0.008 | $0.008 |
| Wall time | 34.7 s | 30.9 s | 35.0 s | 31.2 s |

Quality evidence:

- Direct cold versus Amortize cold: parity ✓, 120 fields.
- Amortize cold versus Amortize warm: parity ✓, 120 fields.
- Accuracy: all four runs correct against committed ground truth.

Interpretation: this is a valid control but not a savings claim. Both optimizer
layers were stubs, so the small deltas are ordinary run-to-run noise.

Evidence split in the current build:

- Snowflake: run and step economics, model, backend, tokens, dollars, latency,
  Skill ID/output hash fields when populated.
- `demo_report.json`: four-cell result, `simulated`, parity, and ground-truth
  accuracy.

Do not describe parity or accuracy as an already persisted Snowflake grade row
until the harness emits those records after grading.

## Current verified LIGHTEN result

Source: `BUILD_REPORT.md`, Workstream A, repository evidence commit `09e4396`.

| Metric | LIGHTEN off | LIGHTEN on | Result |
|---|---:|---:|---:|
| Eight-tool schema tokens, estimated as chars/4 with stub text included | 1,497 | 518 | **−65.4%** |
| Live input tokens | 41,058 | 34,820 | **−15.2%** |
| Final report | reference | field-exact equal | **parity pass** |

Interpretation: the Layer 1 acceptance gate is green. `BUILD_REPORT.md` records
65.8% from its earlier gate run; the current checkout reruns at 65.4% after the
integration fixes, so public assets use the current lower value. The live
input-token result is one measured pair, not a mean; the build report notes
±10–20% trajectory variance. It is not automatically an end-to-end dollar-cost
claim.

## Acceptance targets—not achieved claims

| Gate | Target | Executable source |
|---|---:|---|
| Layer 1 schema reduction | ≥60% | **PASS: 65.4% current checkout** · `scripts/accept_layer1.py` |
| Layer 2 warm cost reduction | ≥85% | **PASS: 96.7-98.3% across runs** · `scripts/accept_layer2.py` |
| Output quality | Field-exact parity and correct ground truth | demo grader + acceptance scripts |

## Final submission run

Populate only after both implementation merges and a clean live run.

```yaml
commit_sha: a6e9380  # code state of the run (docs-only edits followed in the day-one commit)
run_started_at: "2026-08-07T20:08:07Z"
model: deepseek/deepseek-v4-flash
ledger_backend: snowflake
memory_backend: everos
simulated: false

direct_cold:
  run_id: run_5f4b24f2739949aa
  input_tokens: 42665
  output_tokens: 6038
  cost_usd: 0.008146
  wall_ms: 36486

amortize_cold:
  run_id: run_23fa58949c5e41da
  input_tokens: 27882
  output_tokens: 7093
  cost_usd: 0.005993
  wall_ms: 39797

direct_warm:
  run_id: run_bd69812af669403c
  input_tokens: 33803
  output_tokens: 5600
  cost_usd: 0.006661
  wall_ms: 33528

amortize_warm:
  run_id: run_d788faab9af64b19
  input_tokens: 626
  output_tokens: 473
  cost_usd: 0.00022
  wall_ms: 7258
  skill_id: skl_790ab652c2c2

layer1_schema_reduction_pct: 65.4          # accept_layer1 unit measure, stub text counted
layer1_end_to_end_cost_delta_pct: -26.4    # tokens -28.2; run-to-run noise ~±10 pts — quote as "~25-30%", never a fixed constant
layer2_warm_cost_reduction_pct: -96.7      # tokens -97.2; deterministic replay, stable
cold_parity_fields: 120
cold_accuracy_fields: 120
warm_parity_fields: 120
warm_accuracy_fields: 120
all_cells_ground_truth_pass: true

compile_cost_usd: 0.00056742               # ledger: STEPS name='compile' under run_23fa5894…, 745 in / 1,654 out
direct_repeat_cost_usd: 0.006661
guarded_replay_cost_usd: 0.00022
break_even_repeats: 0.09                   # compile pays for itself 9% into the FIRST repeat
```

## Calculation definitions

```text
Layer 1 end-to-end cost reduction
  = (direct_cold_cost - amortize_cold_cost) / direct_cold_cost × 100

Layer 2 warm cost reduction
  = (direct_warm_cost - amortize_warm_cost) / direct_warm_cost × 100

Break-even repeats
  = compile_cost / (direct_warm_cost - amortize_warm_cost)

Cumulative net saving after N repeats
  = N × direct_warm_cost - compile_cost - N × amortize_warm_cost
```

Schema reduction is calculated by the Layer 1 acceptance test, including the
synthetic discovery tool text. Do not substitute character counts from a slide.

## Final sign-off

- [ ] Final SHA recorded
- [ ] `simulated` is false
- [ ] Model and pricing row verified
- [ ] All internal Layer 1 calls included in usage
- [ ] Snowflake/SQLite backend stated exactly
- [ ] Cold parity passes
- [ ] Warm parity passes
- [ ] 120/120 cold fields correct
- [ ] 120/120 repeat fields correct
- [ ] Ground-truth accuracy passes in all four cells
- [ ] Verified Skill ID exists before showing replay
- [ ] Break-even inputs use measured, all-in costs
- [ ] Snowflake row and report share the displayed run ID
- [ ] Script tokens replaced
- [ ] Slide result source line updated
- [ ] Video captions match this file
- [ ] Thumbnail and README metric ribbon match this file
