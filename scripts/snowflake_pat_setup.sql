-- Run in Snowsight as ACCOUNTADMIN with "Run All". Idempotent; safe to re-run.
--
-- Fixes "Fail : Network policy is required." (390432) when authenticating with
-- the AMORT programmatic access token.
--
-- A PAT is refused unless the user is subject to a network policy. Rather than
-- satisfy that with an 0.0.0.0/0 firewall hole (what an earlier version of this
-- script did), lift the requirement with the toggle Snowflake provides for it:
-- an authentication policy whose PAT_POLICY sets NETWORK_POLICY_EVALUATION.

USE ROLE ACCOUNTADMIN;

-- 0. Database context ---------------------------------------------------------
-- AUTHENTICATION POLICY is a SCHEMA-level object, so the session needs a current
-- database or the CREATE fails with "This session does not have a current
-- database". Same DB/schema the ledger DDL uses, created here so this script can
-- run before `amort snowflake-init`.
CREATE DATABASE IF NOT EXISTS AMORTIZE;
CREATE SCHEMA IF NOT EXISTS AMORTIZE.LEDGER;
USE SCHEMA AMORTIZE.LEDGER;

-- 1. Drop the network-policy requirement for PATs -----------------------------
-- ENFORCED_NOT_REQUIRED: a network policy is no longer required to use a token,
-- but if one IS attached it still gets enforced. (NOT_ENFORCED would skip it
-- entirely — don't, that silently disables the policy if you add one later.)
--
-- AUTHENTICATION_METHODS is deliberately omitted so it defaults to ALL. Naming
-- methods here would restrict how VRAJ can log in and can lock you out of
-- Snowsight.
CREATE AUTHENTICATION POLICY IF NOT EXISTS AMORTIZE.LEDGER.AMORT_PAT_POLICY
  PAT_POLICY = (
    NETWORK_POLICY_EVALUATION = ENFORCED_NOT_REQUIRED
  )
  COMMENT = 'Amortize demo: let the AMORT PAT authenticate without an attached network policy.';

ALTER AUTHENTICATION POLICY AMORTIZE.LEDGER.AMORT_PAT_POLICY SET
  PAT_POLICY = (
    NETWORK_POLICY_EVALUATION = ENFORCED_NOT_REQUIRED
  );

-- No `=` here. Attaching a policy is its own grammar; `SET NETWORK_POLICY = x`
-- takes an equals sign, `SET AUTHENTICATION POLICY x` does not.
ALTER USER VRAJ SET AUTHENTICATION POLICY AMORTIZE.LEDGER.AMORT_PAT_POLICY;

-- 2. Close the 0.0.0.0/0 hole from the previous run ---------------------------
-- No longer load-bearing now that the requirement is lifted.
ALTER ACCOUNT UNSET NETWORK_POLICY;
ALTER USER VRAJ UNSET NETWORK_POLICY;

-- 3. Cortex + ledger access for the token's role ------------------------------
-- The AMORT token is ROLE_RESTRICTION'd to SYSADMIN, and Cortex Agents evaluate
-- privileges with the querying role, so SYSADMIN is what needs these.
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SYSADMIN;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE SYSADMIN;

-- ACCOUNTADMIN created AMORTIZE above, so it owns it and SYSADMIN gets only what
-- is granted. `amort snowflake-init` issues CREATE SCHEMA IF NOT EXISTS, which
-- checks the privilege even when the schema already exists — so USAGE is not
-- enough. Hand the database to SYSADMIN instead of granting CREATE SCHEMA,
-- CREATE TABLE, CREATE VIEW … one at a time; SYSADMIN owning databases is the
-- conventional Snowflake layout anyway.
GRANT OWNERSHIP ON DATABASE AMORTIZE TO ROLE SYSADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA AMORTIZE.LEDGER TO ROLE SYSADMIN COPY CURRENT GRANTS;

-- 4. Verify -------------------------------------------------------------------
DESC AUTHENTICATION POLICY AMORTIZE.LEDGER.AMORT_PAT_POLICY;  -- ENFORCED_NOT_REQUIRED
SHOW PARAMETERS LIKE 'NETWORK_POLICY' IN USER VRAJ;           -- expect empty value

-- Teardown after the demo:
--   ALTER USER VRAJ UNSET AUTHENTICATION POLICY;
--   DROP AUTHENTICATION POLICY AMORTIZE.LEDGER.AMORT_PAT_POLICY;
--   DROP NETWORK POLICY IF EXISTS AMORT_DEV_POLICY;
--   DROP NETWORK RULE IF EXISTS AMORT_DEV_RULE;
