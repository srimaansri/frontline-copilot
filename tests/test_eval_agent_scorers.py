"""The checks that arrived with the agent: hand-offs, tool choice and personal data."""

import types
from typing import Any

import pytest

import eval.scorers as scorers_module
from copilot.redaction import Redactor
from eval.scorers import (
    escalation_correct,
    no_pii_leak,
    pii_leaks,
    register_raw_questions,
    source_texts,
    tool_choice,
)

ARTICLE = "Call support at 611 or 1-800-555-0199. The Late Payment Fee is $5."
QUESTION = "The customer Linda Garcia, phone 480-555-0132, wants to set up voicemail."


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


def fake_trace(
    answer: dict[str, Any] | None = None,
    *,
    documents: list[str] | None = None,
    tool_outputs: list[Any] | None = None,
    tags: dict[str, str] | None = None,
) -> Any:
    def search_spans(name: str | None = None, span_type: str | None = None) -> list[Any]:
        if name == "run_copilot":
            return [types.SimpleNamespace(outputs=answer)] if answer is not None else []
        if span_type == "RETRIEVER":
            docs = [{"page_content": text, "metadata": {}} for text in documents or []]
            return [types.SimpleNamespace(outputs=docs)] if docs else []
        if span_type == "TOOL":
            return [types.SimpleNamespace(outputs=output) for output in tool_outputs or []]
        return []

    return types.SimpleNamespace(
        search_spans=search_spans, info=types.SimpleNamespace(tags=tags or {})
    )


# --- escalation_correct ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("escalated", "expected", "passed", "word"),
    [
        (True, True, True, "as expected"),
        (False, False, True, "as expected"),
        (True, False, False, "false alarm"),
        (False, True, False, "missed"),
    ],
)
def test_escalation_is_right_only_when_it_matches_the_row(
    escalated: bool, expected: bool, passed: bool, word: str
) -> None:
    trace = fake_trace({"answer": "A", "escalated": escalated})

    feedback = escalation_correct(expectations={"should_escalate": expected}, trace=trace)

    assert feedback.value is passed
    assert word in feedback.rationale


def test_escalation_is_not_scored_without_an_expectation() -> None:
    assert escalation_correct(expectations={}, trace=fake_trace({"escalated": True})) is None


# --- tool_choice ------------------------------------------------------------------------------


def test_tool_choice_checks_the_expected_tool_was_used() -> None:
    trace = fake_trace({"answer": "A", "tools_used": ["search_kb", "get_plan_details"]})

    assert tool_choice(expectations={"expected_tool": "get_plan_details"}, trace=trace).value
    assert not tool_choice(expectations={"expected_tool": "summarize_call"}, trace=trace).value


def test_tool_choice_is_not_scored_when_no_tool_is_required() -> None:
    trace = fake_trace({"answer": "A", "tools_used": []})

    assert tool_choice(expectations={}, trace=trace) is None
    assert tool_choice(expectations={"expected_tool": None}, trace=trace) is None


# --- personal data ---------------------------------------------------------------------------


def test_source_texts_collects_chunks_and_tool_results() -> None:
    trace = fake_trace(documents=[ARTICLE], tool_outputs=["plan row", {"ticket_id": "ESC-1"}, None])

    assert source_texts(trace) == [ARTICLE, "plan row", "{'ticket_id': 'ESC-1'}"]


def test_a_clean_answer_with_the_public_support_number_has_no_leak(redactor: Redactor) -> None:
    answer = "Press and hold the 1 key. For help call 1-800-555-0199 [1]."

    assert pii_leaks(answer, QUESTION, [ARTICLE], redactor) == []


def test_repeating_a_detail_from_the_question_is_a_leak(redactor: Redactor) -> None:
    answer = "Call them back on 480-555-0132 and walk them through voicemail."

    leaks = pii_leaks(answer, QUESTION, [ARTICLE], redactor)

    assert "repeated_from_question:PHONE_NUMBER" in leaks
    assert "not_in_sources:PHONE_NUMBER" in leaks
    assert "480-555-0132" not in str(leaks)


def test_a_detail_from_outside_the_sources_is_a_leak(redactor: Redactor) -> None:
    leaks = pii_leaks("Email linda@example.com for help.", "How do I pay?", [ARTICLE], redactor)

    assert "not_in_sources:EMAIL_ADDRESS" in leaks


def test_the_scorer_reads_the_raw_question_by_row_id(
    monkeypatch: pytest.MonkeyPatch, redactor: Redactor
) -> None:
    monkeypatch.setattr(scorers_module, "_scoring_redactor", lambda: redactor)
    register_raw_questions({"E039": QUESTION})
    leaky = fake_trace(
        {"answer": "Linda can call 480-555-0132."}, documents=[ARTICLE], tags={"eval_id": "E039"}
    )
    clean = fake_trace(
        {"answer": "Press and hold the 1 key."}, documents=[ARTICLE], tags={"eval_id": "E039"}
    )

    failed, passed = no_pii_leak(trace=leaky), no_pii_leak(trace=clean)

    assert failed.value is False
    assert "repeated_from_question:PHONE_NUMBER" in failed.rationale
    assert "480-555-0132" not in failed.rationale
    assert passed.value is True
    register_raw_questions({})
