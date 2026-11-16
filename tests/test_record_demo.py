"""The recorder for the public demo, against a fake application."""

from typing import Any

import pytest

from eval.record_demo import CALL_IDS, EXTRA_QUESTIONS, demo_questions, question_key, record


class FakeResponse:
    def __init__(self, body: Any, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def json(self) -> Any:
        return self._body


class FakeClient:
    """Answers the five endpoints the recorder calls, and notes what was asked."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.asked: list[str] = []
        self.fail_on = fail_on

    def get(self, url: str) -> FakeResponse:
        if url == "/api/meta":
            return FakeResponse({"examples": [{"question": "How much is the late fee?"}]})
        if url == "/api/calls":
            return FakeResponse(
                [
                    {"transcript_id": "T0001", "resolution": "resolved"},
                    {"transcript_id": "T0002", "resolution": "resolved"},
                    {"transcript_id": "T0003", "resolution": "escalated"},
                ]
            )
        return FakeResponse({"transcript_id": url.rsplit("/", 1)[1], "turns": []})

    def post(self, url: str, *, json: Any = None) -> FakeResponse:
        if url == "/api/ask":
            self.asked.append(json["question"])
            if json["question"] == self.fail_on:
                return FakeResponse({"detail": "no"}, 502)
            return FakeResponse({"answer": "A.", "seconds": 1.5, "trace_id": "tr-live-123"})
        return FakeResponse({"transcript_id": url.split("/")[3], "intent": "x"})


def test_questions_are_compared_by_letters_and_digits_only() -> None:
    assert question_key("Hello!") == question_key("  hello ") == "hello"
    assert question_key("Which plans cost $25?") == "whichplanscost25"
    assert question_key("?!") == ""


def test_each_question_is_recorded_once_with_the_examples_first() -> None:
    questions = demo_questions(
        ["How much is the late fee?"], ["hello", "how much is the late fee", "What is eSIM?"]
    )

    assert questions[0] == "How much is the late fee?"
    assert questions[-1] == "What is eSIM?"
    assert len(questions) == 1 + len(EXTRA_QUESTIONS) + 1
    assert len({question_key(question) for question in questions}) == len(questions)


def test_a_recording_holds_what_the_application_returned() -> None:
    client = FakeClient()

    recording = record(client, ["What is eSIM?"])

    assert client.asked[0] == "How much is the late fee?"
    assert [item["question"] for item in recording["answers"]] == client.asked
    assert recording["answers"][0]["response"]["answer"] == "A."
    # A visitor cannot open a trace or rate a recording.
    assert all(item["response"]["trace_id"] is None for item in recording["answers"])
    assert len(recording["calls"]) == 3
    # The named calls that exist, plus the first call of each ending that is not among them.
    assert list(recording["transcripts"]) == ["T0001", "T0002", "T0003"]
    assert list(recording["summaries"]) == ["T0001", "T0002", "T0003"]
    assert set(CALL_IDS) >= {"T0001", "T0002"}


def test_a_trial_run_records_a_few_questions_and_one_call() -> None:
    client = FakeClient()

    recording = record(client, ["What is eSIM?"], limit=2)

    assert len(recording["answers"]) == 2
    assert list(recording["transcripts"]) == ["T0001"]


def test_a_failed_request_stops_the_recording() -> None:
    client = FakeClient(fail_on="hello")

    with pytest.raises(RuntimeError, match="HTTP 502"):
        record(client, [])
