# Positioning and wording guide

## Category

**Amortize is the cost-control plane for enterprise AI agents.**

Do not lead with “agent memory,” “observability,” or “gateway.” They are
mechanisms or adjacent categories. Lead with lower, auditable cost per
successful agent task.

## Reference pattern: TencentDB Agent Memory

The [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)
README is effective because it starts with a practical repeat-work question,
turns experience into named assets, shows product media early, supports the
story with a benchmark, and states limitations.

Use that structure without copying wording or implying feature parity.

| TencentDB Agent Memory | Amortize |
|---|---|
| Team-level memory hub | Enterprise agent cost-control plane |
| Preserves chat, skills, docs, and code knowledge | Reduces avoidable work and reuses guarded procedures |
| Primary outcome: agents inherit experience | Primary outcome: lower cost per successful task |
| Control surface: memory assets and access | Control surface: economics, quality, and fallback evidence |
| Database anchor: TencentDB | Economic ledger: Snowflake with SQLite fallback |

The products can be complementary. Memory supplies reusable experience;
Amortize measures whether using it safely improves task economics.

## Message hierarchy

1. **Concrete problem:** the same 30-ticket workflow starts over at full cost.
2. **Product:** one self-hosted model endpoint.
3. **Mechanism:** LIGHTEN, REPLAY, PROVE.
4. **Proof:** raw cost, measured reduction, parity, ground-truth accuracy.
5. **Receipt:** Snowflake economics plus signed report, joined by run ID.
6. **Buyer:** AI platform and FinOps leaders.
7. **Expansion:** shared Skills, governance, budgets, and chargeback.

## Approved lines

- Repeated agent work should get cheaper with experience.
- The cost drops. The graded output doesn't.
- Don't trust the percentage. Query it.
- Agents learn. Their economics don't.
- Companies don't buy tokens. They buy completed work.
- AI agents should have a learning curve—and finance should have the receipt.
- One endpoint. Same graded output. Measured economics.
- One endpoint. Same graded output. Lower measured cost. *(Use after the
  end-to-end cost gate passes.)*
- Cost per successful task—not just cost per million tokens.

## Avoid

- “Revolutionary AI optimization platform.”
- “Zero hallucinations.”
- “Guaranteed 85% savings.”
- “Any agent” when only supported compatible paths are proven.
- “Same answer” when the proof is a 120-field structured output contract.
- “Snowflake stores parity” until grade events are actually persisted there.
- “Enterprise-ready” before auth, tenancy, data controls, and HA ship.
- Any percentage copied from an acceptance target or older commit.

## Naming the three acts

Use this order in launch visuals:

```text
LIGHTEN new work
REPLAY verified repeats
PROVE every claim
```

`AMORTIZE` remains the product name and may describe the underlying layer in
technical docs. `REPLAY` is clearer on stage.

## Proof order

```text
completed workflow → repeat cost reset → one endpoint → fair race
→ raw dollars → reduction → parity + accuracy → receipt → enterprise path
```

Do not open or close with architecture. Open with the economic reset and close
with the verified result.
