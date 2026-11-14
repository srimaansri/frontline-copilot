# Databricks notebook source
# MAGIC %md
# MAGIC # 01 Ingest: landing volume to bronze
# MAGIC
# MAGIC Reads the four files uploaded by `data_gen/upload.py` and writes them as Delta
# MAGIC tables, unchanged apart from two lineage columns.
# MAGIC
# MAGIC Bronze holds the **unredacted** transcripts. That is acceptable here only because
# MAGIC the data is synthetic. In production this schema would be locked down with Unity
# MAGIC Catalog grants and column masks.
# MAGIC
# MAGIC Safe to re-run: every table is replaced.

# COMMAND ----------

import json

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from copilot.config import Settings

dbutils.widgets.text("catalog", "frontline")
settings = Settings(catalog=dbutils.widgets.get("catalog"))
landing = settings.volume_path("raw", "landing")
print(f"reading from {landing}")

# COMMAND ----------

KB_SCHEMA = T.StructType(
    [
        T.StructField("article_id", T.StringType(), False),
        T.StructField("url", T.StringType(), False),
        T.StructField("title", T.StringType(), False),
        T.StructField("section", T.StringType(), True),
        T.StructField("body_text", T.StringType(), True),
        T.StructField("scraped_at", T.StringType(), True),
        T.StructField("last_modified", T.StringType(), True),
        T.StructField("synthetic", T.BooleanType(), True),
    ]
)
TRANSCRIPT_SCHEMA = T.StructType(
    [
        T.StructField("transcript_id", T.StringType(), False),
        T.StructField("channel", T.StringType(), True),
        T.StructField("category", T.StringType(), True),
        T.StructField("created_at", T.TimestampType(), True),
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
            True,
        ),
        T.StructField("resolution", T.StringType(), True),
    ]
)
LABEL_SCHEMA = T.StructType(
    [
        T.StructField("transcript_id", T.StringType(), False),
        T.StructField("turn_index", T.IntegerType(), False),
        T.StructField("start", T.IntegerType(), False),
        T.StructField("end", T.IntegerType(), False),
        T.StructField("entity_type", T.StringType(), False),
        T.StructField("text", T.StringType(), True),
    ]
)
PLAN_SCHEMA = T.StructType(
    [
        T.StructField("plan_id", T.StringType(), False),
        T.StructField("kind", T.StringType(), True),
        T.StructField("name", T.StringType(), True),
        T.StructField("monthly_price_usd", T.DecimalType(8, 2), True),
        T.StructField("billing_period", T.StringType(), True),
        T.StructField("data_gb", T.DoubleType(), True),
        T.StructField("talk_text", T.StringType(), True),
        T.StructField("hotspot_gb", T.DoubleType(), True),
        T.StructField("international", T.StringType(), True),
        T.StructField("notes", T.StringType(), True),
    ]
)

# COMMAND ----------


def with_lineage(df: DataFrame) -> DataFrame:
    return df.withColumn("_ingested_at", F.current_timestamp()).withColumn(
        "_source_file", F.col("_metadata.file_path")
    )


def write_bronze(df: DataFrame, name: str) -> int:
    table = settings.table("bronze", name)
    with_lineage(df).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    count = spark.table(table).count()
    print(f"{table}: {count} rows")
    return count


counts = {
    "kb_articles": write_bronze(
        spark.read.schema(KB_SCHEMA).json(f"{landing}/kb_articles.jsonl"), "kb_articles"
    ),
    "transcripts": write_bronze(
        spark.read.schema(TRANSCRIPT_SCHEMA).json(f"{landing}/transcripts.jsonl"), "transcripts"
    ),
    "pii_labels": write_bronze(
        spark.read.schema(LABEL_SCHEMA).json(f"{landing}/pii_labels.jsonl"), "pii_labels"
    ),
    "plans": write_bronze(
        spark.read.schema(PLAN_SCHEMA).option("header", "true").csv(f"{landing}/plans.csv"),
        "plans",
    ),
}

# COMMAND ----------

# An empty table means a file was missing or its schema no longer matches.
empty = [name for name, count in counts.items() if count == 0]
if empty:
    raise RuntimeError(f"bronze tables with no rows: {empty}")

dbutils.notebook.exit(json.dumps(counts))
