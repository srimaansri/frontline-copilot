# Databricks notebook source
# MAGIC %md
# MAGIC # 06 Call insights: silver to gold
# MAGIC
# MAGIC Runs the rule check (`copilot.compliance`, five rules, no model call) on every
# MAGIC redacted call and writes `gold.call_insights`: one row per call, with what the
# MAGIC check found as an array. A call in which no rule fired still has a row, so
# MAGIC "checked, nothing found" is not the same as "not checked".
# MAGIC
# MAGIC **Only the redacted table is read, and no text from a call is written.** A row
# MAGIC holds the call id, counts, rule names, turn numbers and the checker's own fixed
# MAGIC sentences.
# MAGIC
# MAGIC A finding is a reason for a supervisor to open the call. It is not a verdict: the
# MAGIC rules miss some breaches, and `eval/compliance_eval.py` measures how many.
# MAGIC
# MAGIC In the job this runs after the index is built and before the quality checks, which
# MAGIC read the table it writes.
# MAGIC
# MAGIC Safe to re-run: the table is replaced.

# COMMAND ----------

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime

import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql import types as T

from copilot.config import Settings

dbutils.widgets.text("catalog", "frontline")
dbutils.widgets.text("git_sha", "unknown")
settings = Settings(catalog=dbutils.widgets.get("catalog"))
git_sha = dbutils.widgets.get("git_sha") or "unknown"
if not re.fullmatch(r"[0-9a-f]{7,40}|unknown", git_sha):
    raise ValueError(f"git_sha is not a commit hash: {git_sha!r}")
run_at = datetime.now(UTC)

# COMMAND ----------

# The columns `copilot.call_insights.insight_row` returns, in the order of the table.
INSIGHT_SCHEMA = T.StructType(
    [
        T.StructField("transcript_id", T.StringType(), False),
        T.StructField("n_turns", T.IntegerType(), False),
        T.StructField("n_findings", T.IntegerType(), False),
        T.StructField("rules", T.ArrayType(T.StringType(), False), False),
        T.StructField(
            "findings",
            T.ArrayType(
                T.StructType(
                    [
                        T.StructField("rule", T.StringType(), False),
                        T.StructField("turn_index", T.IntegerType(), False),
                        T.StructField("reason", T.StringType(), False),
                    ]
                ),
                False,
            ),
            False,
        ),
    ]
)


def check_batches(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    """Check whole calls: two of the rules depend on the order of the turns."""
    from copilot.call_insights import insight_row

    for batch in batches:
        rows = [
            insight_row(transcript_id, list(turns))
            for transcript_id, turns in zip(batch["transcript_id"], batch["turns"], strict=True)
        ]
        yield pd.DataFrame(rows, columns=[field.name for field in INSIGHT_SCHEMA.fields])


silver_transcripts = spark.table(settings.table("silver", "transcripts_redacted"))
insights_table = settings.table("gold", "call_insights")
(
    silver_transcripts.select("transcript_id", "turns")
    .mapInPandas(check_batches, schema=INSIGHT_SCHEMA)
    .select(
        "transcript_id",
        "n_turns",
        "n_findings",
        "rules",
        "findings",
        F.lit(git_sha).alias("git_sha"),
        F.lit(run_at).alias("_checked_at"),
    )
    # The table and its column comments come from setup/00_setup.sql. The schema is not
    # overwritten here, so a column that no longer matches stops the run, not the comments.
    .write.mode("overwrite")
    .saveAsTable(insights_table)
)

# COMMAND ----------

insights = spark.table(insights_table)
n_calls = insights.count()
n_flagged = insights.where("n_findings > 0").count()
by_rule = {
    row["rule"]: row["calls"]
    for row in insights.select(F.explode("rules").alias("rule"))
    .groupBy("rule")
    .agg(F.count("*").alias("calls"))
    .collect()
}
print(f"{insights_table}: {n_calls} calls checked, {n_flagged} with a finding")
display(insights.where("n_findings > 0").orderBy("transcript_id").limit(50))

# COMMAND ----------

# Every redacted call has to be in the table, or the calls list would show it as unchecked.
n_redacted = silver_transcripts.count()
if n_calls != n_redacted:
    raise RuntimeError(f"{n_calls} calls checked of {n_redacted} redacted")

dbutils.notebook.exit(
    json.dumps({"calls_checked": n_calls, "calls_with_a_finding": n_flagged, "by_rule": by_rule})
)
