# Voice cursor integration

## Recommendation

Yes—voice control can improve the launch demo, but it should control the
presentation, not serve as proof of cost savings. The strongest version is a
local, optional command layer over the stage view:

```text
“show the new run”     → reveal cold result
“show the repeat”      → reveal guarded replay result
“show the receipt”     → switch to Snowflake/report proof
“show the business”    → reveal land-and-expand state
“reset demo”           → return to opening state
```

This adds theatrical polish without changing the measured experiment. The
numbers still come only from `demo_report.json` and ledger rows.

## Best integration point

The current stage is a local FastAPI page at `http://127.0.0.1:4700` with an
SSE stream at `/events`. After the implementation workstreams freeze:

1. Add a small local-only command endpoint such as `POST /control`.
2. Map a fixed allowlist of commands to stage reveal states.
3. Use browser speech recognition or a local speech-to-text process to send
   only those commands.
4. Keep the keyboard/OBS scene controls as the primary fallback.

Do not put arbitrary spoken text into a shell, SQL worksheet, or model prompt.
The voice layer should never execute commands outside the fixed presentation
allowlist.

## Demo choreography

Use at most one voice moment, around **1:26**:

> “Amortize, show the repeat.”

The stage reveals the already measured repeat result. The presenter then says:

> “Voice changed the view. It did not generate the evidence.”

This prevents judges from confusing a rehearsed interface control with a live
two-minute benchmark.

## Production guardrails

- local-only binding (`127.0.0.1`);
- explicit command allowlist;
- visual confirmation before any state change;
- push-to-talk or wake phrase to avoid accidental triggers;
- no secrets, prompts, or tool outputs in speech-provider logs;
- keyboard/scene fallback that works with voice disabled;
- optional feature flag, off by default.

## Go / no-go rule

Use voice in the final pitch only after ten consecutive rehearsal passes in a
noisy room. If any command misfires, remove it from the live path and keep it in
the recorded 75-second video as a clearly labeled presentation control.
