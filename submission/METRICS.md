# Verified metrics — submission truth lock

This file separates **measured**, **target**, and **proposed** claims. The pitch,
slides, README hero, and video must all use the same final row.

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

## Acceptance targets—not achieved claims

| Gate | Target | Executable source |
|---|---:|---|
| Layer 1 schema reduction | ≥60% | `scripts/accept_layer1.py` |
| Layer 2 warm cost reduction | ≥85% | `scripts/accept_layer2.py` |
| Output quality | Field-exact parity and correct ground truth | demo grader + acceptance scripts |

## Final submission run

Populate only after both implementation merges and a clean live run.

```yaml
commit_sha: TBD
run_started_at: TBD
model: TBD
ledger_backend: TBD
memory_backend: TBD
simulated: false

direct_cold:
  run_id: TBD
  input_tokens: TBD
  output_tokens: TBD
  cost_usd: TBD
  wall_ms: TBD

amortize_cold:
  run_id: TBD
  input_tokens: TBD
  output_tokens: TBD
  cost_usd: TBD
  wall_ms: TBD

direct_warm:
  run_id: TBD
  input_tokens: TBD
  output_tokens: TBD
  cost_usd: TBD
  wall_ms: TBD

amortize_warm:
  run_id: TBD
  input_tokens: TBD
  output_tokens: TBD
  cost_usd: TBD
  wall_ms: TBD

layer1_schema_reduction_pct: TBD
layer1_end_to_end_cost_delta_pct: TBD
layer2_warm_cost_reduction_pct: TBD
cold_parity_fields: TBD
warm_parity_fields: TBD
accuracy: TBD
```

## Calculation definitions

```text
Layer 1 end-to-end cost reduction
  = (direct_cold_cost - amortize_cold_cost) / direct_cold_cost × 100

Layer 2 warm cost reduction
  = (direct_warm_cost - amortize_warm_cost) / direct_warm_cost × 100
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
- [ ] Ground-truth accuracy passes
- [ ] Script tokens replaced
- [ ] Slide result source line updated
- [ ] Video captions match this file
