"""Scorers for the copilot evaluation.

Two kinds:

* **Deterministic scorers**, defined here. They read the answer and the trace
  and need no model, so they are cheap and repeatable. Their logic is in plain
  functions that are unit-tested; the ``@scorer`` wrappers only adapt them.
* **LLM judges**, built by ``llm_judges``. These are MLflow's built-in judges
  plus one RAGAS metric, all pointed at a judge model that is not the copilot's
  own model.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import textstat
from mlflow.entities import Feedback, SpanType, Trace
from mlflow.genai.scorers import (
    Correctness,
    ExpectationsGuidelines,
    RelevanceToQuery,
    RetrievalGroundedness,
    RetrievalRelevance,
    RetrievalSufficiency,
    Safety,
    scorer,
)
from mlflow.genai.scorers.base import Scorer

READING_GRADE_TARGET = 8.0
ROOT_SPAN_NAME = "run_copilot"

_CITATION_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_MARKDOWN_RE = re.compile(r"[*_`#>]+")
_LIST_MARKER_RE = re.compile(r"^[ \t]*(?:\d+[.)]|[-*])[ \t]+", re.MULTILINE)


# --- plain functions ---------------------------------------------------------------------


def plain_text_for_reading_level(answer: str) -> str:
    """Strip citation markers and Markdown so they do not distort the reading grade."""
    text = _CITATION_RE.sub("", answer)
    text = _LIST_MARKER_RE.sub("", text)
    text = _MARKDOWN_RE.sub("", text)
    # Removing a citation leaves a space before the punctuation that followed it.
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def reading_grade(answer: str) -> float:
    """Flesch-Kincaid grade of an answer. Lower is easier to read."""
    text = plain_text_for_reading_level(answer)
    return float(textstat.flesch_kincaid_grade(text)) if text else 0.0


def source_rank(doc_uris: Sequence[str], expected_source: str) -> int | None:
    """1-based position of the expected article among the retrieved documents."""
    for position, uri in enumerate(doc_uris, start=1):
        if uri.rstrip("/").endswith("/" + expected_source):
            return position
    return None


def acceptable_sources(expectations: Mapping[str, Any] | None) -> list[str]:
    """The expected article first, then any other article that also holds the full answer."""
    expected = (expectations or {}).get("expected_source")
    if not expected:
        return []
    return [str(expected), *(expectations or {}).get("also_acceptable_sources", [])]


def best_source_rank(doc_uris: Sequence[str], sources: Sequence[str]) -> int | None:
    """Best 1-based position of any acceptable article among the documents."""
    ranks = [rank for source in sources if (rank := source_rank(doc_uris, source)) is not None]
    return min(ranks) if ranks else None


def root_output(trace: Trace) -> dict[str, Any]:
    """The ``CopilotAnswer`` recorded on the copilot's root span."""
    for span in trace.search_spans(name=ROOT_SPAN_NAME):
        if isinstance(span.outputs, dict):
            return span.outputs
    return {}


def retrieved_uris(trace: Trace) -> list[str]:
    """``doc_uri`` of every retrieved document, in rank order."""
    uris: list[str] = []
    for span in trace.search_spans(span_type=SpanType.RETRIEVER):
        for document in span.outputs or []:
            metadata = document.get("metadata", {}) if isinstance(document, dict) else {}
            if metadata.get("doc_uri"):
                uris.append(str(metadata["doc_uri"]))
    return uris


# --- scorers -----------------------------------------------------------------------------


@scorer
def reading_level(outputs: Any) -> list[Feedback]:
    """Raw reading grade, and whether it is at or below the target."""
    grade = reading_grade(str(outputs or ""))
    return [
        Feedback(name="reading_grade", value=round(grade, 2)),
        Feedback(
            name="reading_level_ok",
            value=grade <= READING_GRADE_TARGET,
            rationale=f"Flesch-Kincaid grade {grade:.1f}, target {READING_GRADE_TARGET:.0f}",
        ),
    ]


def citations_ok(output: Mapping[str, Any], *, citation_required: bool) -> bool:
    """No invalid citation was removed and, where one is required, a source is cited.

    A citation is required only when the row names an article that holds the
    answer. A correct "the help articles do not cover this" has nothing to cite.
    """
    flags = output.get("guardrail_flags") or []
    cited = len(output.get("citations") or [])
    return "invalid_citation_removed" not in flags and (cited > 0 or not citation_required)


@scorer
def citation_valid(expectations: Mapping[str, Any], trace: Trace) -> Feedback:
    """Citations are valid, and present where the row expects an article to be cited."""
    output = root_output(trace)
    required = bool(acceptable_sources(expectations))
    return Feedback(
        name="citation_valid",
        value=citations_ok(output, citation_required=required),
        rationale=(
            f"{len(output.get('citations') or [])} valid citations; "
            f"citation {'required' if required else 'not required'}; "
            f"flags {output.get('guardrail_flags') or []}"
        ),
    )


@scorer
def expected_source(expectations: Mapping[str, Any], trace: Trace) -> list[Feedback]:
    """Was an article that holds the answer retrieved, at what rank, and was it cited?

    A row may list ``also_acceptable_sources`` next to ``expected_source`` when a
    second article holds the whole answer. The best-ranked of them counts.
    """
    wanted = acceptable_sources(expectations)
    if not wanted:
        return []
    rank = best_source_rank(retrieved_uris(trace), wanted)
    cited_urls = [str(c.get("url", "")) for c in root_output(trace).get("citations") or []]
    return [
        Feedback(
            name="expected_source_retrieved",
            value=rank is not None,
            rationale=f"rank {rank} (accepted: {', '.join(wanted)})"
            if rank
            else f"none of {', '.join(wanted)} in the retrieved set",
        ),
        Feedback(name="expected_source_reciprocal_rank", value=round(1 / rank, 4) if rank else 0.0),
        Feedback(
            name="expected_source_cited", value=best_source_rank(cited_urls, wanted) is not None
        ),
    ]


@scorer
def latency_ms(trace: Trace) -> Feedback:
    """End-to-end time of the copilot call, from the trace."""
    return Feedback(name="latency_ms", value=float(trace.info.execution_duration or 0))


DETERMINISTIC_SCORERS: tuple[Scorer, ...] = (
    reading_level,
    citation_valid,
    expected_source,
    latency_ms,
)


def when_expected(judge: Scorer, *keys: str) -> Scorer:
    """Run ``judge`` only on rows whose expectations hold one of ``keys``.

    The evaluation set mixes rows graded by facts with rows graded by rules.
    MLflow's ``Correctness`` and ``ExpectationsGuidelines`` raise on a row that
    lacks what they grade against, which would show as an error on every such
    row. Wrapped this way the judge is skipped there and the row is not counted
    for it.
    """

    @scorer(name=judge.name)
    def conditional(
        inputs: Mapping[str, Any], outputs: Any, expectations: Mapping[str, Any]
    ) -> Feedback | None:
        if not any((expectations or {}).get(key) for key in keys):
            return None
        result: Feedback = judge(inputs=inputs, outputs=outputs, expectations=expectations)
        return result

    return conditional


def llm_judges(judge_endpoint: str, *, include_ragas: bool = True) -> list[Scorer]:
    """MLflow's built-in judges plus RAGAS ContextPrecision, all using ``judge_endpoint``.

    ``Correctness`` grades rows that list expected facts. ``ExpectationsGuidelines``
    grades rows that list rules the answer must follow; some rows have both.

    RAGAS Faithfulness is left out on purpose: it measures what
    ``RetrievalGroundedness`` already measures and would double the judge calls.
    """
    model = f"databricks:/{judge_endpoint}"
    judges: list[Scorer] = [
        RetrievalGroundedness(model=model),
        RelevanceToQuery(model=model),
        RetrievalRelevance(model=model),
        RetrievalSufficiency(model=model),
        when_expected(Correctness(model=model), "expected_facts", "expected_response"),
        when_expected(ExpectationsGuidelines(model=model), "guidelines"),
        Safety(model=model),
    ]
    if include_ragas:
        from mlflow.genai.scorers.ragas import ContextPrecision

        judges.append(ContextPrecision(model=model))
    return judges
