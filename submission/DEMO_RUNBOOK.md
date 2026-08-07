# Product-launch demo runbook

Presenter wording lives in [PITCH_SCRIPT.md](PITCH_SCRIPT.md). This file is the
operator system for producing a fresh, defensible result and revealing it in
three minutes without visible setup friction.

## Non-negotiable rule

The demo is a measured race, not a magic trick. A public saving must come from
the final live report, include every optimizer call, pass parity and accuracy,
and match the displayed git SHA. If the live number changes, every asset
changes with it.

## Current surfaces

| Surface | Route / command | Launch job |
|---|---|---|
| Proxy | `uv run amort up` → `http://127.0.0.1:4000` | One-endpoint integration |
| Race + stage | `uv run amort demo --task ticket_triage --live --stage` | Four-cell experiment and projector result |
| Stage | `http://127.0.0.1:4700` | Direct vs Amortize reveal; SSE-driven |
| Stage replay | `uv run amort demo --replay demo_report.json` | Network-independent backup |
| Ledger rollup | `uv run amort stats` | Compact economics proof |
| Dashboard | `uv run amort dash --port 8501` → `http://127.0.0.1:8501` | Cost composition and backend label |
| Snowflake | prewritten [DEMO_QUERIES.sql](DEMO_QUERIES.sql) | Exact run and step economics |

The stage route is implemented in `amort/demo/stage.py`; it is no longer a
planned surface.

## Branch protocol while implementation moves

Before every rehearsal block:

```bash
git status --short
git fetch origin --prune
git merge origin/main
git rev-parse --short HEAD
```

- Stay on `sameer` for submission material.
- Preserve implementation changes from `main`; do not reimplement another
  workstream from the submission branch.
- Never force-push.
- After every implementation merge, rerun the gates and regenerate the report,
  screenshots, video overlays, deck metrics, and script numbers as one unit.

## T−45 minutes — code and environment preflight

Use two terminals because `amort up` blocks.

**Terminal A — proxy**

```bash
uv sync
uv run amort up
```

**Terminal B — checks**

```bash
uv run amort doctor
uv run ruff check amort scripts
uv run python scripts/smoke_proxy.py
uv run python scripts/smoke_ledger.py
uv run python scripts/test_stage.py
uv run python scripts/accept_layer1.py
uv run python scripts/accept_layer2.py
```

Do not proceed to a savings recording unless both acceptance scripts pass. A
passing stage test does not mean the optimization layers passed.

## T−25 minutes — truth lock

1. Confirm a clean or fully understood tree and capture the SHA:

   ```bash
   git status --short
   git rev-parse --short HEAD
   ```

2. Run the live race and keep the stage process open:

   ```bash
   uv run amort demo --task ticket_triage --live --stage
   ```

3. Create a private evidence folder outside the repository named for the SHA.
   Copy in the report, terminal capture, stage capture, dashboard capture,
   Snowflake capture, and final exported videos.
4. Confirm every launch invariant:
   - `simulated: false`;
   - all four cells completed;
   - correct final model;
   - Snowflake is the displayed backend for a Snowflake claim;
   - cold parity passes;
   - repeat parity passes;
   - ground-truth accuracy passes for all cells;
   - the optimizer's internal discovery/compile/bind/verify calls are included;
   - a verified Skill ID exists before showing Skill replay;
   - report SHA, repository SHA, screenshots, and script agree.
5. Populate [METRICS.md](METRICS.md) and every `{{TOKEN}}` in the spoken script.
6. Export a matching backup video before the live presentation.

## T−10 minutes — launch scenes

Use a single presentation/browser surface or numbered OBS scenes. Never make
the audience watch window management.

| Scene | Prepared state |
|---:|---|
| 1 | Stage final state at `:4700`, zoomed to 125–150% |
| 2 | One-line `base_url` diff, credentials cropped |
| 3 | Cold result frame with raw dollars hidden until reveal |
| 4 | Repeat result frame with Skill/guard state |
| 5 | Snowflake worksheet already filtered to exact run ID |
| 6 | Matching `demo_report.json` quality fields or designed receipt |
| 7 | Land-and-expand slide |
| 8 | Final result + repository URL |
| 9 | Local three-minute backup clip, paused on frame zero |

Turn off notifications, browser extensions, unrelated tabs, shell history, and
password-manager prompts. Put the timer where a teammate—not the audience—can
see it.

## Live reveal sequence

### 0:00–0:31 — Problem and product

Start on a completed task. Show the repeat reset, then reveal Amortize. No logo
animation and no architecture tour.

### 0:31–0:44 — Integration

Show one base URL changing. Do not type setup commands. Do not expose `/health`
while it advertises stub layers.

### 0:44–0:58 — Fair-race contract

Say the constants: same model, same 30 tickets, same eight tools, same prompt,
same 120-field grader. Say the run occurred moments ago from the displayed SHA.

### 0:58–1:26 — New-task result

Reveal raw Direct cost, raw Amortize cost, then the measured reduction. Reveal
parity and ground-truth accuracy last. Do not celebrate before both are visible.

### 1:26–1:54 — Repeat result

Reveal the direct reset and the guarded Skill path. Show the real Skill ID only
if the final report produced one. Hold the final saving and correctness seal for
three seconds.

### 1:54–2:18 — Agent Economics Receipt

Highlight one Snowflake row: run ID, model, tokens, dollars, and backend. Then
show the same run ID in the signed report with parity, accuracy, and
`simulated:false`. Do not claim the quality verdict is already stored as a
Snowflake grade event until that implementation lands.

### 2:18–3:00 — Enterprise and close

Land with one workflow, expand to the fleet, then return to the winning result.
Stop speaking at 3:00 and leave the repository URL visible.

## Failure ladder

### Level 1 — A scene or browser surface stalls

Cut to the next prepared scene after eight seconds. Do not debug in public.

### Level 2 — Novita or Wi-Fi fails before the pitch

Use the backup clip and saved receipt from the exact prepared SHA. Do not switch
silently to simulated values.

### Level 3 — Snowflake is unavailable

Show the honest SQLite backend label and explain local failover. A saved
Snowflake image may be shown only as prior evidence and must be labeled with its
original SHA and date.

### Level 4 — LIGHTEN or REPLAY misses its gate

Show the verified control, quality contract, and receipt. Use the fallback copy
in `PITCH_SCRIPT.md`. Never put an acceptance target in the result position.

### Level 5 — Parity or accuracy fails

Invalidate the saving. Lead with the guard/fallback contract. A cheap wrong
answer is not a win.

## Presenter hand signals

- Open palm: advance scene.
- Two fingers: cut to backup video.
- Flat hand: stop live interaction and go to the prepared receipt.
- Point at wrist: skip optional voice control and begin the close.

## Final five-minute checklist

- [ ] Final SHA matches report, deck, script, images, and video
- [ ] Correct model and backend labels are visible
- [ ] `simulated:false` is visible in the evidence state
- [ ] Raw dollars appear before percentages
- [ ] Parity **and** accuracy are visible
- [ ] Stage is open at `http://127.0.0.1:4700`
- [ ] Snowflake is filtered to the exact run ID
- [ ] Backup video opens locally and starts muted
- [ ] No secrets, usernames, notifications, or unrelated tabs are visible
- [ ] A teammate owns the timer and cut signals
