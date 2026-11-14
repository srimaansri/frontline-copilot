"""The evaluation set, the scorers' logic and the runner's bookkeeping. No model calls."""

import types
from collections import Counter
from typing import Any

import pytest
from mlflow.entities import Feedback

from data_gen.kb_topics import TOPICS
from data_gen.plans import PLANS
from eval.run_eval import (
    EVAL_ID_TAG,
    SUMMARY_HEADER,
    aggregate,
    as_pass,
    load_eval_set,
    mean_text,
    rate_text,
    rows_by_eval_id,
    rows_without_answer,
    scores_from_trace,
    summary_row,
    to_records,
)
from eval.scorers import (
    DETERMINISTIC_SCORERS,
    acceptable_sources,
    answer_recorded,
    best_source_rank,
    citation_valid,
    citations_ok,
    expected_source,
    latency_ms,
    llm_judges,
    on_retrieval_rows,
    plain_text_for_reading_level,
    reading_grade,
    reading_level,
    reference_answer,
    retrieved_uris,
    root_output,
    source_rank,
    when_expected,
)

BASE = "https://help.northline.example/articles"


def fake_trace(
    *,
    answer: dict[str, Any] | None = None,
    uris: list[str] | None = None,
    duration: int = 1500,
    tags: dict[str, str] | None = None,
    assessments: list[Any] | None = None,
) -> Any:
    documents = [{"page_content": "x", "metadata": {"doc_uri": uri}} for uri in uris or []]

    def search_spans(name: str | None = None, span_type: str | None = None) -> list[Any]:
        if name == "run_copilot":
            return [types.SimpleNamespace(outputs=answer)] if answer is not None else []
        if span_type == "RETRIEVER":
            return [types.SimpleNamespace(outputs=documents)]
        return []

    return types.SimpleNamespace(
        search_spans=search_spans,
        info=types.SimpleNamespace(
            execution_duration=duration, tags=tags or {}, assessments=assessments or []
        ),
    )


def feedback(name: str, value: Any, error: Any = None) -> Any:
    return types.SimpleNamespace(
        name=name, feedback=types.SimpleNamespace(value=value, error=error)
    )


# --- the evaluation set -----------------------------------------------------------------


def test_eval_set_has_the_planned_mix_and_unique_ids() -> None:
    rows = load_eval_set()

    assert len(rows) == 40
    assert len({row["id"] for row in rows}) == 40
    assert Counter(row["category"] for row in rows) == {
        "kb": 22,
        "plan": 6,
        "call_summary": 4,
        "escalation": 5,
        "adversarial": 3,
    }
    assert all(isinstance(row["reviewed"], bool) for row in rows)
    assert all(row["inputs"]["question"].strip() for row in rows)


def test_every_kb_row_points_at_a_real_article_and_has_facts() -> None:
    """A kb row names its article and facts, unless it tests a question no article answers."""
    slugs = {topic.slug for topic in TOPICS}

    for row in load_eval_set(category="kb"):
        expectations = row["expectations"]
        assert expectations["should_escalate"] is False
        if "expected_source" not in expectations:
            # A no-answer row: nothing true can be listed, so it is graded by its rules.
            assert expectations["guidelines"], row["id"]
            assert "expected_facts" not in expectations, row["id"]
            continue
        assert expectations["expected_source"] in slugs, row["id"]
        assert len(expectations["expected_facts"]) >= 2, row["id"]


def test_alternate_sources_are_real_articles_next_to_an_expected_one() -> None:
    slugs = {topic.slug for topic in TOPICS}

    for row in load_eval_set():
        expectations = row["expectations"]
        alternates = expectations.get("also_acceptable_sources", [])
        if alternates:
            assert expectations["expected_source"] not in alternates, row["id"]
            assert set(alternates) <= slugs, row["id"]


def test_prices_in_plan_rows_exist_in_the_catalogue() -> None:
    prices = {f"${row.monthly_price_usd:.0f}" for row in PLANS}

    for row in load_eval_set(category="plan"):
        for fact in row["expectations"]["expected_facts"]:
            quoted = {word.rstrip(".,") for word in fact.split() if word.startswith("$")}
            assert quoted <= prices, (row["id"], fact)


def test_escalation_rows_expect_escalation() -> None:
    rows = load_eval_set(category="escalation")

    assert all(row["expectations"]["should_escalate"] is True for row in rows)
    assert all(row["expectations"]["expected_tool"] == "escalate_to_human" for row in rows)


def test_category_filter_and_limit() -> None:
    assert [row["id"] for row in load_eval_set(category="kb", limit=2)] == ["E001", "E002"]
    assert load_eval_set(category="nope") == []


def test_records_drop_null_expectations_and_keep_the_rest() -> None:
    rows = [
        {
            "inputs": {"question": "Q"},
            "expectations": {"expected_tool": None, "should_escalate": False},
        }
    ]

    assert to_records(rows) == [
        {"inputs": {"question": "Q"}, "expectations": {"should_escalate": False}}
    ]


# --- scorer logic ---------------------------------------------------------------------------


def test_reading_text_drops_citations_markdown_and_list_markers() -> None:
    answer = "**The fee is $5** [1].\n\n1. Dial `611` [2, 3].\n- Ask for a waiver."

    assert plain_text_for_reading_level(answer) == "The fee is $5.\n\nDial 611.\nAsk for a waiver."


def test_reading_grade_is_lower_for_simpler_text() -> None:
    simple = "You can pay in the app. It is free. Tap Billing. Then tap Pay."
    dense = (
        "Remuneration of outstanding telecommunications obligations necessitates authentication "
        "via the proprietary application preceding the authorisation of electronic disbursement."
    )

    assert reading_grade(simple) < 5 < reading_grade(dense)
    assert reading_grade("") == 0.0


def test_source_rank_finds_the_article_by_its_slug() -> None:
    uris = [f"{BASE}/set-up-autopay", f"{BASE}/late-payment-fee/"]

    assert source_rank(uris, "late-payment-fee") == 2
    assert source_rank(uris, "set-up-autopay") == 1
    # A slug that is only the end of another slug is not a match.
    assert source_rank(uris, "fee") is None
    assert source_rank([], "late-payment-fee") is None


def test_trace_readers() -> None:
    trace = fake_trace(answer={"answer": "A"}, uris=[f"{BASE}/a", f"{BASE}/b"])

    assert root_output(trace) == {"answer": "A"}
    assert retrieved_uris(trace) == [f"{BASE}/a", f"{BASE}/b"]
    assert root_output(fake_trace()) == {}
    assert retrieved_uris(fake_trace()) == []


def test_reading_level_scorer_reports_grade_and_verdict() -> None:
    grade, verdict = reading_level(outputs="You can pay in the app. It is free.")

    assert grade.name == "reading_grade"
    assert verdict.name == "reading_level_ok"
    assert verdict.value is True
    assert isinstance(grade.value, float)


def test_citation_scorer() -> None:
    cited = {"answer": "A [1].", "citations": [{"url": f"{BASE}/a"}], "guardrail_flags": []}
    removed = {**cited, "guardrail_flags": ["invalid_citation_removed"]}
    uncited = {"answer": "A.", "citations": [], "guardrail_flags": ["no_citation"]}

    row = {"expected_source": "a"}

    assert citation_valid(expectations=row, trace=fake_trace(answer=cited)).value is True
    assert citation_valid(expectations=row, trace=fake_trace(answer=removed)).value is False
    assert citation_valid(expectations=row, trace=fake_trace(answer=uncited)).value is False


def test_citation_is_required_only_where_the_row_names_an_article() -> None:
    """A correct 'the articles do not cover this' has nothing to cite."""
    uncited = {"answer": "A.", "citations": [], "guardrail_flags": ["no_citation"]}
    removed = {"answer": "A.", "citations": [], "guardrail_flags": ["invalid_citation_removed"]}
    no_source_row = {"guidelines": ["The response must say the articles do not answer this"]}

    assert citation_valid(expectations=no_source_row, trace=fake_trace(answer=uncited)).value
    # An invented citation still fails, whether or not one was required.
    assert not citation_valid(expectations=no_source_row, trace=fake_trace(answer=removed)).value
    assert citations_ok(uncited, citation_required=False) is True
    assert citations_ok(uncited, citation_required=True) is False


def test_an_empty_or_missing_answer_cannot_pass() -> None:
    """Empty text reads as grade zero and has no invalid citation; neither may count as a pass."""
    no_source_row = {"guidelines": ["The response must decline"]}
    blank = fake_trace(answer={"answer": "  ", "citations": [], "guardrail_flags": []})
    missing = fake_trace()

    assert answer_recorded(trace=fake_trace(answer={"answer": "A."})).value is True
    assert answer_recorded(trace=blank).value is False
    assert answer_recorded(trace=missing).value is False
    assert citation_valid(expectations=no_source_row, trace=blank).value is False
    assert citation_valid(expectations=no_source_row, trace=missing).value is False
    assert reading_level(outputs="") == []
    assert reading_level(outputs=None) == []
    assert reading_level(outputs=" [1] ") == []


def test_expected_source_scorer() -> None:
    answer = {"citations": [{"url": f"{BASE}/late-payment-fee"}]}
    trace = fake_trace(answer=answer, uris=[f"{BASE}/set-up-autopay", f"{BASE}/late-payment-fee"])

    retrieved, reciprocal_rank, cited = expected_source(
        expectations={"expected_source": "late-payment-fee"}, trace=trace
    )

    assert (retrieved.name, retrieved.value) == ("expected_source_retrieved", True)
    assert reciprocal_rank.value == 0.5
    assert (cited.name, cited.value) == ("expected_source_cited", True)


def test_expected_source_scorer_when_the_article_was_not_retrieved() -> None:
    trace = fake_trace(answer={"citations": []}, uris=[f"{BASE}/set-up-autopay"])

    retrieved, reciprocal_rank, cited = expected_source(
        expectations={"expected_source": "late-payment-fee"}, trace=trace
    )

    assert retrieved.value is False
    assert reciprocal_rank.value == 0.0
    assert cited.value is False


def test_expected_source_scorer_is_silent_without_an_expected_source() -> None:
    assert expected_source(expectations={}, trace=fake_trace()) == []
    # Alternates alone do not make a row a retrieval row.
    only_alternates = {"also_acceptable_sources": ["compare-plans"]}
    assert expected_source(expectations=only_alternates, trace=fake_trace()) == []


def test_acceptable_sources_lists_the_expected_article_first() -> None:
    row = {"expected_source": "canada-and-mexico", "also_acceptable_sources": ["compare-plans"]}

    assert acceptable_sources(row) == ["canada-and-mexico", "compare-plans"]
    assert acceptable_sources({"expected_source": "canada-and-mexico"}) == ["canada-and-mexico"]
    assert acceptable_sources({}) == []
    assert acceptable_sources(None) == []


def test_best_source_rank_takes_the_highest_placed_acceptable_article() -> None:
    uris = [f"{BASE}/a", f"{BASE}/compare-plans", f"{BASE}/canada-and-mexico"]

    assert best_source_rank(uris, ["canada-and-mexico", "compare-plans"]) == 2
    assert best_source_rank(uris, ["canada-and-mexico"]) == 3
    assert best_source_rank(uris, ["late-payment-fee"]) is None


def test_expected_source_scorer_accepts_an_alternate_article() -> None:
    answer = {"citations": [{"url": f"{BASE}/compare-plans"}]}
    trace = fake_trace(answer=answer, uris=[f"{BASE}/compare-plans", f"{BASE}/set-up-autopay"])
    row = {"expected_source": "canada-and-mexico", "also_acceptable_sources": ["compare-plans"]}

    retrieved, reciprocal_rank, cited = expected_source(expectations=row, trace=trace)

    assert retrieved.value is True
    assert reciprocal_rank.value == 1.0
    assert cited.value is True
    # Without the alternate listed, the same trace is a miss.
    strict = expected_source(expectations={"expected_source": "canada-and-mexico"}, trace=trace)
    assert [item.value for item in strict] == [False, 0.0, False]


def test_latency_scorer_reads_the_trace_duration() -> None:
    assert latency_ms(trace=fake_trace(duration=2345)).value == 2345.0


def test_judges_use_the_judge_endpoint_and_leave_out_ragas_faithfulness() -> None:
    judges = llm_judges("my-judge")
    names = {judge.name for judge in judges}

    assert len(DETERMINISTIC_SCORERS) == 5
    assert {"retrieval_groundedness", "correctness", "relevance_to_query", "safety"} <= names
    assert "expectations_guidelines" in names
    assert {"retrieval_relevance", "retrieval_sufficiency"} <= names
    assert any("ContextPrecision" in name for name in names)
    assert not any("Faithfulness" in name for name in names)
    assert all(getattr(judge, "model", "databricks:/my-judge") == "databricks:/my-judge"
               for judge in judges)  # fmt: skip
    assert len(llm_judges("my-judge", include_ragas=False)) == len(judges) - 1


class RecordingJudge:
    """Stands in for a model-backed judge and records what it was asked."""

    name = "fake_judge"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Feedback:
        self.calls.append(kwargs)
        return Feedback(name=self.name, value="yes")


def test_a_judge_runs_only_on_rows_that_have_what_it_grades() -> None:
    judge = RecordingJudge()
    wrapped = when_expected(judge, "guidelines")  # type: ignore[arg-type]
    rules = {"guidelines": ["The response must not contain a poem"]}

    question = {"question": "Q"}
    facts_only = {"expected_facts": ["x"]}

    skipped = wrapped(inputs=question, outputs="A", expectations=facts_only, trace=None)
    graded = wrapped(inputs=question, outputs="A", expectations=rules, trace=None)

    assert wrapped.name == "fake_judge"
    assert skipped is None
    assert graded.value == "yes"
    # The judge gets the answer and the row, not the trace.
    assert judge.calls == [{"inputs": question, "outputs": "A", "expectations": rules}]


def test_a_judge_is_skipped_when_the_expectation_is_empty() -> None:
    judge = RecordingJudge()
    wrapped = when_expected(judge, "expected_facts", "expected_response")  # type: ignore[arg-type]
    empty = {"expected_facts": []}
    response = {"expected_response": "x"}

    assert wrapped(inputs={}, outputs="A", expectations=empty, trace=None) is None
    assert wrapped(inputs={}, outputs="A", expectations=response, trace=None) is not None
    assert len(judge.calls) == 1


def test_retrieval_judges_run_only_on_rows_that_name_an_article() -> None:
    """A question no article answers has nothing to retrieve, so nothing to judge."""
    judge = RecordingJudge()
    wrapped = on_retrieval_rows(judge)  # type: ignore[arg-type]
    with_context = on_retrieval_rows(judge, fields=("trace", "expectations"))  # type: ignore[arg-type]
    trace = fake_trace()
    kb_row = {"expected_source": "late-payment-fee", "expected_facts": ["x"]}
    no_answer_row = {"guidelines": ["The response must say the articles do not cover this"]}

    assert wrapped(inputs={}, outputs="A", expectations=no_answer_row, trace=trace) is None
    assert wrapped(inputs={}, outputs="A", expectations=kb_row, trace=trace) is not None
    assert with_context(inputs={}, outputs="A", expectations=kb_row, trace=trace) is not None
    assert judge.calls == [{"trace": trace}, {"trace": trace, "expectations": kb_row}]


def test_ragas_gets_the_expected_facts_as_its_only_reference() -> None:
    """MLflow joins every expectation value into the RAGAS reference, so only facts are passed."""
    row = {
        "expected_facts": ["The Late Payment Fee is $5", "It is charged after 10 days."],
        "expected_source": "late-payment-fee",
        "should_escalate": False,
        "expected_tool": "search_kb",
    }
    judge = RecordingJudge()
    wrapped = on_retrieval_rows(  # type: ignore[arg-type]
        judge, fields=("expectations", "trace"), reshape=reference_answer
    )
    trace = fake_trace()

    wrapped(inputs={}, outputs="A", expectations=row, trace=trace)

    reference = {"expected_output": "The Late Payment Fee is $5. It is charged after 10 days."}
    assert reference_answer(row) == reference
    assert judge.calls == [{"expectations": reference, "trace": trace}]
    assert reference_answer({}) == {"expected_output": ""}


# --- runner bookkeeping ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), ("yes", True), ("No", False), ("PASS", True), (0.7, None),
     ("maybe", None), (None, None)],
)  # fmt: skip
def test_as_pass(value: Any, expected: bool | None) -> None:
    assert as_pass(value) is expected


def test_aggregate_counts_only_rows_that_have_a_value() -> None:
    per_row = [
        {"correctness": "yes", "latency_ms": 1000.0, "reading_level_ok": True},
        {"correctness": "no", "latency_ms": 3000.0, "reading_level_ok": True},
        {"correctness": None, "latency_ms": 2000.0},
    ]

    metrics = aggregate(per_row)

    assert metrics["correctness"] == {"kind": "pass_fail", "passed": 1, "scored": 2, "rate": 0.5}
    assert metrics["reading_level_ok"]["scored"] == 2
    assert metrics["latency_ms"] == {
        "kind": "numeric",
        "scored": 3,
        "mean": 2000.0,
        "median": 2000.0,
        "p90": 3000.0,
    }


def test_rate_and_mean_text() -> None:
    metrics = aggregate([{"correctness": "yes", "grade": 4.0}, {"correctness": "no", "grade": 6.0}])

    assert rate_text(metrics, "correctness") == "1/2"
    assert rate_text(metrics, "grade") == "n/a"
    assert rate_text(metrics, "missing") == "n/a"
    assert mean_text(metrics, "grade") == "5.00 (n=2)"
    assert mean_text(metrics, "correctness") == "n/a"


def test_scores_from_trace_skips_errors_and_non_feedback() -> None:
    trace = fake_trace(
        assessments=[
            feedback("correctness", "yes"),
            feedback("context_precision", None, error="429"),
            types.SimpleNamespace(name="expectation", feedback=None),
        ]
    )

    assert scores_from_trace(trace) == {"correctness": "yes", "context_precision": None}


def test_rows_are_matched_by_tag_and_the_fullest_trace_wins() -> None:
    traces = [
        fake_trace(tags={EVAL_ID_TAG: "E001"}, assessments=[feedback("a", True)]),
        fake_trace(tags={EVAL_ID_TAG: "E001"},
                   assessments=[feedback("a", True), feedback("b", "yes")]),
        fake_trace(tags={EVAL_ID_TAG: "E002"}, assessments=[feedback("a", False)]),
        fake_trace(tags={}, assessments=[feedback("a", True)]),
    ]  # fmt: skip

    assert rows_by_eval_id(traces) == {"E001": {"a": True, "b": "yes"}, "E002": {"a": False}}


def test_rows_without_an_answer_are_named() -> None:
    rows = [{"id": "E001"}, {"id": "E002"}, {"id": "E003"}, {"id": "E004"}]
    scored = {
        "E001": {"answer_recorded": True, "correctness": "yes"},
        "E002": {"answer_recorded": False},
        # A trace whose answer check itself errored is not known to hold an answer.
        "E003": {"answer_recorded": None},
        # E004 has no trace at all.
    }

    assert rows_without_answer(rows, scored) == ["E002", "E003", "E004"]
    assert rows_without_answer(rows[:1], scored) == []


def test_summary_row_matches_the_header_columns() -> None:
    report = {
        "run_at": "2026-11-14T12:00:00Z",
        "tag": "baseline",
        "chunk_config": "A",
        "query_type": "ann",
        "rows": 2,
        "rows_reviewed": 0,
        "git_sha": "abcdef1234567890",
        "metrics": aggregate(
            [
                {"expected_source_retrieved": True, "correctness": "yes", "latency_ms": 2000.0},
                {"expected_source_retrieved": False, "correctness": "yes", "latency_ms": 4000.0},
            ]
        ),
    }

    row = summary_row(report, "file.json")

    header_columns = SUMMARY_HEADER.strip().splitlines()[-2].count("|")
    assert row.count("|") == header_columns
    assert "| baseline | A | ann | 2 | 0/2 | 1/2 |" in row
    assert "| 2/2 |" in row
    assert "| 3.0 | `abcdef1` | file.json |" in row
