"""What a failure inside the copilot looks like from the API. No network, no model.

``tests/test_api.py`` puts a fake copilot behind the API. Here the copilot is the
real one, with a fake model, router, index and SQL runner, so that each test
follows a failure from the part that failed to the response and the log.

Each test's name says what happens today. Where that is a defect, the test
states the behaviour that would be right and is marked as an expected failure
with the reason. The fix is not made here.
"""

import json
import logging
import time
from typing import Any

import mlflow
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import api.main as api_module
from api.main import ASK_FAILED, create_app
from copilot.agent import EMPTY_ANSWER, Copilot
from copilot.guardrails import MAX_HISTORY_TURN_CHARS, MAX_HISTORY_TURNS
from copilot.redaction import Redactor
from test_agent import (
    PHONE,
    FakeModel,
    FakeRouter,
    FakeSql,
    call,
    make_copilot,
)
from test_api import events_in

# A word that is in no prompt, article or fixed reply, to look for in logs and replies.
MARKER = "zebracrossing"
QUESTION = f"Customer at {PHONE} asks about the {MARKER} late fee."
TRANSCRIPT_ROW = {
    "transcript_id": "T0002",
    "category": "billing",
    "resolution": "resolved",
    "turns_json": '[{"speaker": "customer", "text": "My bill has a late fee."}]',
}
SERVER_ERROR = (
    "Defect: this endpoint catches ToolError only. Any other error from the warehouse, the "
    "model or MLflow is unhandled and becomes a 500, and the server then logs the full "
    "traceback with the error's message, which the handlers of /api/ask and the wrap-up "
    "endpoints avoid on purpose. A fix would add the same 'except Exception' as those "
    "handlers: log the kind of error with _log_failure and return a fixed 502 message."
)


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


@pytest.fixture(scope="module")
def trace_store(tmp_path_factory: pytest.TempPathFactory) -> str:
    return f"sqlite:///{(tmp_path_factory.mktemp('failure-modes-api') / 'mlflow.db').as_posix()}"


@pytest.fixture(autouse=True)
def _local_tracking(trace_store: str) -> None:
    mlflow.set_tracking_uri(trace_store)
    mlflow.set_experiment("copilot-api-failure-tests")


class FailingModel(FakeModel):
    """A ``FakeModel`` in which a queued exception is raised when its turn comes."""

    def _reply(self, messages: Any, offered: bool) -> Any:
        reply = super()._reply(messages, offered)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def client_for(copilot: Copilot, *, tracing: bool = False) -> TestClient:
    """The API in front of ``copilot``. A 500 is returned as a response, as a server would."""
    app = create_app(copilot, tracing=tracing, static_dir=None)
    return TestClient(app, raise_server_exceptions=False)


def everything_logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        record.getMessage() + (record.exc_text or "") + str(record.exc_info or "")
        for record in caplog.records
    )


def ask(client: TestClient, question: str = QUESTION, path: str = "/api/ask") -> Any:
    return client.post(path, json={"question": question, "history": []})


# --- the model that answers fails -----------------------------------------------------------


@pytest.mark.parametrize(
    "replies",
    [
        (TimeoutError(f"no reply to the question about {MARKER}"),),
        (call("search_kb", query="late fee"), TimeoutError(f"no reply about {MARKER}")),
    ],
    ids=["on the first call", "on a later call"],
)
def test_a_model_timeout_reaches_the_api_as_a_fixed_502_with_nothing_of_the_question_in_the_log(
    redactor: Redactor, caplog: pytest.LogCaptureFixture, replies: tuple[Any, ...]
) -> None:
    client = client_for(make_copilot(redactor, FailingModel(*replies)))

    with caplog.at_level(logging.DEBUG):
        response = ask(client)

    assert response.status_code == 502
    assert response.json() == {"detail": ASK_FAILED}
    assert MARKER not in response.text
    assert PHONE not in response.text
    logged = everything_logged(caplog)
    # The kind of error and the file and line that raised it. Nothing else.
    assert "The copilot failed to answer (TimeoutError at test_failure_modes_api.py:" in logged
    assert MARKER not in logged
    assert PHONE not in logged
    assert "no reply" not in logged
    assert "Traceback" not in logged
    assert all(record.exc_info is None for record in caplog.records)


def test_a_model_timeout_while_streaming_is_one_error_event_after_the_stages_that_ran(
    redactor: Redactor, caplog: pytest.LogCaptureFixture
) -> None:
    model = FailingModel(call("search_kb", query="late fee"), TimeoutError(f"no {MARKER} reply"))
    client = client_for(make_copilot(redactor, model))

    with caplog.at_level(logging.DEBUG):
        response = ask(client, path="/api/ask/stream")

    # The status was sent before the failure, so it is 200. The stream ends: it does not hang.
    assert response.status_code == 200
    events = events_in(response.text)
    assert [(name, data.get("stage")) for name, data in events] == [
        ("stage", "redaction"),
        ("stage", "input_check"),
        ("stage", "model"),
        ("stage", "tool"),
        ("stage", "answer"),
        ("error", None),
    ]
    assert events[-1][1] == {"detail": ASK_FAILED}
    assert MARKER not in response.text
    assert PHONE not in response.text
    assert MARKER not in everything_logged(caplog)


def test_a_tool_call_whose_arguments_are_a_list_reaches_the_api_as_the_same_fixed_502(
    redactor: Redactor, caplog: pytest.LogCaptureFixture
) -> None:
    class ListArguments(FakeModel):
        def _reply(self, messages: Any, offered: bool) -> Any:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "search_kb", "args": [MARKER], "id": "c1", "type": "tool_call"}
                ],
            )

    client = client_for(make_copilot(redactor, ListArguments("unused")))

    with caplog.at_level(logging.DEBUG):
        response = ask(client)

    assert response.status_code == 502
    assert response.json() == {"detail": ASK_FAILED}
    logged = everything_logged(caplog)
    assert "The copilot failed to answer (ValidationError at " in logged
    # The validation error's message quotes the arguments. The log does not.
    assert MARKER not in logged


# --- failures the copilot absorbs: the API answers 200 and says what happened ---------------


def test_a_router_failure_is_a_normal_answer_with_a_step_that_says_the_rules_decided(
    redactor: Redactor,
) -> None:
    model = FakeModel(call("search_kb", query="late fee"), "The late fee is $5 [1].")
    copilot = make_copilot(
        redactor, model, router="model", router_model=FakeRouter(TimeoutError("no reply"))
    )

    response = ask(client_for(copilot), "How much is the late fee?")

    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == "The late fee is $5 [1]."
    assert body["guardrail_flags"] == ["router_unavailable"]
    assert "Checked by the rules only" in [step["title"] for step in body["steps"]]


def test_a_tool_failure_is_a_normal_answer_with_a_warning_on_that_tool_s_step(
    redactor: Redactor, caplog: pytest.LogCaptureFixture
) -> None:
    sql = FakeSql(RuntimeError(f"warehouse stopped during the {MARKER} lookup"))
    model = FakeModel(call("get_plan_details", plan_name="Plus 10"), "I could not look that up.")
    client = client_for(make_copilot(redactor, model, sql=sql))

    with caplog.at_level(logging.DEBUG):
        response = ask(client, "How much is Plus 10?")

    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == "I could not look that up."
    step = next(step for step in body["steps"] if step["tool"] == "get_plan_details")
    assert (step["status"], step["detail"]) == (
        "warning",
        "The lookup failed, and the copilot said so.",
    )
    logged = everything_logged(caplog)
    assert "Tool get_plan_details failed (RuntimeError)" in logged
    assert MARKER not in logged


def test_an_unknown_tool_is_a_normal_answer_with_a_warning_step_named_after_it(
    redactor: Redactor,
) -> None:
    model = FakeModel(call("delete_account", id="1"), "I cannot do that.")

    response = ask(client_for(make_copilot(redactor, model)), "What can you do?")

    body = response.json()
    assert response.status_code == 200
    step = next(step for step in body["steps"] if step["tool"] == "delete_account")
    assert (step["title"], step["status"]) == ("Used delete_account", "warning")


def test_a_search_that_finds_nothing_is_a_normal_answer_with_a_step_that_says_so(
    redactor: Redactor,
) -> None:
    model = FakeModel(
        call("search_kb", query="senior discount"), "The help articles do not cover this."
    )

    response = ask(
        client_for(make_copilot(redactor, model, rows=[])), "Is there a senior discount?"
    )

    body = response.json()
    assert response.status_code == 200
    assert body["citations"] == []
    assert body["guardrail_flags"] == ["no_context"]
    step = next(step for step in body["steps"] if step["tool"] == "search_kb")
    assert (step["status"], step["detail"]) == ("notice", "No article matched.")


def test_a_model_that_never_stops_asking_for_tools_is_a_normal_reply_with_the_fallback_answer(
    redactor: Redactor,
) -> None:
    class AlwaysAsks(FakeModel):
        def _reply(self, messages: Any, offered: bool) -> Any:
            self.calls.append(list(messages))
            return call("search_kb", query="late fee")

    model = AlwaysAsks("unused")

    response = ask(client_for(make_copilot(redactor, model)), "Late fee?")

    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == EMPTY_ANSWER
    assert "tool_limit_reached" in body["guardrail_flags"]
    assert "empty_answer" in body["guardrail_flags"]
    # Four rounds with tools and one turn without.
    assert len(model.calls) == 5


# --- the largest conversation the API accepts -------------------------------------------------


def largest_history() -> list[dict[str, str]]:
    """Forty turns of 8,000 characters, the most the request model allows."""
    turns = []
    for number in range(40):
        role = "user" if number % 2 == 0 else "assistant"
        opening = f"Turn {number}. The customer's number is {PHONE}. "
        turns.append(
            {"role": role, "content": (opening + "The bill was late again. " * 400)[:8000]}
        )
    return turns


def test_the_largest_conversation_the_api_accepts_is_answered_with_only_its_last_turns_sent(
    redactor: Redactor,
) -> None:
    model = FakeModel("It is $5.")
    client = client_for(make_copilot(redactor, model))
    history = largest_history()
    assert all(len(turn["content"]) == 8000 for turn in history)

    started = time.perf_counter()
    response = client.post("/api/ask", json={"question": "q" * 2000, "history": history})
    seconds = time.perf_counter() - started

    assert response.status_code == 200
    assert response.json()["answer"] == "It is $5."
    (messages,) = model.calls
    earlier = messages[1:-1]
    # 320,000 characters arrive. Twelve turns of at most 2,000 are sent to the model.
    assert len(earlier) == MAX_HISTORY_TURNS
    assert earlier[0].content.startswith("Turn 28.")
    assert all(len(message.content) <= MAX_HISTORY_TURN_CHARS for message in earlier)
    assert len(messages[-1].content) == 2000
    # The phone number in every turn was replaced before the model saw any of them.
    assert PHONE not in str(messages)
    assert "<PHONE_NUMBER_1>" in earlier[0].content
    # Redacting it is the slow part, and it is seconds of work, not a hang.
    assert seconds < 60


@pytest.mark.parametrize(
    "body",
    [
        {"question": "Late fee?", "history": [{"role": "user", "content": "x"}] * 41},
        {"question": "Late fee?", "history": [{"role": "user", "content": "x" * 8001}]},
        {"question": "q" * 2001, "history": []},
    ],
    ids=["41 turns", "a turn of 8,001 characters", "a question of 2,001 characters"],
)
def test_one_step_past_the_largest_request_is_refused_before_the_copilot_is_called(
    redactor: Redactor, body: dict[str, Any]
) -> None:
    model = FakeModel("unused")

    response = client_for(make_copilot(redactor, model)).post("/api/ask", json=body)

    assert response.status_code == 422
    assert model.calls == []


# --- the endpoints that call a tool directly --------------------------------------------------


def test_a_hand_off_whose_ticket_cannot_be_written_is_returned_with_a_script_to_transfer_by_hand(
    redactor: Redactor, caplog: pytest.LogCaptureFixture
) -> None:
    sql = FakeSql(RuntimeError(f"warehouse stopped while writing {MARKER}"))
    client = client_for(make_copilot(redactor, FakeModel("unused"), sql=sql))

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/api/handoffs",
            json={"reason": f"Refund the fee. Number {PHONE}.", "category": "billing"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["recorded"] is False
    assert "by hand" in body["agent_script"]
    assert PHONE not in response.text
    logged = everything_logged(caplog)
    assert "A hand-off ticket could not be written (RuntimeError)" in logged
    assert MARKER not in logged


@pytest.mark.xfail(strict=True, reason=SERVER_ERROR)
def test_a_stopped_warehouse_on_the_list_of_calls_is_a_fixed_502(redactor: Redactor) -> None:
    sql = FakeSql(RuntimeError("warehouse is stopped"))
    client = client_for(make_copilot(redactor, FakeModel("unused"), sql=sql))

    response = client.get("/api/calls")

    assert response.status_code == 502


@pytest.mark.xfail(strict=True, reason=SERVER_ERROR)
def test_a_stopped_warehouse_on_one_transcript_is_a_fixed_502(redactor: Redactor) -> None:
    sql = FakeSql(RuntimeError("warehouse is stopped"))
    client = client_for(make_copilot(redactor, FakeModel("unused"), sql=sql))

    response = client.get("/api/calls/T0002")

    assert response.status_code == 502


@pytest.mark.xfail(strict=True, reason=SERVER_ERROR)
def test_a_model_timeout_on_the_call_summary_endpoint_is_a_fixed_502(redactor: Redactor) -> None:
    model = FailingModel(TimeoutError("no reply to the summary"))
    client = client_for(make_copilot(redactor, model, sql=FakeSql([TRANSCRIPT_ROW])))

    response = client.post("/api/calls/T0002/summary")

    assert response.status_code == 502


def test_a_summary_the_model_wrote_badly_is_a_400_with_the_tool_s_own_message(
    redactor: Redactor,
) -> None:
    model = FakeModel("The customer called about a late fee.")
    client = client_for(make_copilot(redactor, model, sql=FakeSql([TRANSCRIPT_ROW])))

    response = client.post("/api/calls/T0002/summary")

    # The model's fault is reported with the status of a bad request from the caller.
    assert response.status_code == 400
    assert response.json() == {"detail": "The model did not return a JSON object"}


def test_a_model_timeout_on_the_wrap_up_endpoint_is_a_fixed_502_logged_by_its_kind(
    redactor: Redactor, caplog: pytest.LogCaptureFixture
) -> None:
    model = FailingModel(TimeoutError(f"no reply about {MARKER}"))
    client = client_for(make_copilot(redactor, model, sql=FakeSql([TRANSCRIPT_ROW])))

    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/calls/T0002/wrapup")

    assert response.status_code == 502
    assert response.json() == {"detail": api_module.WRAP_UP_FAILED}
    logged = everything_logged(caplog)
    assert "The copilot failed to answer (TimeoutError at " in logged
    assert MARKER not in logged


@pytest.mark.xfail(strict=True, reason=SERVER_ERROR)
def test_feedback_that_mlflow_cannot_save_is_a_fixed_502(
    redactor: Redactor, monkeypatch: pytest.MonkeyPatch
) -> None:
    def cannot_save(**_: Any) -> None:
        raise RuntimeError("trace tr-unknown was not found")

    monkeypatch.setattr(api_module.mlflow, "log_feedback", cannot_save)
    client = client_for(make_copilot(redactor, FakeModel("unused")), tracing=True)

    response = client.post("/api/feedback", json={"trace_id": "tr-unknown", "helpful": True})

    assert response.status_code == 502


def test_today_those_unhandled_errors_are_a_bare_500_that_says_nothing_of_the_cause(
    redactor: Redactor,
) -> None:
    """What the four expected failures above look like now, so the response itself is on record."""
    sql = FakeSql(RuntimeError(f"warehouse stopped during {MARKER}"))
    client = client_for(make_copilot(redactor, FakeModel("unused"), sql=sql))

    response = client.get("/api/calls")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert MARKER not in response.text
    assert json.dumps(ASK_FAILED) not in response.text


def test_today_such_an_error_reaches_the_web_server_whole_with_its_message(
    redactor: Redactor,
) -> None:
    """The handler does not catch it, so what is logged about it is up to the web server.

    A web server logs an unhandled error with its traceback and message. This
    test shows only that the error leaves the application with its message.
    """
    sql = FakeSql(RuntimeError(f"warehouse stopped during {MARKER}"))
    app = create_app(
        make_copilot(redactor, FakeModel("unused"), sql=sql), tracing=False, static_dir=None
    )

    with pytest.raises(RuntimeError, match=MARKER):
        TestClient(app, raise_server_exceptions=True).get("/api/calls")
