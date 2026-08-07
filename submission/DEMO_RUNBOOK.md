# Live demo runbook

Presenter wording and exact on-screen beats live in [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
This file is the operator checklist that makes that two-minute product sequence
reliable.

## The non-negotiable rule

The demo is a measured race, not a magic trick. Every public percentage must be
copied from the final run and tied to its commit SHA. If the live number changes,
the slide changes.

## Current surfaces

| Screen | Route/command | Demo job |
|---|---|---|
| Proxy | `uv run amort up` → `http://127.0.0.1:4000` | Show one-switch compatibility and health |
| Race | `uv run amort demo --task ticket_triage --live` | Produce the direct/proxied × cold/warm comparison |
| Evidence | `uv run amort stats` | Show the ledger rollup |
| Dashboard | `uv run amort dash --port 8501` | Show savings and cost composition |
| Stage | Planned `http://127.0.0.1:4700` | Use only when `--stage` and `amort/demo/stage.py` actually exist |

## Branch protocol while main is moving

Before each rehearsal block:

```bash
git status --short
git fetch origin
git merge origin/main
```

Rules:

- Stay on `sameer` for submission material.
- Do not edit code owned by another workstream from this branch.
- Never force-push.
- Resolve documentation conflicts by preserving newer verified metrics from
  main, then reapply submission wording.
- Re-run the truth lock after every implementation merge.

## T−30 minutes: technical preflight

```bash
uv sync
uv run amort doctor
uv run ruff check amort scripts
uv run python scripts/smoke_proxy.py
uv run python scripts/smoke_ledger.py
```

Then run the acceptance gate appropriate to the merged work:

```bash
uv run python scripts/accept_layer1.py
uv run python scripts/accept_layer2.py
```

Do not expose `.env`, shell history, PATs, API keys, account identifiers, or
browser password managers on the projector.

## T−20 minutes: truth lock

1. Record the exact commit:

   ```bash
   git rev-parse --short HEAD
   ```

2. Run the live 2×2 once without screen recording overhead, immediately before
   presenting. Four real model cells do not fit inside the three-minute pitch;
   the on-stage sequence reveals this fresh truth-locked run.
3. Copy `demo_report.json` to a private timestamped evidence folder outside the
   repository; it is intentionally gitignored.
4. Confirm:
   - all four cells completed;
   - cold parity passes;
   - warm parity passes;
   - ground-truth accuracy passes;
   - backend label is the backend actually used;
   - no number is `simulated: true` for a live claim.
5. Populate [METRICS.md](METRICS.md), then update slide 5 and the script tokens.
6. Capture a screenshot and a backup video from this exact commit.

## T−10 minutes: stage layout

Use three visible surfaces, with notifications and unrelated windows closed:

```text
LEFT 40%       proxy health + concise logs
CENTER 40%     race/stage result
RIGHT 20%      Snowflake-backed dashboard
```

Use 125–150% terminal zoom. Keep API keys off screen. Pin the final result and
Snowflake query in separate browser tabs.

## Live sequence

### Beat 1 — Adoption, 15 seconds

Show the healthy proxy and the one base URL. Do not type setup commands from
scratch.

### Beat 2 — Live proxy proof, 8 seconds

Run `curl -s http://127.0.0.1:4000/health`. Leave after eight seconds.

### Beat 3 — Cold result, 30 seconds

Reveal direct versus Amortize from the fresh pre-run. Explain schema dieting.
Freeze on cost and parity.

### Beat 4 — Repeat result, 30 seconds

Reveal the warm row from the same run. Optional voice input is allowed only as
a rehearsed visual insert, not as evidence that the full run is live.

### Beat 5 — Snowflake receipt, 25 seconds

Open the exact run's rows. Point to total tokens, cost, internal calls, and
parity. Say “query it,” then stop scrolling.

### Beat 6 — Enterprise close, 10 seconds

Show the product ladder and final result. Do not start another agent task.

## Failure ladder

### Level 1 — Live health check is slow

Leave the terminal after eight seconds and reveal the pre-run result.

### Level 2 — Novita or Wi-Fi fails

Use the verified video and Snowflake screenshot. Do not silently switch to
offline numbers.

### Level 3 — Snowflake is unavailable

Show the SQLite backend label and say that writes degrade locally by design.
Use the saved Snowflake screenshot only as prior evidence, clearly labeled.

### Level 4 — An optimization misses parity

Do not show its saving as success. Explain the guard/fallback contract and use
the last truth-locked run. A cheap wrong answer is not a win.

## Presenter hand signals

- Open palm: advance slide.
- Two fingers: cut to backup clip.
- Flat hand: stop live typing and go to results.
- Point at wrist: skip optional voice/client beat and close.

## Final five-minute checklist

- [ ] Final commit and script SHA match
- [ ] Correct model and backend labels visible
- [ ] Backup video opens locally with sound muted by default
- [ ] Dashboard and Snowflake tabs are already loaded
- [ ] Terminal font is readable from the back of the room
- [ ] No notifications, secrets, usernames, or unrelated tabs visible
- [ ] Timer is visible to a teammate, not the audience
