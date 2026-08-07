# Judge Q&A

Answer in under 25 seconds. Lead with the distinction, then point to a measured
artifact.

## “What is Amortize?”

Amortize is the cost-control plane for enterprise AI agents. It sits between an
agent and its model, reduces avoidable context, reuses verified procedures, and
records cost plus output quality in Snowflake.

## “Isn't this just prompt caching?”

Prompt caching discounts repeated provider-side prefixes. LIGHTEN changes what
needs to enter context. AMORTIZE can replace a full agent loop with guarded code
execution. We record cache reads separately, so Amortize can benefit from both.

## “Isn't this an agent-memory product?”

Memory retrieves prior information. Amortize uses Cases and Skills to improve
task economics. The key output is not a memory hit—it is a lower cost per
successful task with parity evidence.

## “How do you know the cheaper output is correct?”

Savings do not count without quality. The fixture has deterministic ground
truth and field-exact grading across 120 fields. Candidate Skills never replay;
verified Skills still run guards and fall back to the full agent on failure.

## “Why is Snowflake essential?”

Optimization introduces internal discovery calls, replay steps, and grades that
a provider invoice cannot explain. Snowflake is the auditable economic record
behind cost per successful task and the data foundation for budgets, routing,
governance, and chargeback.

## “Why would a large company buy this?”

Large companies need more than a cheaper API call. They need attribution,
quality proof, policy, reusable procedures, and a path to charge costs across
teams. Amortize starts with measurable savings and expands into that control
plane.

## “Who is the user and who is the buyer?”

The user is an AI platform engineer running tool-heavy agents. The buyer is the
leader accountable for model spend and reliability: VP Engineering, Head of AI
Platform, or FinOps.

## “What is your first enterprise workflow?”

Structured, repetitive tasks with a deterministic quality contract: support
triage, incident playbooks, invoice reconciliation, release checklists, and
recurring code maintenance.

## “What happens if the optimizer breaks?”

Optimization is fail-open. The original full request is retried. Unsupported
or streaming paths can pass through untouched, and ledger writes can degrade to
the schema-compatible SQLite backend.

## “Does it work with existing agents?”

The proxy exposes OpenAI-compatible and Anthropic-compatible routes. Adoption
is a base-URL change. The repository also has Claude Code gateway conformance
checks, while the live demo uses Novita's OpenAI-compatible endpoint.

## “Where does Voice Cursor fit?”

Voice is an optional input, not the optimizer. It can trigger an existing
compatible agent through the same proxy. The result and Snowflake trace—not the
voice interaction—are the proof.

## “What is the business model?”

The open-source local proxy is the wedge. A paid team control plane can add
shared Skill governance, policy, budgets, retention, managed analytics,
chargeback, and enterprise identity controls. That is a hypothesis, not current
revenue.

## “What is the moat?”

The compounding combination of verified procedures and cross-run economic
evidence. A gateway sees traffic; Amortize learns which procedures are safe to
reuse and exactly how much successful reuse saves.

## “What is built versus roadmap?”

Use the final `BUILD_REPORT.md`. The transparent proxy, compatible routes,
Novita demo harness, parity grader, Snowflake/SQLite ledger, and memory adapter
are real. Describe LIGHTEN, AMORTIZE, and stage only according to their final
acceptance results. SSO, RBAC, budgets, and chargeback are product direction.

## “What if models become much cheaper?”

Cheaper models expand agent volume, tool use, and context. Enterprises still
need to avoid recomputing known work and attribute cost to successful outcomes
across providers. The control problem grows with adoption.

## “What would you build next?”

More deterministic enterprise tasks and continuous parity evaluation, followed
by shared Skill governance, task-aware model routing, budgets, and chargeback.
