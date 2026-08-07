# CHANGELOG-AGENTS

*Per-branch log of what changed and which files were touched, written for the next agent or
contributor picking this repo up. Append a section per branch; do not rewrite earlier ones.
`CONTRACTS.md` remains the authority on interfaces and ownership — this file records what actually
landed and why.*

---

## branch `abhishek` — teammate hand-off tracks 1–4

Scope taken from the hand-off list: **stage view design pass**, **dashboard styling**, **a second
demo task module**, **docs + friction**. No implementation of Layer 1 or Layer 2.

### Boundaries respected

Not touched, per the hand-off boundaries and `CONTRACTS.md`:
`amort/proxy/**`, `amort/skills/**`, `amort/config.py`, `amort/ledger/**`,
`scripts/accept_*.py`, `scripts/gate.sh`, `amort/demo/report.py`.

No new dependencies. No CDN or external assets. No invented numbers — every figure on the stage and
the dashboard is a measured ledger value or arithmetic over two measured values, and the
`simulated` / `replayed` badges are preserved end to end.

### Files touched

| File | Change |
|---|---|
| `amort/demo/stage.html` | rewritten — layout, typography, comparison bars, meter settling |
| `amort/dashboard/app.py` | inline theme, lane-coloured chart, per-lane KPI, richer empty states |
| `amort/demo/tasks/invoice_reconcile.py` | **new** — second demo task |
| `amort/demo/tasks/invoices.json` | **new** — its committed fixture (30 invoices, 26 payments, 2 credit notes) |
| `amort/demo/harness.py` | **one line** — `invoice_reconcile` registered in `TASKS` |
| `README.md` | live-run footgun, second-task section, Layer-1 status corrected, doc links |
| `ACKNOWLEDGEMENTS.md` | **new** — prior art, dependencies, assets, fixtures |
| `CHANGELOG-AGENTS.md` | **new** — this file |

`amort/proxy/lighten.py` and `amort/proxy/interceptors.py` appear in this branch's history
(commit `dba8dc3`, an independent Layer 1 built before Workstream A merged). That work was
**superseded** — the merge of `origin/main` took main's version wholesale, so the branch's final
tree is byte-identical to main for both files. Ignore the commit; read main's implementation.

### 1. Stage view (`amort/demo/stage.html`)

The event contract with `stage.py` is **unchanged** — same `run_start` / `step` / `run_end` /
`parity` / `final` types and fields — so `stage.py` needed no edits and `scripts/test_stage.py`
passes untouched.

- **Comparison bars replace the bottom cell list.** Each lane draws its two runs as horizontal bars
  on a **scale shared across both lanes** (the largest measured run). The shorter bar *is* the
  saving. A per-lane scale would let two equal-length bars mean different numbers, which on a
  projector is a lie by omission.
- **Layout.** The lane is a 6-row grid; ~55% of the surface was previously empty.
- **Meters settle instead of asymptoting.** Both counters now snap once within half a displayed
  unit (tokens `< 0.5`, cost `< 0.00005`). Previously the cost meter eased toward its target
  forever and could sit visibly below the measured value for seconds — bad on a screen whose whole
  claim is that its numbers come from the ledger.
- **Δ per row** — computed from the two lanes' measured run totals, the same arithmetic
  `report.py` does. Shown only once both lanes have reported that mode.
- **Step rail** — one block per step event, blue = model call, outlined = tool call; the only thing
  that moves continuously during a live run. Capped at 240 blocks.
- **Final overlay** — opaque (was translucent, so lanes bled through the number), with the
  comparison named above the figure and `SIMULATED` / `REPLAY` badges in their honesty colours
  (amber / blue). Press `f` or click to toggle.

### 2. Dashboard (`amort/dashboard/app.py`)

- Inline CSS only. Lane colours match `stage.html` (grey = direct, green = amortize) so the two
  screens read as one system.
- The cost line chart is coloured **by lane**, not by series order.
- Headline tile compares **average cost per run** between lanes rather than showing gross spend —
  a lane that merely ran more times previously looked more expensive. `delta_color="inverse"`
  because a falling cost is good. Falls back to gross spend when only one lane has runs.
- Empty states for the `SAVINGS` view and the tool-cost panel now say what is missing and how to
  fill it, instead of a bare caption.

### 3. Second demo task (`invoice_reconcile`)

Reconciles 30 invoices against 26 payments with 8 verbose tools (~1,540 tokens of schema, versus
`ticket_triage`'s ~1,500), so Layer 1's dieting claim is measured against more than one catalogue
shape. Deterministic: every tool is a pure function of the committed `invoices.json`.

**Two things to know before extending it:**

1. **The output list is `lines`, not `report`.** `skills/grader.py` compares a `report` list by
   `REPORT_KEY = "ticket_id"`. A second task emitting `report` would be compared on a field its rows
   do not have — `None` on both sides — and score **parity ✓ having compared nothing**. Naming it
   `lines` routes `grade()` to `_compare_scalar`, exact whole-object comparison. That is why this
   task's parity line reads `1 field` rather than `120`; it is stricter, not weaker. If Workstream B
   ever generalises `REPORT_KEY`, this can be revisited.
2. **Credit notes are the trap.** Four invoices are short-paid; two are fully explained by a credit
   note and are therefore `matched`, not `short_paid`. An agent that skips `lookup_credit_notes`
   gets exactly two rows wrong — a plausible-looking wrong answer, which is what makes the accuracy
   grade worth reading.

Measured offline (`AMORT_LEDGER=sqlite uv run amort demo --task invoice_reconcile --offline`):
37,727 tok direct vs 31,436 through Amortize, **−17%**, parity ✓, accuracy ✓ against ground truth.
Simulated numbers, labelled as such — the offline lane estimates tokens at chars/4.

### 4. Docs

- **README** — documents the live-run footgun below; adds the second-task section; corrects the
  "what is not built yet" entry for Layer 1, which still claimed no dieting existed.
- **ACKNOWLEDGEMENTS.md** — new. Credits Cursor's 46.9% dynamic-tool-discovery result as Layer 1's
  prior art, EverOS for the Case/Skill model, Anthropic's gateway docs, and every runtime
  dependency. Records that no third-party source is vendored.

### Open items for whoever picks this up

1. **`AMORT_UPSTREAM_OPENAI` defaults to `https://api.openai.com`** (`config.py:53`, and
   `.env.example:18` sets it explicitly). The proxy routes `/v1/chat/completions` there, so demo
   lane B and both live acceptance scripts send a Novita key to OpenAI and 401. Documented in the
   README as a required `.env` line; the **real fix is a config default change**, which is
   integrator-owned. Worth doing before demo day.
2. **`amort/demo/report.py`'s explanatory panel is stale.** It still reads *"Both columns are equal
   on purpose … Layer 1 … stubs … which is why it prints 0%"* while printing −15% / −17%. Left
   untouched deliberately: `report.py` is Workstream C's file and an unasked edit invites a
   conflict. Its owner should derive that wording from the measured delta.
3. **Layer 1 does not apply to Claude Code.** The gate excludes streaming and the Anthropic path;
   Claude Code always streams. The "one env var, any client" beat is currently a transparent-proxy
   demo with no dieting. Fine as engineering, but the pitch should not imply otherwise.
4. **`grader.py`'s `REPORT_KEY`/`REPORT_FIELDS` are ticket-triage-specific**, which is what forced
   the `lines` naming above. A per-task key would let future tasks use `report` safely.
