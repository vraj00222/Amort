# Hackathon submission copy

## Product name

Amortize

## Tagline

The cost-control plane for enterprise AI agents.

## Memorable line

Every agent run should get cheaper with experience.

## 50-word description

Amortize is a transparent proxy that reduces and audits the cost of enterprise
AI agents. It reveals tool context only when needed, turns successful repeated
work into guarded Skills, and writes every token, dollar, replay, accuracy, and
parity grade into Snowflake. Adoption is one base-URL change.

## 150-word description

Enterprises are deploying AI agents into support, engineering, operations, and
finance, but their unit economics reset on every run. Agents resend large tool
catalogues, reprocess large outputs, and rediscover workflows the company
already paid to solve.

Amortize is a transparent local proxy with three layers. LIGHTEN reduces
avoidable context on new runs through on-demand tool discovery and result
spilling. AMORTIZE converts agreeing successful Cases into guarded, versioned
Skills for repeated work. PROVE writes every model call, tool, replay, token,
cost, accuracy result, and parity grade to a Snowflake-compatible ledger.

The demo runs the same 30-ticket, eight-tool task direct and through Amortize,
cold and repeated, using a deterministic 120-field grader. Savings count only
when parity passes. Teams integrate by changing one model base URL—no agent
rewrite or SDK migration.

## Problem

Agent fleets have no durable unit-economics loop. Context is over-sent,
successful procedures are recomputed, and provider bills cannot explain cost
per successful business task.

## Solution

A fail-open proxy that optimizes new and repeated agent runs and pairs every
savings claim with Snowflake cost and quality evidence.

## Why Snowflake?

Snowflake stores the economic trace across runs, model calls, tools, internal
discovery, replays, tokens, dollars, latency, parity, and accuracy. It powers
the measured comparison today and provides the data foundation for enterprise
budgets, routing, governance, and chargeback.

## Track selection

**Primary: Cost of Intelligence.** The executable gates require a real schema-
token reduction and a real warm-run cost reduction with equal output.

**Secondary: Wildcard.** Amortize creates an agent-economics layer for budgets,
chargeback, routing, and verified procedural reuse.

## Technical differentiation

- One base URL for compatible clients.
- Optimizes context and repeated procedures—not only provider routing.
- Candidate Skills do not replay; guards fail back to the full agent.
- Internal optimization calls are included in usage.
- Savings fail when field-exact parity fails.
- Snowflake and SQLite use the same ledger shape.

## Business path

The open-source local proxy is the adoption wedge. The enterprise control plane
can monetize shared Skill governance, policy, budgets, managed reporting,
retention, SSO/RBAC, chargeback, and fleet analytics. This is a product and
pricing hypothesis, not current revenue.

## Demo steps

1. Show the one-base-URL integration.
2. Run the direct-versus-Amortize cold race.
3. Show schema/cost delta plus exact parity.
4. Show the repeated-task race and verified Skill replay.
5. Query the Snowflake rows behind the percentage.

## Repository evidence

- `BUILD_REPORT.md` — live baseline and engineering log.
- `scripts/accept_layer1.py` — Layer 1 executable claim.
- `scripts/accept_layer2.py` — Layer 2 executable claim.
- `demo_report.json` — final truth source, intentionally gitignored.
