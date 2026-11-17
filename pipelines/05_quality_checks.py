# Databricks notebook source
# MAGIC %md
# MAGIC # 05 Quality checks
# MAGIC
# MAGIC Assertions over the silver and gold tables. Every result is written to
# MAGIC `ops.quality_checks`, then the notebook **fails** if any check did not pass, so a
# MAGIC bad run cannot go unnoticed.
# MAGIC
# MAGIC The PII leak scan looks for raw phone numbers, email addresses and long digit
# MAGIC runs in the redacted transcripts. It reports counts only, never the matched text.
# MAGIC It does not scan the knowledge base: help articles legitimately contain the
# MAGIC carrier's own support numbers.

# COMMAND ----------

import json
import re
from datetime import UTC, datetime

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

chunks = spark.table(settings.table("gold", "kb_chunks"))
articles = spark.table(settings.table("silver", "kb_articles_clean"))
transcripts = spark.table(settings.table("silver", "transcripts_redacted"))
plans = spark.table(settings.table("gold", "plans"))
insights = spark.table(settings.table("gold", "call_insights"))

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    results.append((name, bool(passed), detail))
    print(("PASS  " if passed else "FAIL  ") + f"{name}: {detail}")


# COMMAND ----------

# MAGIC %md
# MAGIC ## Keys and structure

# COMMAND ----------

for table_name, df, keys in (
    ("gold.kb_chunks", chunks, ["chunk_id", "article_id", "url", "text", "chunk_config"]),
    ("silver.kb_articles_clean", articles, ["article_id", "url", "title", "body_text"]),
    ("silver.transcripts_redacted", transcripts, ["transcript_id", "turns"]),
    ("gold.plans", plans, ["plan_id", "name", "monthly_price_usd"]),
    ("gold.call_insights", insights, ["transcript_id", "n_turns", "rules", "findings"]),
):
    null_condition = None
    for key in keys:
        is_null = F.col(key).isNull()
        null_condition = is_null if null_condition is None else (null_condition | is_null)
    nulls = df.where(null_condition).count()
    check(f"no_null_keys:{table_name}", nulls == 0, f"{nulls} rows with a null in {keys}")

duplicate_ids = chunks.groupBy("chunk_id").count().where("count > 1").count()
check("unique_chunk_ids", duplicate_ids == 0, f"{duplicate_ids} duplicated chunk_id values")

missing_url = chunks.where(~F.col("url").startswith("http")).count()
check("every_chunk_has_a_url", missing_url == 0, f"{missing_url} chunks without an http URL")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Chunk sizes and coverage

# COMMAND ----------

for config_name, config in sorted(settings.chunking.items()):
    of_config = chunks.where(F.col("chunk_config") == config_name)
    total = of_config.count()
    too_big = of_config.where(F.col("n_tokens") > config.chunk_size_tokens).count()
    empty = of_config.where(F.length(F.trim("text")) == 0).count()
    check(
        f"chunk_sizes_within_bounds:{config_name}",
        total > 0 and too_big == 0 and empty == 0,
        f"{total} chunks, {too_big} over {config.chunk_size_tokens} tokens, {empty} empty",
    )
    uncovered = articles.join(of_config, "article_id", "left_anti").count()
    check(
        f"every_article_is_chunked:{config_name}",
        uncovered == 0,
        f"{uncovered} of {articles.count()} articles have no chunk",
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## PII leak scan on redacted transcripts

# COMMAND ----------

turn_text = transcripts.select("transcript_id", F.explode("turns").alias("turn")).select(
    "transcript_id", F.col("turn.text").alias("text")
)
LEAK_PATTERNS = {
    "phone_number": r"(?:\(\d{3}\)\s?|\b\d{3}[\s.-])\d{3}[\s.-]\d{4}\b",
    "email_address": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    # Account numbers, IMEIs, ICCIDs and card numbers are all runs of 9 or more digits.
    "long_digit_run": r"\d{9,}",
    "grouped_card_number": r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}\b",
}
total_leaks = 0
for name, pattern in LEAK_PATTERNS.items():
    hits = turn_text.where(F.col("text").rlike(pattern)).count()
    total_leaks += hits
    check(f"pii_leak_scan:{name}", hits == 0, f"{hits} redacted turns still match")

n_transcripts = transcripts.count()
n_bronze = spark.table(settings.table("bronze", "transcripts")).count()
check(
    "all_transcripts_redacted",
    n_transcripts == n_bronze and n_transcripts > 0,
    f"{n_transcripts} redacted of {n_bronze} ingested",
)
with_placeholder = transcripts.where(F.size(F.map_keys("entity_counts")) > 0).count()
check(
    "redaction_found_something_in_every_transcript",
    with_placeholder == n_transcripts,
    f"{with_placeholder} of {n_transcripts} transcripts have at least one redaction",
)
duplicate_calls = transcripts.groupBy("transcript_id").count().where("count > 1").count()
check("unique_transcript_ids", duplicate_calls == 0, f"{duplicate_calls} duplicated transcript ids")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Call insights
# MAGIC
# MAGIC The rule check has to cover every redacted call exactly once, point only at turns
# MAGIC that exist, and hold no text from a call. Whether its findings are right is not
# MAGIC checked here: `eval/compliance_eval.py` measures that on labelled calls.

# COMMAND ----------

n_insights = insights.count()
unchecked = transcripts.join(insights, "transcript_id", "left_anti").count()
unknown_calls = insights.join(transcripts, "transcript_id", "left_anti").count()
check(
    "every_call_is_checked_once",
    n_insights == n_transcripts and unchecked == 0 and unknown_calls == 0,
    f"{n_insights} rows for {n_transcripts} calls, {unchecked} calls with no row, "
    f"{unknown_calls} rows for no call",
)
# A finding that points past the end of its call, or a count that disagrees with the list.
bad_shape = insights.where(
    "n_findings != size(findings) "
    "OR exists(findings, f -> f.turn_index < 0 OR f.turn_index >= n_turns) "
    "OR exists(findings, f -> NOT array_contains(rules, f.rule))"
).count()
check(
    "findings_point_at_turns_of_their_call",
    bad_shape == 0,
    f"{bad_shape} calls with a finding outside the call or a count that does not match",
)
# A placeholder in a reason would mean text was copied out of a turn.
copied = insights.where("exists(findings, f -> f.reason LIKE '%<%' OR f.reason LIKE '%>%')").count()
check(
    "call_insights_hold_no_transcript_text",
    copied == 0,
    f"{copied} calls whose findings hold a placeholder",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Plans

# COMMAND ----------

bad_prices = plans.where((F.col("monthly_price_usd") <= 0) | F.col("monthly_price_usd").isNull())
check("plan_prices_are_positive", bad_prices.count() == 0, f"{bad_prices.count()} bad prices")
n_plans = plans.where("kind = 'plan'").count()
check("plan_catalogue_is_complete", n_plans == 8, f"{n_plans} plans, expected 8")

# COMMAND ----------

RESULT_SCHEMA = T.StructType(
    [
        T.StructField("git_sha", T.StringType(), False),
        T.StructField("run_at", T.TimestampType(), False),
        T.StructField("check_name", T.StringType(), False),
        T.StructField("passed", T.BooleanType(), False),
        T.StructField("detail", T.StringType(), True),
    ]
)
results_df = spark.createDataFrame(
    [(git_sha, run_at, name, passed, detail) for name, passed, detail in results], RESULT_SCHEMA
)
checks_table = settings.table("ops", "quality_checks")
if spark.catalog.tableExists(checks_table):
    # One set of rows per code version: a re-run replaces its own rows only.
    results_df.write.mode("overwrite").option("replaceWhere", f"git_sha = '{git_sha}'").saveAsTable(
        checks_table
    )
else:
    results_df.write.saveAsTable(checks_table)

failed = [name for name, passed, _ in results if not passed]
summary = {
    "checks": len(results),
    "failed": failed,
    "pii_leak_hits": total_leaks,
}
print(json.dumps(summary))
if failed:
    raise RuntimeError(f"{len(failed)} quality checks failed: {failed}")

dbutils.notebook.exit(json.dumps(summary))
