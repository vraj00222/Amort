# Judge Q&A

Answer each in under 25 seconds. Lead with the distinction, then point to one
measured artifact.

## “What is Amortize?”

Amortize is the cost-control plane for enterprise AI agents. It sits between a
supported agent client and its model, creates a place to reduce avoidable work,
and measures cost per successful task.

## “What is actually built?”

The compatible proxy, Novita live harness, 120-field grader, Snowflake/SQLite
ledger, memory adapter, dashboard, and live/replay projector stage are built.
LIGHTEN is merged and acceptance-green at 65.4% less schema context; one live
pair used 15.2% fewer input tokens with field-exact parity. Guarded Skill
replay remains behind its executable gate.

## “Isn't this just prompt caching?”

Prompt caching discounts provider-recognized repeated prefixes. LIGHTEN is
designed to change what enters context. REPLAY is designed to avoid a full
agent loop with guarded execution. Cache reads can coexist with both and must
be counted separately.

## “Isn't this an agent-memory product?”

Memory retrieves prior information. Amortize uses Cases and Skills as inputs to
task economics. The output is not a memory hit; it is lower measured cost per
successful task, with a quality verdict and fallback history.

## “How do you know the cheaper output is correct?”

The fixture has deterministic ground truth and field-exact grading across 120
fields. We show parity and ground-truth accuracy. If either fails, the saving is
invalid. Matching two wrong answers would not pass.

## “Does the percentage include internal optimizer calls?”

Yes—that is part of the acceptance contract. Discovery, compilation, binding,
and verification calls count toward Amortize's total. Otherwise the comparison
would hide the real cost of optimization.

## “How is the race fair?”

Both lanes use the same final commit, model, 30 tickets, eight tools, prompt,
output budget, and 120-field grader. We compare direct versus Amortize for new
and repeated work and join the evidence by run ID.

## “How many repeats until a Skill pays back?”

We calculate break-even as one-time compilation cost divided by the difference
between direct repeat cost and guarded replay cost. The final demo must show the
measured inputs; we will not invent a generic break-even number.

## “How is dollar cost calculated?”

Token counts are multiplied by the checked-in model pricing table, with the
model and price source disclosed. The report also labels simulated estimates,
and public claims require a live `simulated:false` run.

## “Why is Snowflake essential?”

Provider invoices cannot explain internal optimization steps or cost per
business task. Snowflake makes run and step economics queryable by platform and
finance teams and supplies the foundation for budgets, routing, governance, and
chargeback.

## “Is parity stored in Snowflake today?”

Not reliably as its own grade event in this build. Snowflake stores the run and
step economics; the signed demo report stores parity and accuracy. We show both
with the same run ID rather than overstate the current schema path.

## “Why would a large company buy this?”

They need more than a cheaper API call: attribution, quality proof, safe reuse,
policy, and a path to charge costs across teams. We land with one measurable
workflow and expand only after the economics are proven.

## “Who is the user and buyer?”

The user is the AI platform engineer operating tool-heavy agents. The buyer is
the leader accountable for model spend and reliability: Head of AI Platform,
VP Engineering, or FinOps.

## “What is the first workflow?”

Deterministic, structured, read-heavy work: support triage, incident
classification, reconciliation review, release checklists, and recurring
analysis. These provide a real quality contract and a safe reuse boundary.

## “Would you replay money-moving or destructive actions?”

Not with today's controls. Side-effecting Skills need idempotency, explicit
approval, action policy, and stronger audit guarantees. Our first wedge avoids
those workflows.

## “What invalidates a Skill?”

A model, tool, schema, policy, or output-contract change should invalidate or
re-verify it. A guard failure falls back to the full path and becomes evidence
for whether the Skill should be demoted.

## “What happens if optimization breaks?”

Optimization is fail-open: retry the original full request. Unsupported shapes
pass through, and ledger writes can degrade to the schema-compatible SQLite
backend. A failed optimization is visible, not converted into a fake saving.

## “Does the proxy add latency or become a single point of failure?”

It adds a network/control hop, which we measure. The local technical preview is
not yet a production HA service. Enterprise direction includes redundant
deployment, health checks, timeout policy, bypass, and VPC operation.

## “Does it work with existing agents?”

The proxy exposes OpenAI Chat Completions and Anthropic Messages surfaces. The
Claude Code gateway path is tested, and the live demo uses Novita. We say
“supported compatible clients,” because protocol passthrough is broader than
the optimizer's current coverage.

## “Why Snowflake instead of Postgres?”

The local path uses SQLite for frictionless development. Snowflake is the
enterprise analytics destination: finance and platform teams can query spend,
join organizational data, govern access, and build budgets or chargeback in a
system they already use.

## “Where does Voice Cursor fit?”

Voice is an optional presentation/control input, not the optimizer or proof. It
can reveal an already measured stage state through an allowlisted local
command. The report and ledger—not the voice moment—remain the evidence.

## “What data is persisted?”

The ledger stores run/step economics and metadata. Local/EverOS Cases may store
prompts, tool arguments/results, and outputs. Production requires redaction,
retention, encryption, tenant isolation, and access controls; we call those
roadmap, not shipped features.

## “What is the business model?”

The open-source self-hosted proxy is the wedge. A paid team/enterprise control
plane can add shared Skill governance, policy, budgets, retention, managed
analytics, chargeback, identity, and VPC deployment. That is a hypothesis, not
current revenue.

## “Who signs the first contract?”

An AI platform leader with a repetitive workflow and visible model spend. The
initial offer is a measured cost-per-success engagement; the expansion is an
annual control-plane contract after savings are proven.

## “What is the moat?”

The compounding customer-specific map from task fingerprint, to verified
procedure, to realized savings, to fallback history. A gateway sees traffic;
Amortize learns when reuse is both safe and economically valuable.

## “What if models become much cheaper?”

Cheaper models expand agent volume, tools, and context. Companies still need to
avoid recomputing known work and attribute cost to successful outcomes across
providers. The control problem grows with adoption.

## “What would you build next?”

Finish and truth-lock guarded REPLAY, rerun the complete four-cell launch race,
persist quality grade events, and measure break-even across more workflows;
then add shared Skill policy, task-aware routing, budgets, and chargeback.
