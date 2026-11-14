# Databricks notebook source
# MAGIC %md
# MAGIC # 03 Chunk: silver to gold
# MAGIC
# MAGIC Splits every knowledge-base article with `copilot.chunking`, once per chunk
# MAGIC configuration, into `gold.kb_chunks`. Both configurations live in one table,
# MAGIC told apart by `chunk_config`, so a single AI Search index serves the experiment.
# MAGIC
# MAGIC The table has Change Data Feed on, which a Delta Sync index requires. Rows are
# MAGIC merged by `chunk_id`, so a re-run with unchanged articles writes nothing and
# MAGIC the index has nothing to re-embed.

# COMMAND ----------

import json

from pyspark.sql import functions as F
from pyspark.sql import types as T

from copilot.chunking import chunk_article, make_chunk_id, tiktoken_counter
from copilot.config import Settings

dbutils.widgets.text("catalog", "frontline")
settings = Settings(catalog=dbutils.widgets.get("catalog"))
count_tokens = tiktoken_counter()

# COMMAND ----------

# 87 articles are chunked on the driver. For a large knowledge base this loop would
# move into `mapInPandas`, as the redaction step does.
articles = spark.table(settings.table("silver", "kb_articles_clean")).collect()

rows = []
for config_name, config in sorted(settings.chunking.items()):
    for article in articles:
        for chunk in chunk_article(
            article["title"],
            article["body_text"],
            chunk_size_tokens=config.chunk_size_tokens,
            overlap_tokens=config.overlap_tokens,
            count_tokens=count_tokens,
        ):
            rows.append(
                (
                    make_chunk_id(article["article_id"], config_name, chunk.chunk_index),
                    article["article_id"],
                    article["url"],
                    article["title"],
                    article["section"],
                    chunk.heading,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.n_tokens,
                    config_name,
                )
            )

CHUNK_SCHEMA = T.StructType(
    [
        T.StructField("chunk_id", T.StringType(), False),
        T.StructField("article_id", T.StringType(), False),
        T.StructField("url", T.StringType(), False),
        T.StructField("title", T.StringType(), False),
        T.StructField("section", T.StringType(), True),
        T.StructField("heading", T.StringType(), True),
        T.StructField("chunk_index", T.IntegerType(), False),
        T.StructField("text", T.StringType(), False),
        T.StructField("n_tokens", T.IntegerType(), False),
        T.StructField("chunk_config", T.StringType(), False),
    ]
)
spark.createDataFrame(rows, CHUNK_SCHEMA).createOrReplaceTempView("new_chunks")
print(f"{len(rows)} chunks from {len(articles)} articles")

# COMMAND ----------

chunks_table = settings.table("gold", "kb_chunks")
spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {chunks_table} (
        chunk_id STRING NOT NULL,
        article_id STRING NOT NULL,
        url STRING NOT NULL,
        title STRING NOT NULL,
        section STRING,
        heading STRING,
        chunk_index INT NOT NULL,
        text STRING NOT NULL,
        n_tokens INT NOT NULL,
        chunk_config STRING NOT NULL,
        CONSTRAINT kb_chunks_pk PRIMARY KEY (chunk_id)
    )
    COMMENT 'Knowledge-base chunks for retrieval. One row per chunk per chunk_config.'
    TBLPROPERTIES (delta.enableChangeDataFeed = true)
    """
)
# Also covers a table that was created before this property was added.
spark.sql(f"ALTER TABLE {chunks_table} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")

merged = spark.sql(
    f"""
    MERGE INTO {chunks_table} AS target
    USING new_chunks AS source
    ON target.chunk_id = source.chunk_id
    WHEN MATCHED AND (
        target.text <> source.text
        OR target.n_tokens <> source.n_tokens
        OR target.url <> source.url
        OR target.title <> source.title
        OR NOT (target.section <=> source.section)
        OR NOT (target.heading <=> source.heading)
    ) THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    WHEN NOT MATCHED BY SOURCE THEN DELETE
    """
).collect()[0]

# COMMAND ----------

gold_plans = settings.table("gold", "plans")
(
    spark.table(settings.table("silver", "plans"))
    .write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(gold_plans)
)

# COMMAND ----------

summary = (
    spark.table(chunks_table)
    .groupBy("chunk_config")
    .agg(
        F.count("*").alias("chunks"),
        F.countDistinct("article_id").alias("articles"),
        F.min("n_tokens").alias("min_tokens"),
        F.expr("percentile(n_tokens, 0.5)").cast("int").alias("median_tokens"),
        F.max("n_tokens").alias("max_tokens"),
    )
    .orderBy("chunk_config")
)
display(summary)

cdf_on = (
    spark.sql(f"SHOW TBLPROPERTIES {chunks_table} ('delta.enableChangeDataFeed')").collect()[0][
        "value"
    ]
    == "true"
)
if not cdf_on:
    raise RuntimeError(f"Change Data Feed is not enabled on {chunks_table}")

dbutils.notebook.exit(
    json.dumps(
        {
            "configs": {row["chunk_config"]: row.asDict() for row in summary.collect()},
            "merge": merged.asDict(),
            "change_data_feed": cdf_on,
            "plans": spark.table(gold_plans).count(),
        }
    )
)
