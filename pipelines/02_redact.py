# Databricks notebook source
# MAGIC %md
# MAGIC # 02 Redact: bronze to silver
# MAGIC
# MAGIC 1. Redacts every transcript with `copilot.redaction` (Presidio + spaCy), in Spark.
# MAGIC 2. Measures the redactor against the labeled transcripts and stores the metrics.
# MAGIC 3. Cleans the knowledge base and the plan catalogue.
# MAGIC
# MAGIC **No unredacted transcript text leaves this notebook.** Silver holds redacted turns
# MAGIC only, and the detections table holds positions and types, never the values.
# MAGIC
# MAGIC Safe to re-run: tables are replaced, and metrics are replaced per code version.

# COMMAND ----------

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime

import pandas as pd
from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from copilot.config import Settings
from copilot.redaction import (
    CPNI_ENTITY_TYPES,
    DEFAULT_ALLOW_LIST,
    DEFAULT_SPACY_MODEL,
    PII_ENTITY_TYPES,
)
from copilot.span_metrics import Counts, Span, match_spans, merge_counts, micro_total

dbutils.widgets.text("catalog", "frontline")
dbutils.widgets.text("git_sha", "unknown")
settings = Settings(catalog=dbutils.widgets.get("catalog"))
git_sha = dbutils.widgets.get("git_sha") or "unknown"
if not re.fullmatch(r"[0-9a-f]{7,40}|unknown", git_sha):
    raise ValueError(f"git_sha is not a commit hash: {git_sha!r}")
run_at = datetime.now(UTC)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Redact the transcripts

# COMMAND ----------

# Product names are not personal data. Without this, a named-entity model can tag a
# plan name as a person.
plan_names = [row["name"] for row in spark.table(settings.table("bronze", "plans")).collect()]
allow_list = [*DEFAULT_ALLOW_LIST, *plan_names]
spacy_model = DEFAULT_SPACY_MODEL

REDACTED_SCHEMA = T.StructType(
    [
        T.StructField("transcript_id", T.StringType(), False),
        T.StructField(
            "turns",
            T.ArrayType(
                T.StructType(
                    [
                        T.StructField("speaker", T.StringType(), True),
                        T.StructField("text", T.StringType(), True),
                    ]
                )
            ),
            False,
        ),
        T.StructField(
            "entity_counts",
            T.ArrayType(
                T.StructType(
                    [
                        T.StructField("entity_type", T.StringType(), False),
                        T.StructField("n", T.IntegerType(), False),
                    ]
                )
            ),
            False,
        ),
        T.StructField(
            "detections",
            T.ArrayType(
                T.StructType(
                    [
                        T.StructField("turn_index", T.IntegerType(), False),
                        T.StructField("start", T.IntegerType(), False),
                        T.StructField("end", T.IntegerType(), False),
                        T.StructField("entity_type", T.StringType(), False),
                        T.StructField("score", T.DoubleType(), False),
                    ]
                )
            ),
            False,
        ),
    ]
)


def redact_batches(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    """Redact whole conversations, so a short answer can borrow its question's cue words."""
    from copilot.redaction import Redactor

    redactor = Redactor(spacy_model, allow_list=allow_list)  # built once per partition
    for batch in batches:
        rows = []
        for transcript_id, turns in zip(batch["transcript_id"], batch["turns"], strict=True):
            speakers = [turn["speaker"] for turn in turns]
            results = redactor.redact_turns([turn["text"] for turn in turns])
            counts: dict[str, int] = defaultdict(int)
            detections = []
            for turn_index, result in enumerate(results):
                for entity in result.entities:
                    counts[entity.entity_type] += 1
                    detections.append(
                        {
                            "turn_index": turn_index,
                            "start": entity.start,
                            "end": entity.end,
                            "entity_type": entity.entity_type,
                            "score": float(entity.score),
                        }
                    )
            rows.append(
                {
                    "transcript_id": transcript_id,
                    "turns": [
                        {"speaker": speaker, "text": result.text}
                        for speaker, result in zip(speakers, results, strict=True)
                    ],
                    "entity_counts": [
                        {"entity_type": entity_type, "n": n}
                        for entity_type, n in sorted(counts.items())
                    ],
                    "detections": detections,
                }
            )
        yield pd.DataFrame(rows, columns=[field.name for field in REDACTED_SCHEMA.fields])


bronze_transcripts = spark.table(settings.table("bronze", "transcripts"))
redacted = bronze_transcripts.select("transcript_id", "turns").mapInPandas(
    redact_batches, schema=REDACTED_SCHEMA
)

# Written once to a staging table so the redactor runs a single time, then split into
# the silver table and the detections table.
staging = settings.table("ops", "redaction_staging")
redacted.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(staging)

# COMMAND ----------

silver_transcripts = settings.table("silver", "transcripts_redacted")
(
    spark.table(staging)
    .join(
        bronze_transcripts.select(
            "transcript_id", "channel", "category", "created_at", "resolution"
        ),
        "transcript_id",
    )
    .select(
        "transcript_id",
        "channel",
        "category",
        "created_at",
        "resolution",
        "turns",
        F.map_from_entries(
            F.transform("entity_counts", lambda item: F.struct(item["entity_type"], item["n"]))
        ).alias("entity_counts"),
        F.size("turns").alias("n_turns"),
        F.lit(spacy_model).alias("redactor_model"),
        F.lit(run_at).alias("_redacted_at"),
    )
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(silver_transcripts)
)

detections_table = settings.table("ops", "redaction_detections")
(
    spark.table(staging)
    .select("transcript_id", F.explode("detections").alias("d"))
    .select("transcript_id", "d.turn_index", "d.start", "d.end", "d.entity_type", "d.score")
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(detections_table)
)
spark.sql(f"DROP TABLE IF EXISTS {staging}")

n_redacted = spark.table(silver_transcripts).count()
n_detections = spark.table(detections_table).count()
print(f"{silver_transcripts}: {n_redacted} rows; {detections_table}: {n_detections} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Measure the redactor on the labeled transcripts
# MAGIC
# MAGIC Same matching rule as `eval/redaction_eval.py`: a detection matches a label when
# MAGIC their intersection-over-union is at least 0.5 and the type is the same.

# COMMAND ----------

labels = spark.table(settings.table("bronze", "pii_labels")).collect()
labeled_ids = sorted({row["transcript_id"] for row in labels})
predicted_rows = (
    spark.table(detections_table).where(F.col("transcript_id").isin(labeled_ids)).collect()
)

gold: dict[tuple[str, int], list[Span]] = defaultdict(list)
for row in labels:
    gold[(row["transcript_id"], row["turn_index"])].append(
        Span(row["start"], row["end"], row["entity_type"])
    )
predicted: dict[tuple[str, int], list[Span]] = defaultdict(list)
for row in predicted_rows:
    predicted[(row["transcript_id"], row["turn_index"])].append(
        Span(row["start"], row["end"], row["entity_type"])
    )

per_type = merge_counts(
    match_spans(gold.get(key, []), predicted.get(key, [])) for key in set(gold) | set(predicted)
)
rows = [("PII", name, per_type.get(name, Counts())) for name in PII_ENTITY_TYPES] + [
    ("CPNI", name, per_type.get(name, Counts())) for name in CPNI_ENTITY_TYPES
]
rows.append(("PII", "ALL_PII", micro_total(per_type, PII_ENTITY_TYPES)))
rows.append(("CPNI", "ALL_CPNI", micro_total(per_type, CPNI_ENTITY_TYPES)))

METRICS_SCHEMA = T.StructType(
    [
        T.StructField("git_sha", T.StringType(), False),
        T.StructField("run_at", T.TimestampType(), False),
        T.StructField("redactor_model", T.StringType(), False),
        T.StructField("transcripts_scored", T.IntegerType(), False),
        T.StructField("entity_group", T.StringType(), False),
        T.StructField("entity_type", T.StringType(), False),
        T.StructField("support", T.IntegerType(), False),
        T.StructField("tp", T.IntegerType(), False),
        T.StructField("fp", T.IntegerType(), False),
        T.StructField("fn", T.IntegerType(), False),
        T.StructField("precision", T.DoubleType(), True),
        T.StructField("recall", T.DoubleType(), True),
        T.StructField("f1", T.DoubleType(), True),
    ]
)
metrics = spark.createDataFrame(
    [
        (git_sha, run_at, spacy_model, len(labeled_ids), group, name, c.support, c.tp, c.fp,
         c.fn, c.precision, c.recall, c.f1)
        for group, name, c in rows
    ],
    METRICS_SCHEMA,
)  # fmt: skip
metrics_table = settings.table("ops", "redaction_metrics")
if spark.catalog.tableExists(metrics_table):
    # One set of rows per code version: a re-run replaces its own rows only.
    metrics.write.mode("overwrite").option("replaceWhere", f"git_sha = '{git_sha}'").saveAsTable(
        metrics_table
    )
else:
    metrics.write.saveAsTable(metrics_table)
display(metrics.orderBy("entity_group", "entity_type"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Clean the knowledge base and the plans

# COMMAND ----------

latest_first = Window.partitionBy("url").orderBy(F.col("scraped_at").desc())
kb_clean = settings.table("silver", "kb_articles_clean")
(
    spark.table(settings.table("bronze", "kb_articles"))
    .withColumn("body_text", F.trim("body_text"))
    .where(F.length("body_text") >= 200)
    .withColumn("_rank", F.row_number().over(latest_first))
    .where("_rank = 1")
    .select(
        "article_id",
        "url",
        F.trim("title").alias("title"),
        "section",
        "body_text",
        F.length("body_text").alias("n_chars"),
        "synthetic",
        "scraped_at",
    )
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(kb_clean)
)

silver_plans = settings.table("silver", "plans")
(
    spark.table(settings.table("bronze", "plans"))
    .select(
        "plan_id",
        "kind",
        F.trim("name").alias("name"),
        "monthly_price_usd",
        "billing_period",
        "data_gb",
        "talk_text",
        "hotspot_gb",
        "international",
        "notes",
    )
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(silver_plans)
)

n_kb = spark.table(kb_clean).count()
n_plans = spark.table(silver_plans).count()
print(f"{kb_clean}: {n_kb} rows; {silver_plans}: {n_plans} rows")

# COMMAND ----------

all_pii = micro_total(per_type, PII_ENTITY_TYPES)
all_cpni = micro_total(per_type, CPNI_ENTITY_TYPES)
dbutils.notebook.exit(
    json.dumps(
        {
            "transcripts_redacted": n_redacted,
            "detections": n_detections,
            "kb_articles_clean": n_kb,
            "plans": n_plans,
            "labeled_transcripts": len(labeled_ids),
            "pii": {"support": all_pii.support, "tp": all_pii.tp, "fp": all_pii.fp,
                    "fn": all_pii.fn, "precision": all_pii.precision, "recall": all_pii.recall},
            "cpni": {"support": all_cpni.support, "tp": all_cpni.tp, "fp": all_cpni.fp,
                     "fn": all_cpni.fn, "precision": all_cpni.precision,
                     "recall": all_cpni.recall},
        }
    )
)  # fmt: skip
