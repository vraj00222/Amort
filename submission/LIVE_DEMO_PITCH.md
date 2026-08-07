# Live playground pitch — word-for-word, with real numbers only

*Surface: http://127.0.0.1:4700 (the playground) + http://localhost:8501 (the dashboard).
Every number you speak is on screen the moment you say it. If a run measures differently,
say what the screen says — the honesty IS the pitch.*

## The 3-minute script

**[Open on the playground page]**

> "Every company racing to be AI-native has the same problem: agents are gold, but they're
> wasteful. An agent re-sends the same tool catalogue on every single turn, and re-does the
> same work on every single run. At Uber's scale that waste is a line item with a lot of zeros.
>
> Amortize is a proxy. One environment variable — no code changes, no SDK swap — and your
> agent traffic flows through it. This page is the whole pitch: same prompt, two paths."

**[Type or keep the prefilled prompt. Hit RUN BOTH. Point left, then right.]**

> "Left lane: the agent exactly as you run it today, straight to Novita. Right lane:
> the identical agent through Amortize. Watch the token meters — these are live API-reported
> numbers, not a recording."

**[While lanes run — point at the feature cards lighting up]**

> "Layer one, LIGHTEN, fires on every prompt: the proxy strips eight verbose tool schemas to
> one-line stubs, and the model pulls a full schema only when it actually needs it. Oversized
> tool results spill to disk with a readable digest. On our live runs that's typically
> double-digit percent off every cold prompt — our recorded run measured **−26% cost** —
> with the output field-for-field identical. The parity check at the bottom proves that;
> it's a grader, not a promise."

**[When the right lane goes warm / the memory diamond pulses]**

> "Layer two, AMORTIZE, is the headline. Every run is remembered as a Case in EverOS — watch
> the memory graph, bottom right: that diamond pulsing is the system recognising it has solved
> this exact task before, from the same node it stored it under. Two runs that agree
> field-exactly get distilled into a verified Skill. Now the repeat doesn't run an agent loop
> at all — it replays the skill as code, with just two small model calls: bind the parameters,
> verify the output."

**[The verdict banner lands — read it out loud, whatever it says. Recent live runs: −97% to −98%.]**

> "**Minus ninety-eight percent. Output verified identical — 120 fields.** And the skill paid
> for itself nine percent of the way into its first repeat — compile cost was five hundredths
> of a cent."

**[Switch to the dashboard]**

> "Layer three is why you can believe layers one and two. Every model call, tool call and
> replay is a row in Snowflake — that's the sponsor line at the top: Novita inference,
> EverOS memory live, Snowflake ledger with the real row count. This is the amortization
> curve: the direct lane stays flat, the Amortize lane bends toward zero as skills form.
> Nothing on either screen can display a number that wasn't measured."

**[Close — the universality beat]**

> "This isn't a framework you adopt. It's one env var. Claude Code, any OpenAI SDK, any
> agent your teams already built — point the base URL at Amortize and the meter starts
> running. That's how a corporation goes AI-native without the bill going exponential."

## Claim sheet (say these, nothing stronger)

| Claim | Number to say | Source |
|---|---|---|
| Layer 1, every prompt | "typically 10–30% off; our recorded run: −26% cost" | METRICS.md, run_23fa5894… |
| Layer 2, repeats | "−97 to −98%, output verified identical" | METRICS.md + live playground runs |
| Break-even | "the skill pays for itself 9% into the first repeat" | METRICS.md (compile $0.00057) |
| Parity | "120 of 120 fields identical, graded not asserted" | grader, on screen |
| NEVER say | a fixed "15–20%" or any number not on screen | iron rule |

## Demo arcs (pick one)

- **Fast (recommended):** skill already in memory → hit RUN BOTH once → right lane goes warm
  → −98% in ~40 seconds. What we verified live today.
- **Full story:** before the demo, delete `.amort/memory/**/skills/skill_*` → first RUN BOTH:
  both lanes cold, Layer-1 delta shows, then "skill distilled" appears in the memory strip →
  RUN BOTH again: warm, −98%. Two submits, ~2.5 minutes.
- **Wifi dead:** `uv run amort demo --offline --stage --replay demo_report.json` (page at
  :4700/stage) — replays the recorded live run, labelled as a replay.

## Video demo shot list (record from the playground)

1. 0:00 Cold open on the page title: "same prompt, two paths, real numbers."
2. 0:05 Type the prompt, hit RUN BOTH — split-screen meters climbing, Novita badge pulsing.
3. 0:25 Feature card close-ups as they light: LIGHTEN → AMORTIZE → PROVE.
4. 0:40 The memory diamond pulse + "skill recalled — replaying as code."
5. 0:50 Verdict banner lands: "−98.1% tokens · output verified identical ✓" — hold 3s.
6. 0:55 Dashboard: sponsor line, amortization curve bending down, skills table.
7. 1:10 Terminal: `export ANTHROPIC_BASE_URL=http://127.0.0.1:4000` + Claude Code `/status`.
8. 1:20 End card: real numbers from METRICS.md + repo URL.
Caption every number with its run_id (METRICS.md has them). No number in the edit that
isn't in the truth-lock.
