-- AMORTIZE — three-minute demo worksheet
-- Prepare this worksheet before presenting. Never edit SQL on stage.

USE SCHEMA AMORTIZE.LEDGER;

-- 1. The fresh four-cell race.
-- Keep MODEL, cost, latency, and PARITY visible on screen.
SELECT
  RUN_ID,
  LANE,
  MODE,
  MODEL,
  INPUT_TOKENS,
  OUTPUT_TOKENS,
  COST_USD,
  WALL_MS,
  PARITY
FROM RUNS
ORDER BY STARTED_AT DESC
LIMIT 4;

-- 2. Cost summary by task fingerprint.
SELECT
  TASK_FINGERPRINT,
  AVG_BASELINE_COST,
  AVG_LIGHTENED_COST,
  AVG_WARM_COST,
  NET_SAVED_USD,
  TOTAL_RUNS
FROM SAVINGS
ORDER BY TOTAL_RUNS DESC;

-- 3. Exact trace behind the headline warm result.
-- Replace the value during rehearsal, not during the pitch.
SET DEMO_RUN_ID = 'replace-with-final-amortize-warm-run-id';

SELECT
  STEP_IDX,
  KIND,
  NAME,
  MODEL,
  INPUT_TOKENS,
  OUTPUT_TOKENS,
  COST_USD,
  WALL_MS,
  META
FROM STEPS
WHERE RUN_ID = $DEMO_RUN_ID
ORDER BY STEP_IDX;

-- 4. The quality receipt for that same run.
SELECT
  RUN_ID,
  TASK_FINGERPRINT,
  LANE,
  MODE,
  SKILL_ID,
  PARITY,
  OUTPUT_HASH
FROM RUNS
WHERE RUN_ID = $DEMO_RUN_ID;
