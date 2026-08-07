# Judge Q&A

Keep answers under 25 seconds. Lead with the distinction, then point to evidence.

## “Isn't this just prompt caching?”

No. Prompt caching discounts repeated provider-side prefixes. LIGHTEN reduces
the context that must be sent by discovering tools on demand. AMORTIZE can avoid
the full agent loop by replaying a verified procedure as guarded code. We still
record cache-read tokens, so Amortize can benefit from prompt caching too.

## “How do you know a cheaper answer is still correct?”

Savings do not count without quality. The demo has deterministic ground truth
and field-exact parity across 120 fields. Candidate Skills never replay; verified
Skills run guards and fall back to the full agent if anything is wrong.

## “Why is Snowflake essential?”

The optimizations introduce internal model calls and replay steps that a normal
API bill cannot explain. Snowflake is the auditable economic record across runs,
steps, tools, models, agents, and teams. It powers the percentage, parity trail,
budgets, and future chargeback—not just a dashboard screenshot.

## “What happens if the proxy breaks?”

Optimization is fail-open. The original request is retried with the full tool
catalogue. Streaming and unsupported request shapes remain transparent. Ledger
writes can degrade to the schema-compatible local SQLite backend.

## “Does it work with existing agents?”

The proxy exposes OpenAI-compatible `/v1/chat/completions` and Anthropic-compatible
`/v1/messages`. Adoption is a base-URL change. The repository includes gateway
compatibility checks for Claude Code, and the demo uses Novita's OpenAI-compatible
endpoint.

## “Where does Voice Cursor fit?”

Voice is an optional input layer, not the optimizer. It can trigger an existing
compatible agent, which routes through the same Amortize proxy. The wow moment is
that voice, CLI, IDE, and application traffic all create the same measurable
Snowflake economic trace.

## “What is the business model?”

The local proxy can remain an open-source adoption wedge. The paid team control
plane adds shared verified Skills, governance, spend budgets, routing policy,
fleet analytics, and chargeback. Pricing is a hypothesis until validated; do
not claim current revenue or customers.

## “Who pays?”

Engineering and operations teams running repetitive agent workflows—support
triage, code maintenance, incident response, finance operations, and research.
The economic buyer is the leader accountable for model spend and reliability.

## “What is the moat?”

The compounding dataset of verified Cases and Skills, plus the cross-provider
economic ledger. A generic gateway sees requests; Amortize learns which
procedures are safely reusable and has parity evidence for each promotion.

## “What is built versus roadmap?”

Use `BUILD_REPORT.md` from the final commit. Today the transparent proxy,
OpenAI/Anthropic routes, Novita demo harness, parity grader, Snowflake/SQLite
ledger, and EverOS/local memory are real. Describe LIGHTEN, AMORTIZE, and stage
only according to their final acceptance results.

## “Why will this matter if models get cheaper?”

Cheaper models expand agent usage, tool counts, and context volume. Teams still
need to stop recomputing identical work, and they need an economic record across
models. Amortization becomes more valuable as agents become more ubiquitous.

## “What would you build next?”

First, more deterministic task families and continuous parity evaluation. Then
team policy, model routing using measured task economics, shared Skill promotion,
and chargeback on the Snowflake ledger.
