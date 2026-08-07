# Positioning and wording guide

## Category

**Amortize is the cost-control plane for enterprise AI agents.**

Do not lead with “agent memory,” “observability,” or “gateway.” They are
mechanisms or adjacent categories. Lead with the business outcome: lower,
auditable cost per successful agent task.

## Reference pattern: TencentDB Agent Memory

The [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)
README is effective because it:

1. starts from one practical question about repetitive agent work;
2. turns an abstract concept into named, reusable assets;
3. frames the product as a team control plane, not a database table;
4. demonstrates workflow and UI before deep implementation detail;
5. supports the story with a benchmark and explicit current limitations.

We should use that structure, not copy its sentences or claim its capabilities.

## Clear separation

| TencentDB Agent Memory | Amortize |
|---|---|
| Team-level memory hub | Enterprise agent cost-control plane |
| Preserves chat, skills, docs, and code knowledge | Reduces context and reuses verified procedures |
| Primary outcome: agents inherit experience | Primary outcome: lower cost per successful task |
| Control surface: memory assets and access | Control surface: economics, parity, and replay evidence |
| Database anchor: TencentDB | Economic ledger: Snowflake with SQLite fallback |

The products can be complementary. Memory supplies reusable experience;
Amortize measures whether reusing it safely improves task economics.

## Message hierarchy

1. **Problem:** agents pay repeatedly for known context and procedures.
2. **Product:** one transparent base-URL proxy.
3. **Mechanism:** LIGHTEN, AMORTIZE, PROVE.
4. **Proof:** direct-versus-optimized cost with exact parity.
5. **Buyer:** AI platform and FinOps leaders.
6. **Expansion:** governance, budgets, routing, and chargeback.

## Approved lines

- Every agent run should get cheaper with experience.
- The cost drops. The answer doesn't.
- Do not trust the percentage. Query it.
- The company should not pay twice for reasoning it already owns.
- One base URL. Same agent. Same answer. Lower measured cost.
- Cost per successful task—not just cost per million tokens.

## Avoid

- “Revolutionary AI optimization platform.”
- “Zero hallucinations.”
- “Guaranteed 85% savings.”
- “Enterprise-ready” before auth, tenancy, and governance ship.
- “AI memory, routing, observability, and governance platform.”
- Any final percentage copied from a target or prior commit.

## Naming the three layers

Always use the verbs in this order:

```text
LIGHTEN new work
AMORTIZE repeated work
PROVE every claim
```

## Visual proof order

```text
one base URL → fair race → parity → Snowflake rows → enterprise product path
```

Do not open with architecture. Do not close with architecture. Open with the
economic problem and close with the verified result.
