# AMORTIZE

## Enterprise AI agents should improve their unit economics over time

### Product

Amortize is a transparent cost-control proxy for enterprise AI agents. It
reduces unnecessary context on new tasks, reuses verified procedures on repeat
tasks, and records cost and output-quality evidence in Snowflake.

### Problem

Tool-using agents create three forms of waste:

- large tool catalogues are repeatedly included in model context;
- successful workflows are rediscovered instead of reused;
- spend is difficult to attribute to a task, step, tool, or quality outcome.

The result is a provider bill without reliable cost per successful business
task.

### Solution

| Capability | Control |
|---|---|
| Selective context | Discover full tool schemas only when needed |
| Result spill | Keep large results behind readable, retrievable handles |
| Verified reuse | Promote agreeing successful Cases into guarded Skills |
| Safe fallback | Retry the original full agent path on optimization failure |
| Economic ledger | Record tokens, cost, steps, parity, and accuracy in Snowflake |

### Integration

```text
Existing agent → change one base URL → Amortize → existing model provider
```

OpenAI-compatible and Anthropic-compatible surfaces are supported by the
current proxy. SQLite mirrors the ledger schema for local development and
resilient fallback.

### Initial customer profile

**User:** AI platform engineer or agent-infrastructure team.

**Buyer:** VP Engineering, Head of AI Platform, or FinOps leader.

**Environment:** repeated, tool-heavy workflows with measurable structured
outputs.

Initial use cases:

- customer-support triage;
- incident-response playbooks;
- recurring code-maintenance tasks;
- invoice and reconciliation workflows;
- compliance and release checklists;
- scheduled research and reporting.

### ROI model

```text
monthly avoidable spend
= agent runs per month
× repeatable-workflow share
× avoidable cost per run
```

Amortize reports the final variable from measured direct-versus-optimized runs.
Do not use an illustrative ROI calculation as product evidence.

### Why Snowflake

Optimization introduces internal discovery calls, replays, and grades that a
provider invoice cannot explain. Snowflake becomes the auditable ledger for cost
per agent task and the data layer for future budgets, routing, governance, and
chargeback.

### Business model hypothesis

- **Open source:** local proxy, SQLite fallback, developer proof dashboard.
- **Team:** shared verified Skills, policy, managed reporting, retention.
- **Enterprise direction:** SSO/RBAC, budgets, chargeback, compliance controls,
  and fleet analytics.

Only the first layer is represented by the current repository; paid tiers are a
go-to-market hypothesis.

### Defensibility

The compounding asset is not a generic chat history. It is the combination of:

- versioned, verified procedures;
- task-level cost and quality history;
- provider-independent traffic integration;
- evidence about when reuse is safe and economically valuable.

### Current evidence

The live control run achieves exact 120-field parity and correct ground truth
across direct/proxied and cold/warm cells. Final savings percentages remain
truth-locked until the optimizer acceptance gates pass.
