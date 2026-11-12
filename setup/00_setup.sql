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
