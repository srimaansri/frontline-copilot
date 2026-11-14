"""Knowledge-base retrieval from the AI Search index.

Queries go through the Databricks SDK (``vector_search_indexes.query_index``),
because it accepts every kind of sign-in the project uses: a CLI profile on a
laptop, the notebook's identity, and an app's service principal. The dedicated
``databricks-ai-search`` client is used to *build* the index (pipeline step 04),
but for querying from outside Databricks it insists on a token or a service
principal.

Each search is recorded as an MLflow ``RETRIEVER`` span whose output is a list of
documents, which is the shape MLflow's retrieval judges read.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

import mlflow
from mlflow.entities import Document, SpanType

from copilot.config import Settings
from copilot.schemas import KBHit

RETURN_COLUMNS: tuple[str, ...] = ("chunk_id", "url", "title", "section", "heading", "text")


class IndexQuery(Protocol):
    """Runs one query against the index and returns ``(column_names, rows)``."""

    def __call__(
        self,
        *,
        index_name: str,
        query_text: str,
        columns: Sequence[str],
        num_results: int,
        filters: dict[str, Any],
        query_type: str,
    ) -> tuple[list[str], list[list[Any]]]:
        """Return the column names and the result rows, best match first."""
        ...


def sdk_index_query() -> IndexQuery:
    """Build an ``IndexQuery`` backed by the Databricks SDK."""
    from databricks.sdk import WorkspaceClient

    workspace = WorkspaceClient()

    def query(
        *,
        index_name: str,
        query_text: str,
        columns: Sequence[str],
        num_results: int,
        filters: dict[str, Any],
        query_type: str,
    ) -> tuple[list[str], list[list[Any]]]:
        response = workspace.vector_search_indexes.query_index(
            index_name=index_name,
            columns=list(columns),
            query_text=query_text,
            num_results=num_results,
            filters_json=json.dumps(filters),
            query_type=query_type.upper(),
        )
        manifest, result = response.manifest, response.result
        columns_found = manifest.columns if manifest and manifest.columns else []
        data = result.data_array if result and result.data_array else []
        return [column.name or "" for column in columns_found], [list(row) for row in data]

    return query


def _to_hit(names: Sequence[str], row: Sequence[Any]) -> KBHit:
    record = dict(zip(names, row, strict=True))
    score = record.get("score")
    return KBHit(
        chunk_id=str(record["chunk_id"]),
        url=str(record["url"]),
        title=str(record["title"]),
        text=str(record["text"]),
        section=record.get("section"),
        heading=record.get("heading") or None,
        score=float(score) if score is not None else None,
    )


def hit_to_document(hit: KBHit) -> Document:
    """Convert a hit to the document shape MLflow's retrieval judges expect."""
    return Document(
        page_content=hit.text,
        metadata={
            "doc_uri": hit.url,
            "chunk_id": hit.chunk_id,
            "title": hit.title,
            "score": hit.score,
        },
        id=hit.chunk_id,
    )


class Retriever:
    """Searches the knowledge base with the configured chunk setting and query type."""

    def __init__(self, settings: Settings, query: IndexQuery | None = None) -> None:
        """Use ``query`` to reach the index, or the Databricks SDK if none is given."""
        self._settings = settings
        self._query = query

    def search(self, question: str, *, top_k: int | None = None) -> list[KBHit]:
        """Return the best-matching chunks for ``question``, best first.

        The caller must pass text that is already free of personal data: the
        question is recorded on the trace.
        """
        settings = self._settings
        if self._query is None:
            self._query = sdk_index_query()
        num_results = top_k or settings.top_k
        with mlflow.start_span(name="search_kb", span_type=SpanType.RETRIEVER) as span:
            span.set_inputs(
                {
                    "query": question,
                    "top_k": num_results,
                    "query_type": settings.query_type,
                    "chunk_config": settings.chunk_config,
                }
            )
            names, rows = self._query(
                index_name=settings.index_name,
                query_text=question,
                columns=RETURN_COLUMNS,
                num_results=num_results,
                filters={"chunk_config": settings.chunk_config},
                query_type=settings.query_type,
            )
            hits = [_to_hit(names, row) for row in rows]
            if settings.min_retrieval_score > 0:
                hits = [
                    hit
                    for hit in hits
                    if hit.score is None or hit.score >= settings.min_retrieval_score
                ]
            span.set_outputs([hit_to_document(hit) for hit in hits])
        return hits
