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

-- After-call wrap-ups (Milestone 9). The copilot drafts one from the redacted
-- transcript, the agent checks it, and only the one they approve is written here.
-- Every text column is checked for personal data again before the insert.
CREATE TABLE IF NOT EXISTS frontline.ops.call_wrapups (
  wrapup_id       STRING NOT NULL COMMENT 'Reference of this record, such as WRP-1A2B3C4D',
  saved_at        TIMESTAMP COMMENT 'UTC, when the agent saved it',
  transcript_id   STRING NOT NULL COMMENT 'The call, as in silver.transcripts_redacted',
  disposition     STRING COMMENT 'How the call ended: resolved, escalated or unresolved',
  category        STRING COMMENT 'What the call was about, one of the ten call categories',
  notes           ARRAY<STRING> COMMENT 'What happened, one short line each, redacted',
  promises        ARRAY<STRING> COMMENT 'What the agent told the customer would happen, redacted',
  follow_up_owner STRING COMMENT 'Who takes the next step: customer, agent or team. NULL if none',
  follow_up       STRING COMMENT 'The next step, redacted. NULL if nothing is left to do',
  sentiment       STRING COMMENT 'The customer''s mood at the end: positive, neutral or negative'
) COMMENT 'After-call records approved by an agent. A call saved twice has two rows; the latest saved_at is current.';
