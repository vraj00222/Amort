#!/usr/bin/env bash
# Integration gate — run after every merge; all green before the next merge.
#   GATE_LEVEL=0  smokes + ruff + quirk-greps (T0/G0)
#   GATE_LEVEL=1  + accept_layer1 unit checks (G1)
#   GATE_LEVEL=2  + accept_layer1 --live (G2)
#   GATE_LEVEL=3  + accept_layer2 [--plan-replay once wired] (G3+, default)
set -euo pipefail
cd "$(dirname "$0")/.."
LEVEL="${GATE_LEVEL:-3}"

echo "── gate (level $LEVEL) ─────────────────────────────────────────"

echo "[ruff]";               uv run ruff check amort scripts

# The two do-not-regress Snowflake quirks + the honest-reporting line
echo "[quirk-greps]"
grep -q "FROM VALUES" amort/ledger/snowflake_writer.py \
  || { echo "FATAL: STEPS multi-row insert lost its SELECT…FROM VALUES form"; exit 1; }
grep -q "PARSE_JSON" amort/ledger/snowflake_writer.py \
  || { echo "FATAL: STEPS insert lost PARSE_JSON"; exit 1; }
grep -q "_container_exists" amort/ledger/snowflake_writer.py \
  || { echo "FATAL: snowflake-init lost its skip-existing-container logic"; exit 1; }
grep -q "BACKEND USED" scripts/smoke_ledger.py \
  || { echo "FATAL: the BACKEND USED honest-reporting line is gone"; exit 1; }
echo "  quirks intact"

echo "[smoke_proxy]";        uv run python scripts/smoke_proxy.py
echo "[smoke_claude_code]";  uv run python scripts/smoke_claude_code.py
echo "[smoke_ledger]";       uv run python scripts/smoke_ledger.py
# Isolated memory dir: the decoy-discrimination assertion predates the compiler
# and fails against a store holding a real compiled ticket-triage skill.
echo "[smoke_everos]";       AMORT_MEMORY_DIR="$(mktemp -d)/memory" uv run python scripts/smoke_everos.py
echo "[smoke_dash]";         uv run python scripts/smoke_dash.py

if [ "$LEVEL" -ge 1 ]; then
  echo "[test_lighten]"
  uv run python scripts/test_lighten.py
  echo "[accept_layer1 unit]"
  uv run python scripts/accept_layer1.py
fi
if [ "$LEVEL" -ge 2 ]; then
  echo "[accept_layer1 live]"
  uv run python scripts/accept_layer1.py --live
fi
if [ "$LEVEL" -ge 3 ]; then
  echo "[accept_layer2]"
  uv run python scripts/accept_layer2.py ${PLAN_REPLAY:+--plan-replay}
fi

echo "── gate PASS (level $LEVEL) ────────────────────────────────────"
