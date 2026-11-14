-- Frontline Copilot: Unity Catalog objects.
-- Run once in the Databricks SQL editor. Safe to re-run: every statement is IF NOT EXISTS.
--
-- If CREATE CATALOG is not allowed in your workspace, skip the first statement,
-- replace `frontline` with your existing catalog (for example `workspace`) in the
-- rest of this file, and set CATALOG to the same name in `.env`.

CREATE CATALOG IF NOT EXISTS frontline
  COMMENT 'Frontline Copilot demo. Synthetic data only.';

CREATE SCHEMA IF NOT EXISTS frontline.raw
  COMMENT 'Landing volume for files uploaded from the laptop.';
CREATE SCHEMA IF NOT EXISTS frontline.bronze
  COMMENT 'Files as ingested. Holds unredacted synthetic transcripts.';
CREATE SCHEMA IF NOT EXISTS frontline.silver
  COMMENT 'Cleaned tables. Transcripts here are PII-redacted.';
CREATE SCHEMA IF NOT EXISTS frontline.gold
  COMMENT 'Serving tables: KB chunks, plans, and the AI Search index.';
CREATE SCHEMA IF NOT EXISTS frontline.ops
  COMMENT 'Operational tables: quality checks, redaction metrics, escalations, feedback.';

CREATE VOLUME IF NOT EXISTS frontline.raw.landing
  COMMENT 'Target of data_gen/upload.py.';

-- Confirm what exists.
SHOW SCHEMAS IN frontline;
SHOW VOLUMES IN frontline.raw;

-- Hand-offs opened by the copilot (Milestone 4). The copilot redacts the reason
-- before the insert, so this table never holds personal data as written.
CREATE TABLE IF NOT EXISTS frontline.ops.escalations (
  ticket_id  STRING NOT NULL COMMENT 'Reference given to the agent, such as ESC-1A2B3C4D',
  created_at TIMESTAMP COMMENT 'UTC',
  category   STRING COMMENT 'billing, plan_change, account_access, device, cancellation or other',
  urgency    STRING COMMENT 'low, normal or high',
  reason     STRING COMMENT 'What was asked for, redacted before the write',
  status     STRING COMMENT 'open when created'
) COMMENT 'Hand-offs to a human specialist opened by the copilot.';
