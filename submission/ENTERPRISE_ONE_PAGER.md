# AMORTIZE

## Repetitive enterprise AI work should get cheaper with experience

### Product

Amortize is a self-hosted cost-control proxy for supported enterprise AI
agents. It creates one control point for reducing unnecessary context, reusing
guarded procedures on repeat tasks, and measuring cost per successful task.

### Problem

Enterprises do not buy tokens; they buy completed work. Today, tool-using
agents create three recurring costs:

- large tool catalogues repeatedly enter model context;
- successful workflows are rediscovered instead of reused;
- provider bills cannot attribute spend to a task, step, or quality outcome.

The result is an agent fleet without a durable unit-economics loop.

### Product contract

| Capability | Enterprise control | Current technical-preview state |
|---|---|---|
| Selective context | Reveal full tool schemas only when needed | **Merged; acceptance green: 65.4% less eight-tool schema context on the current gate** |
| Result spill | Keep large results behind readable handles | **Merged with content-hash handles and head/tail/grep reads** |
| Guarded reuse | Promote agreeing Cases into versioned Skills | Recorder/store present; compile/replay stubs pending final gate |
| Safe fallback | Retry the original full path when optimization fails | Product contract encoded in acceptance path |
| Economic ledger | Record run and step tokens, cost, latency, model, and backend | Snowflake + schema-compatible SQLite implemented |
| Quality verdict | Reject savings when parity or ground truth fails | 120-field grader + signed demo report implemented |

### Integration

```text
supported agent → change one base URL → Amortize → compatible model provider
```

The proxy exposes OpenAI Chat Completions and Anthropic Messages surfaces.
Claude Code's gateway path has been tested; the live demo uses Novita's
OpenAI-compatible endpoint. Protocol compatibility is broader than the current
optimizer coverage, so unsupported shapes pass through.

### Agent Economics Receipt

Snowflake records the economic trace across runs and steps. The signed
`demo_report.json` records parity, ground-truth accuracy, the simulated flag,
model, and four-cell race result. The demo joins them by run ID and SHA.

That distinction is intentional: the current repository should not imply
quality grades are already persisted as Snowflake step events.

### Initial customer profile

**User:** AI platform engineer or agent-infrastructure team.

**Buyer:** VP Engineering, Head of AI Platform, or FinOps leader.

**Environment:** repeated, high-volume, tool-heavy workflows with measurable
structured outputs.

Initial safe wedge:

- customer-support triage;
- incident classification and read-heavy playbooks;
- recurring code-maintenance analysis;
- invoice and reconciliation review;
- compliance and release checklists;
- scheduled research and reporting.

Side-effecting or money-moving Skills require idempotency, approvals, and
action-policy controls before replay.

### ROI and break-even

```text
monthly avoidable spend
= runs per month × repeatable share × avoidable cost per successful run

break-even repeats
= one-time compilation cost ÷ (direct repeat cost − guarded replay cost)
```

Every value must come from the final report and ledger. Do not use an
illustrative ROI calculation as product evidence.

### Why Snowflake

Optimization introduces internal discovery, compilation, binding, and
verification calls that a provider invoice cannot explain. Snowflake makes the
economic trace queryable by platform, finance, and governance teams in their
existing data layer—and supplies the foundation for future budgets, routing,
policy, and chargeback.

### Business model hypothesis

- **Open source:** local proxy, SQLite fallback, comparison harness, stage, and
  developer proof dashboard.
- **Team direction:** shared verified Skills, policy, managed reporting, and
  retention.
- **Enterprise direction:** SSO/RBAC, budgets, chargeback, compliance controls,
  VPC deployment, and fleet analytics.

Paid tiers are product direction, not current revenue.

### Land and expand

1. Route one repetitive, measurable workflow.
2. Return a direct-versus-Amortize cost-per-success report.
3. Expand validated controls from one platform team to the agent fleet.

### Defensibility

The compounding asset is not generic chat history. It is the customer-specific
map from task fingerprint, to verified procedure, to realized savings, to
fallback history.

### Current evidence

The committed control (`f4fca99`) achieved 120/120 parity and 120/120 correct
ground-truth fields across the relevant comparisons. Final savings remain
truth-locked until guarded REPLAY passes. LIGHTEN is now merged: its acceptance
evidence shows 65.4% less schema context and, in one live pair, 15.2% fewer
input tokens with field-exact parity (`09e4396`).

### Design-partner call

> Run more than 100,000 tool-using agent tasks a month? Bring us one repeated
> workflow. We will return a measured cost-per-success report and its evidence.
