"""The evaluation set, the scorers' logic and the runner's bookkeeping. No model calls."""

import types
from collections import Counter
from typing import Any

import pytest

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
    scores_from_trace,
    summary_row,
    to_records,
)
from eval.scorers import (
    DETERMINISTIC_SCORERS,
    citation_valid,
    expected_source,
    latency_ms,
    llm_judges,
    plain_text_for_reading_level,
    reading_grade,
    reading_level,
    retrieved_uris,
    root_output,
    source_rank,
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
    slugs = {topic.slug for topic in TOPICS}

    for row in load_eval_set(category="kb"):
        expectations = row["expectations"]
        assert expectations["expected_source"] in slugs, row["id"]
        assert len(expectations["expected_facts"]) >= 2, row["id"]
        assert expectations["should_escalate"] is False


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
    cited = {"citations": [{"url": f"{BASE}/a"}], "guardrail_flags": []}
    removed = {"citations": [{"url": f"{BASE}/a"}], "guardrail_flags": ["invalid_citation_removed"]}
    uncited = {"citations": [], "guardrail_flags": ["no_citation"]}

    assert citation_valid(trace=fake_trace(answer=cited)).value is True
    assert citation_valid(trace=fake_trace(answer=removed)).value is False
    assert citation_valid(trace=fake_trace(answer=uncited)).value is False


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


def test_latency_scorer_reads_the_trace_duration() -> None:
    assert latency_ms(trace=fake_trace(duration=2345)).value == 2345.0


def test_judges_use_the_judge_endpoint_and_leave_out_ragas_faithfulness() -> None:
    judges = llm_judges("my-judge")
    names = {judge.name for judge in judges}

    assert len(DETERMINISTIC_SCORERS) == 4
    assert {"retrieval_groundedness", "correctness", "relevance_to_query", "safety"} <= names
    assert any("ContextPrecision" in type(judge).__name__ for judge in judges)
    assert not any("Faithfulness" in type(judge).__name__ for judge in judges)
    assert all(getattr(judge, "model", "databricks:/my-judge") == "databricks:/my-judge"
               for judge in judges)  # fmt: skip
    assert len(llm_judges("my-judge", include_ragas=False)) == len(judges) - 1


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
