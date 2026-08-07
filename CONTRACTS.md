# CONTRACTS — frozen interfaces (day-one build)

*These are law. No workstream changes them without integrator sign-off. The
acceptance scripts (`scripts/accept_layer1.py`, `scripts/accept_layer2.py`) are
the executable form of this document — where prose and script disagree, the
script wins.*

## Ownership

| Owner | Files |
|---|---|
| **A — Lighten** | `amort/proxy/**` (may add `amort/proxy/lighten.py`) |
| **B — Amortize** | `amort/skills/**` (may add `amort/skills/llm.py`) |
| **C — Showtime** | `amort/demo/**`, `amort/dashboard/**`, `amort/cli.py`, `README.md` |
| **Integrator only** | `amort/config.py`, `amort/ledger/**`, `scripts/accept_*.py`, `scripts/gate.sh`, cross-workstream wiring |

## Interceptors / proxy (A)

- `before_request(req: ProxyRequest) -> ProxyRequest` and
  `after_response(resp: ProxyResponse) -> ProxyResponse` — signatures frozen.
- Layer-1 gate: `req.provider == "openai" and not req.stream and len(tool catalog) > settings.amort_tool_stub_threshold and settings.amort_lighten`. Everything else — streaming, Anthropic, small requests — passes through **byte-identical** (the existing single-shot `relay()` path stays verbatim).
- A modified body must be a **fresh dict** (`relay()` detects rewrite by identity, `body is not parsed`). In-place mutation silently forwards the original bytes.
- Never touch the `system` array/message. Stub catalogue lives inside the synthetic tool's **description**.
- Synthetic tools are named `amort__search_tools` and `amort__read_spill`; they are never returned to the client. If a model choice mixes synthetic + real tool_calls, splice an assistant message with only the synthetic calls + results upstream-side and drop the real ones for that iteration.
- Loop cap 6 upstream calls per client request; on cap / non-200 / any exception: one clean re-send of the original `raw_body` (full catalogue) and return that response. Never fail the request.
- **Usage honesty:** accumulated prompt/completion tokens across ALL loop iterations are patched into the final response body's `usage` before returning. One `StepEvent` per iteration (`meta.layer1.internal=true` on discovery iterations).
- `amort/proxy/lighten.py` public API (used by accept_layer1 and by C's offline lane):
  - `build_stub_tool(catalog: list[dict]) -> dict` — the `amort__search_tools` tool, stub lines in its description
  - `resolve_search_tools(catalog: list[dict], query: str) -> list[dict]` — substring + fuzzy, returns FULL OpenAI-format tool dicts
  - `spill_result(content: str) -> str` — returns content unchanged when under `settings.amort_spill_threshold` tokens (chars/4) or when it already carries the marker; else writes `.amort/spill/<sha256[:16]>.txt` and returns a replacement containing `amort-spill:<handle>`, head/tail preview, and an id digest
  - `resolve_read_spill(handle: str, mode: str, arg: str) -> str` — modes `head|tail|grep`

## Ledger (integrator)

- `StepEvent` — extend only via `meta` (`meta.layer1.*`, `meta.layer2.*`). `Kind` literal is frozen (`llm|tool|replay|grade`) — the compile call is `kind="llm", name="compile", meta={"phase": "compile"}`.
- SKILLS table writes are **append-only** via `emit_skill`; readers take the latest row per `SKILL_ID`.
- **Do not touch:** the STEPS `SELECT … FROM VALUES` + `PARSE_JSON` insert form; `snowflake-init`'s skip-existing-container logic; the `BACKEND USED` line in `scripts/smoke_ledger.py`.

## Skills (B)

- `store_everos.py` function signatures — unchanged.
- Skill markdown schema — extend only via NEW frontmatter keys. Added today: `version` (bump on every re-distillation), `runs_observed`.
- `compile_skill(cases: list[dict]) -> Skill | None` — signature frozen. Filters to `ok=True` cases sharing one fingerprint; needs ≥2 (`MIN_CASES_TO_DISTIL = 2`). Sets `status="verified"` iff the ≥2 cases' final outputs pass a field-exact pairwise grade (two agreeing runs = the promotion ladder's two passes); otherwise `candidate`.
- `replay(skill, request: dict) -> ReplayOutcome` — signature frozen. Request keys: `user_msg`, `tool_executor: Callable[[str, dict], Any]`, `model`, `base_url`, `api_key`. `candidate` is never replayed; `quarantined` never replays. ≤2 LLM calls (bind params, verify digest); tool outputs never enter LLM context; any guard failure → `ok=False` + `fallback` reason, never an exception.
- `ReplayOutcome.steps` entries are `RecordedStep.to_dict()`-shaped so the harness can replay them into a `RunRecorder`.
- `build_plan_directive(skill, budget_tokens: int) -> str` — PLAN REPLAY text for proxy injection; over budget → truncate to step titles + guards.

## Demo (C)

- The 2×2 cells are measured runs; the compile call is logged under B_cold's `run_id`.
- Every simulated number stays labelled `simulated: true` end-to-end.
- Stage view lives in `amort/demo/stage.py` on its own port (default 4700) — no proxy files.

## Ground rules (everyone)

- **No fabricated numbers.** Every % must trace to ledger rows.
- `uv run ruff check amort scripts` clean before handing back.
- Test with `AMORT_LEDGER=sqlite` locally (keep the shared Snowflake ledger clean); the demo itself runs `auto`.
- No new dependencies without integrator sign-off. No secrets in diffs.
