# Databricks notebook source
# MAGIC %md
# MAGIC # 04 Index: build the AI Search index
# MAGIC
# MAGIC Creates a Delta Sync index over `gold.kb_chunks` with embeddings computed by
# MAGIC Databricks, waits until it is ready, then runs a few smoke queries.
# MAGIC
# MAGIC Free Edition allows Delta Sync indexes only (no Direct Vector Access), on one
# MAGIC endpoint. Both chunk configurations share this index and are separated at query
# MAGIC time with a filter on `chunk_config`.
# MAGIC
# MAGIC Safe to re-run: an existing index is synced, not recreated.

# COMMAND ----------

import json
from datetime import timedelta

from databricks.ai_search.client import AISearchClient

from copilot.config import Settings

dbutils.widgets.text("catalog", "frontline")
dbutils.widgets.text("vs_endpoint", "frontline-vs")
dbutils.widgets.text("embedding_endpoint", "databricks-gte-large-en")
settings = Settings(
    catalog=dbutils.widgets.get("catalog"),
    vs_endpoint=dbutils.widgets.get("vs_endpoint"),
    embedding_endpoint=dbutils.widgets.get("embedding_endpoint"),
)
source_table = settings.table("gold", "kb_chunks")
index_name = settings.index_name
RETURN_COLUMNS = ["chunk_id", "url", "title", "section", "heading", "chunk_config", "text"]

client = AISearchClient(disable_notice=True)

# COMMAND ----------

if client.index_exists(endpoint_name=settings.vs_endpoint, index_name=index_name):
    print(f"{index_name} exists: syncing")
    index = client.get_index(endpoint_name=settings.vs_endpoint, index_name=index_name)
    index.sync()
    created = False
else:
    print(f"creating {index_name} on {settings.vs_endpoint}")
    index = client.create_delta_sync_index(
        endpoint_name=settings.vs_endpoint,
        index_name=index_name,
        source_table_name=source_table,
        primary_key="chunk_id",
        pipeline_type="TRIGGERED",
        embedding_source_column="text",
        embedding_model_endpoint_name=settings.embedding_endpoint,
        # The primary key and the embedded column are always included.
        columns_to_sync=["url", "title", "section", "heading", "chunk_config"],
    )
    created = True

# `wait_for_updates` also waits for a sync that was just triggered to finish.
index.wait_until_ready(verbose=True, timeout=timedelta(minutes=40), wait_for_updates=True)

# COMMAND ----------

description = index.describe()
status = description.get("status", {})
indexed_rows = status.get("indexed_row_count")
source_rows = spark.table(source_table).count()
print(f"ready={status.get('ready')} indexed_rows={indexed_rows} source_rows={source_rows}")
if not status.get("ready"):
    raise RuntimeError(f"index is not ready: {status}")
if indexed_rows is not None and indexed_rows != source_rows:
    raise RuntimeError(f"index has {indexed_rows} rows but {source_table} has {source_rows}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Smoke queries
# MAGIC
# MAGIC Each question is run four ways: both chunk configurations, each with vector
# MAGIC search (ANN, the default) and with hybrid search. These are the query paths the
# MAGIC evaluation in Milestone 3 depends on.

# COMMAND ----------

QUESTIONS = {
    "How do I set up voicemail on a new phone?": "set-up-voicemail",
    "How much is the late payment fee?": "late-payment-fee",
    "Will my phone work in Mexico?": "canada-and-mexico",
    "I lost my phone, what should I do?": "lost-or-stolen-phone",
    "How do I get a transfer PIN to move my number?": "transfer-number-away",
}

smoke = []
for question, expected_slug in QUESTIONS.items():
    for chunk_config in sorted(settings.chunking):
        for query_type in ("ann", "hybrid"):
            arguments = {
                "query_text": question,
                "columns": RETURN_COLUMNS,
                "num_results": 3,
                "filters": {"chunk_config": chunk_config},
                "disable_notice": True,
            }
            if query_type == "hybrid":
                # ANN is the default and is selected by leaving query_type out.
                arguments["query_type"] = "hybrid"
            response = index.similarity_search(**arguments)
            names = [column["name"] for column in response["manifest"]["columns"]]
            hits = [dict(zip(names, row, strict=True)) for row in response["result"]["data_array"]]
            smoke.append(
                {
                    "question": question,
                    "chunk_config": chunk_config,
                    "query_type": query_type,
                    "hits": len(hits),
                    "top_url": hits[0]["url"] if hits else None,
                    "top_score": hits[0].get("score") if hits else None,
                    "expected_in_top3": any(hit["url"].endswith(expected_slug) for hit in hits),
                    "only_this_config": all(hit["chunk_config"] == chunk_config for hit in hits),
                }
            )

display(spark.createDataFrame(smoke))

# COMMAND ----------

problems = [row for row in smoke if row["hits"] == 0 or not row["only_this_config"]]
if problems:
    raise RuntimeError(f"smoke queries returned nothing or ignored the filter: {problems}")

dbutils.notebook.exit(
    json.dumps(
        {
            "index": index_name,
            "created": created,
            "indexed_rows": indexed_rows,
            "source_rows": source_rows,
            "smoke_queries": len(smoke),
            "expected_article_in_top3": sum(row["expected_in_top3"] for row in smoke),
            "smoke": smoke,
        }
    )
)
