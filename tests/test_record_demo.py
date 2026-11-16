"""The recorder for the public demo, against a fake application."""

from json import dumps
from typing import Any

import pytest

from eval.record_demo import CALL_IDS, EXTRA_QUESTIONS, demo_questions, question_key, record


def sse(*events: tuple[str, Any]) -> str:
    return "".join(f"event: {name}\ndata: {dumps(data)}\n\n" for name, data in events)


class FakeResponse:
    def __init__(self, body: Any, status_code: int = 200, text: str = "") -> None:
        self._body = body
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        return self._body


class FakeClient:
    """Answers the five endpoints the recorder calls, and notes what was asked."""

    def __init__(
        self,
        fail_on: str | None = None,
        error_on: str | None = None,
        no_wrap_up_for: str | None = None,
    ) -> None:
        self.asked: list[str] = []
        self.posted: list[str] = []
        self.fail_on = fail_on
        self.error_on = error_on
        self.no_wrap_up_for = no_wrap_up_for

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
        if url == "/api/ask/stream":
            self.asked.append(json["question"])
            if json["question"] == self.fail_on:
                return FakeResponse({"detail": "no"}, 502)
            stage = {"stage": "redaction", "label": "Removing personal details", "tool": None}
            answer = {"answer": "A.", "seconds": 1.5, "trace_id": "tr-live-123"}
            if json["question"] == self.error_on:
                return FakeResponse(None, text=sse(("stage", {**stage, "at": 0.0}), ("error", {})))
            return FakeResponse(None, text=sse(("stage", {**stage, "at": 0.0}), ("answer", answer)))
        self.posted.append(url)
        call_id = url.split("/")[3]
        if url.endswith("/wrapup"):
            if call_id == self.no_wrap_up_for:
                return FakeResponse({"detail": "The model's wrap-up could not be read"}, 400)
            return FakeResponse({"transcript_id": call_id, "disposition": "resolved"})
        return FakeResponse({"transcript_id": call_id, "intent": "x"})


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
    # The stages the copilot reported are kept, with the time each one started.
    assert recording["answers"][0]["stages"] == [
        {"stage": "redaction", "label": "Removing personal details", "tool": None, "at": 0.0}
    ]
    # A visitor cannot open a trace or rate a recording.
    assert all(item["response"]["trace_id"] is None for item in recording["answers"])
    assert len(recording["calls"]) == 3
    # The named calls that exist, plus the first call of each ending that is not among them.
    assert list(recording["transcripts"]) == ["T0001", "T0002", "T0003"]
    assert list(recording["summaries"]) == ["T0001", "T0002", "T0003"]
    assert set(CALL_IDS) >= {"T0001", "T0002"}
    # Each recorded call also has the wrap-up the copilot drafted for it.
    assert recording["wrapups"]["T0003"] == {"transcript_id": "T0003", "disposition": "resolved"}
    assert list(recording["wrapups"]) == ["T0001", "T0002", "T0003"]
    # A draft is asked for and nothing else: the recorder never saves a wrap-up.
    assert not [url for url in client.posted if url.endswith("/save")]


def test_a_wrap_up_that_cannot_be_drafted_is_left_out_and_the_recording_goes_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient(no_wrap_up_for="T0002")

    recording = record(client, [])

    assert list(recording["wrapups"]) == ["T0001", "T0003"]
    assert list(recording["summaries"]) == ["T0001", "T0002", "T0003"]
    assert "no wrap-up for T0002 (HTTP 400)" in capsys.readouterr().out


def test_a_trial_run_records_a_few_questions_and_one_call() -> None:
    client = FakeClient()

    recording = record(client, ["What is eSIM?"], limit=2)

    assert len(recording["answers"]) == 2
    assert list(recording["transcripts"]) == ["T0001"]


def test_an_answer_that_ends_in_an_error_stops_the_recording() -> None:
    client = FakeClient(error_on="hello")

    with pytest.raises(RuntimeError, match="ended with error"):
        record(client, [])


def test_a_failed_request_stops_the_recording() -> None:
    client = FakeClient(fail_on="hello")

    with pytest.raises(RuntimeError, match="HTTP 502"):
        record(client, [])
