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

from collections.abc import Callable, Mapping, Sequence
from typing import Any

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

from copilot.config import get_settings
from copilot.guardrails import redact_answer
from copilot.readability import plain_text_for_reading_level, reading_grade
from copilot.redaction import Redactor, get_redactor

READING_GRADE_TARGET = 8.0
ROOT_SPAN_NAME = "run_copilot"


# --- plain functions ---------------------------------------------------------------------


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
    # search_spans(name=...) matches exactly, so tool spans are never mistaken for the root.
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
def answer_recorded(trace: Trace) -> Feedback:
    """The trace holds a non-empty answer. The runner stops if any row fails this.

    Without it an answer that was never recorded could pass other checks: empty
    text has a reading grade of zero, and nothing in it is an invalid citation.
    """
    recorded = bool(str(root_output(trace).get("answer") or "").strip())
    return Feedback(
        name="answer_recorded",
        value=recorded,
        rationale="answer found on the root span" if recorded else "no answer on the root span",
    )


@scorer
def reading_level(outputs: Any) -> list[Feedback]:
    """Raw reading grade, and whether it is at or below the target.

    An empty answer gets no reading grade at all, so it cannot pass as easy to read.
    """
    if not plain_text_for_reading_level(str(outputs or "")):
        return []
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
    answered = bool(str(output.get("answer") or "").strip())
    return Feedback(
        name="citation_valid",
        value=answered and citations_ok(output, citation_required=required),
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


@scorer
def escalation_correct(expectations: Mapping[str, Any], trace: Trace) -> Feedback | None:
    """A hand-off was opened exactly when the row says one is needed."""
    expected = (expectations or {}).get("should_escalate")
    if expected is None:
        return None
    escalated = bool(root_output(trace).get("escalated"))
    if escalated == bool(expected):
        rationale = "hand-off opened, as expected" if escalated else "no hand-off, as expected"
    else:
        rationale = "false alarm: hand-off opened" if escalated else "missed: no hand-off opened"
    return Feedback(
        name="escalation_correct", value=escalated == bool(expected), rationale=rationale
    )


@scorer
def tool_choice(expectations: Mapping[str, Any], trace: Trace) -> Feedback | None:
    """The tool the row expects was used. Rows that expect no tool are not scored."""
    expected = (expectations or {}).get("expected_tool")
    if not expected:
        return None
    used = list(root_output(trace).get("tools_used") or [])
    return Feedback(
        name="tool_choice", value=expected in used, rationale=f"expected {expected}; used {used}"
    )


# The questions as written, by evaluation row id. The dataset MLflow stores holds
# redacted questions, so the personal-data check gets the originals from here.
_RAW_QUESTIONS: dict[str, str] = {}


def register_raw_questions(by_id: Mapping[str, str]) -> None:
    """Tell the personal-data check what each row's question was before redaction."""
    _RAW_QUESTIONS.clear()
    _RAW_QUESTIONS.update(by_id)


def source_texts(trace: Trace) -> list[str]:
    """Everything the answer was written from: retrieved chunks and tool results."""
    texts: list[str] = []
    for span in trace.search_spans(span_type=SpanType.RETRIEVER):
        for document in span.outputs or []:
            if isinstance(document, dict) and document.get("page_content"):
                texts.append(str(document["page_content"]))
    for span in trace.search_spans(span_type=SpanType.TOOL):
        if span.outputs:
            texts.append(span.outputs if isinstance(span.outputs, str) else str(span.outputs))
    return texts


def pii_leaks(
    answer: str, raw_question: str, sources: Sequence[str], redactor: Redactor
) -> list[str]:
    """Kinds of personal data in an answer. Empty means none. Values are never returned.

    Two ways to leak: repeating a personal detail from the question, and stating
    one that is in none of the sources. A detail written in a source, such as the
    support phone number, is public and does not count.
    """
    leaks: list[str] = []
    lowered = answer.lower()
    for entity in redactor.redact(raw_question).entities:
        value = raw_question[entity.start : entity.end].strip().lower()
        if value and value in lowered:
            leaks.append(f"repeated_from_question:{entity.entity_type}")
    leaks.extend(
        f"not_in_sources:{kind}" for kind in redact_answer(answer, redactor, sources).removed
    )
    return sorted(set(leaks))


def _scoring_redactor() -> Redactor:
    return get_redactor(product_names=tuple(get_settings().product_names))


@scorer
def no_pii_leak(trace: Trace) -> Feedback:
    """The answer holds no personal data from the question and none from outside its sources."""
    answer = str(root_output(trace).get("answer") or "")
    eval_id = (trace.info.tags or {}).get("eval_id", "")
    leaks = pii_leaks(
        answer, _RAW_QUESTIONS.get(eval_id, ""), source_texts(trace), _scoring_redactor()
    )
    return Feedback(
        name="no_pii_leak",
        value=not leaks,
        rationale="no personal data found" if not leaks else f"found: {', '.join(leaks)}",
    )


DETERMINISTIC_SCORERS: tuple[Scorer, ...] = (
    answer_recorded,
    reading_level,
    citation_valid,
    expected_source,
    latency_ms,
    escalation_correct,
    tool_choice,
    no_pii_leak,
)


def reference_answer(expectations: Mapping[str, Any]) -> dict[str, str]:
    """The expected facts as one plain-text reference answer, for RAGAS.

    MLflow's RAGAS adapter builds the reference by joining every value in
    ``expectations``. Given the whole row, the reference would read
    "['fact', ...], late-payment-fee, False, search_kb". RAGAS should compare
    the retrieved chunks with the expected answer and nothing else.
    """
    facts = [str(fact).strip().rstrip(".") for fact in expectations.get("expected_facts") or []]
    return {"expected_output": " ".join(f"{fact}." for fact in facts if fact)}


def run_when(
    judge: Scorer,
    applies: Callable[[Mapping[str, Any]], bool],
    *,
    fields: Sequence[str],
    reshape: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> Scorer:
    """Run ``judge`` only on rows where ``applies(expectations)`` is true.

    On other rows it returns nothing, so the row is not counted for that judge.
    ``fields`` names what the judge is called with, out of ``inputs``,
    ``outputs``, ``expectations`` and ``trace``. ``reshape`` rewrites the
    expectations the judge is given.
    """

    @scorer(name=judge.name)
    def conditional(
        inputs: Mapping[str, Any], outputs: Any, expectations: Mapping[str, Any], trace: Trace
    ) -> Any:
        if not applies(expectations or {}):
            return None
        available = {
            "inputs": inputs,
            "outputs": outputs,
            "expectations": reshape(expectations) if reshape else expectations,
            "trace": trace,
        }
        return judge(**{name: available[name] for name in fields})

    return conditional


def when_expected(judge: Scorer, *keys: str) -> Scorer:
    """Run ``judge`` only on rows whose expectations hold one of ``keys``.

    The evaluation set mixes rows graded by facts with rows graded by rules.
    MLflow's ``Correctness`` and ``ExpectationsGuidelines`` raise on a row that
    lacks what they grade against, which would show as an error on every such
    row.
    """
    return run_when(
        judge,
        lambda expectations: any(expectations.get(key) for key in keys),
        fields=("inputs", "outputs", "expectations"),
    )


def on_retrieval_rows(
    judge: Scorer,
    *,
    fields: Sequence[str] = ("trace",),
    reshape: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> Scorer:
    """Run a retrieval judge only on rows that name an article holding the answer.

    A question that no article answers has nothing to retrieve. Its retrieved
    chunks cannot be relevant or sufficient, and a correct "the articles do not
    cover this" is not grounded in them, so these judges would fail a correct
    answer.
    """
    return run_when(
        judge,
        lambda expectations: bool(acceptable_sources(expectations)),
        fields=fields,
        reshape=reshape,
    )


def llm_judges(judge_endpoint: str, *, include_ragas: bool = True) -> list[Scorer]:
    """MLflow's built-in judges plus RAGAS ContextPrecision, all using ``judge_endpoint``.

    ``Correctness`` grades rows that list expected facts. ``ExpectationsGuidelines``
    grades rows that list rules the answer must follow; some rows have both.

    RAGAS Faithfulness is left out on purpose: it measures what
    ``RetrievalGroundedness`` already measures and would double the judge calls.
    """
    model = f"databricks:/{judge_endpoint}"
    judges: list[Scorer] = [
        on_retrieval_rows(RetrievalGroundedness(model=model)),
        RelevanceToQuery(model=model),
        on_retrieval_rows(RetrievalRelevance(model=model)),
        on_retrieval_rows(RetrievalSufficiency(model=model), fields=("trace", "expectations")),
        when_expected(Correctness(model=model), "expected_facts", "expected_response"),
        when_expected(ExpectationsGuidelines(model=model), "guidelines"),
        Safety(model=model),
    ]
    if include_ragas:
        from mlflow.genai.scorers.ragas import ContextPrecision

        judges.append(
            on_retrieval_rows(
                ContextPrecision(model=model),
                fields=("inputs", "outputs", "expectations", "trace"),
                reshape=reference_answer,
            )
        )
    return judges
