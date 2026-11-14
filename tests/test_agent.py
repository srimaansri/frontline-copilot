"""The copilot end to end, with a fake index and a fake model.

Tracing is real: traces are written to a local SQLite store, so the test that
personal data never reaches a trace inspects what MLflow actually recorded.
"""

import types
from pathlib import Path
from typing import Any

import mlflow
import pytest

import copilot.agent as agent_module
from copilot.agent import FLAG_NO_CONTEXT, Copilot, get_copilot, run_copilot
from copilot.config import Settings
from copilot.guardrails import FLAG_INVALID_CITATION, FLAG_NO_CITATION
from copilot.prompts import NO_CONTEXT_ANSWER, PROMPT_VERSION, SYSTEM_PROMPT
from copilot.redaction import Redactor
from copilot.retriever import Retriever

NAMES = ["chunk_id", "url", "title", "section", "heading", "text", "score"]
ROWS = [
    ["c1", "https://help.northline.example/articles/late-payment-fee", "Late payment fee",
     "Billing", "What the fee is", "A Late Payment Fee of $5 is charged.", 0.8],
    ["c2", "https://help.northline.example/articles/set-up-autopay", "Set up AutoPay",
     "Billing", "", "AutoPay is free.", 0.5],
]  # fmt: skip
PHONE = "480-555-0132"


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


@pytest.fixture(autouse=True)
def _local_tracking(tmp_path: Path) -> None:
    mlflow.set_tracking_uri(f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    mlflow.set_experiment("copilot-tests")


class FakeModel:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[tuple[str, str]]] = []

    def invoke(self, messages: list[tuple[str, str]]) -> Any:
        self.calls.append(messages)
        return types.SimpleNamespace(content=self.reply)


def _copilot(redactor: Redactor, model: FakeModel, rows: list[list[Any]] = ROWS) -> Copilot:
    settings = Settings(_env_file=None, chunk_config="B", query_type="hybrid")  # type: ignore[call-arg]

    def query(**_: Any) -> tuple[list[str], list[list[Any]]]:
        return NAMES, rows

    return Copilot(
        settings, retriever=Retriever(settings, query), chat_model=model, redactor=redactor
    )


def _last_trace() -> Any:
    mlflow.flush_trace_async_logging()
    trace_id = mlflow.get_last_active_trace_id()
    assert trace_id is not None
    return mlflow.get_trace(trace_id)


# --- answers ------------------------------------------------------------------------------


def test_answer_carries_citations_for_the_sources_it_used(redactor: Redactor) -> None:
    model = FakeModel("The late fee is $5 [1]. AutoPay is free [2].")

    answer = _copilot(redactor, model).run("How much is the late fee?")

    assert answer.answer == "The late fee is $5 [1]. AutoPay is free [2]."
    assert [(c.number, c.title) for c in answer.citations] == [
        (1, "Late payment fee"),
        (2, "Set up AutoPay"),
    ]
    assert answer.citations[0].url.endswith("/late-payment-fee")
    assert answer.tools_used == ["search_kb"]
    assert answer.escalated is False
    assert answer.guardrail_flags == []


def test_model_sees_the_system_prompt_and_numbered_sources(redactor: Redactor) -> None:
    model = FakeModel("It is $5 [1].")

    _copilot(redactor, model).run("How much is the late fee?")

    (messages,) = model.calls
    assert messages[0] == ("system", SYSTEM_PROMPT)
    assert messages[-1][0] == "user"
    assert '<source number="1" title="Late payment fee">' in messages[-1][1]
    assert messages[-1][1].endswith("Agent's question: How much is the late fee?")


def test_invalid_citation_is_removed_and_flagged(redactor: Redactor) -> None:
    answer = _copilot(redactor, FakeModel("It is $5 [1]. Also see [9].")).run("Late fee?")

    assert answer.answer == "It is $5 [1]. Also see."
    assert [c.number for c in answer.citations] == [1]
    assert answer.guardrail_flags == [FLAG_INVALID_CITATION]


def test_uncited_answer_is_flagged(redactor: Redactor) -> None:
    answer = _copilot(redactor, FakeModel("It is five dollars.")).run("Late fee?")

    assert answer.citations == []
    assert answer.guardrail_flags == [FLAG_NO_CITATION]


def test_no_retrieved_context_means_no_model_call(redactor: Redactor) -> None:
    model = FakeModel("should not be used")

    answer = _copilot(redactor, model, rows=[]).run("What is the airspeed of a swallow?")

    assert answer.answer == NO_CONTEXT_ANSWER
    assert answer.guardrail_flags == [FLAG_NO_CONTEXT]
    assert model.calls == []


def test_history_is_passed_to_the_model_in_order(redactor: Redactor) -> None:
    model = FakeModel("Yes [1].")
    history = [
        {"role": "user", "content": "How much is the late fee?"},
        {"role": "assistant", "content": "It is $5 [1]."},
    ]

    _copilot(redactor, model).run("Can it be waived?", history)

    (messages,) = model.calls
    assert [role for role, _ in messages] == ["system", "user", "assistant", "user"]
    assert messages[1][1] == "How much is the late fee?"


# --- personal data never reaches the model or the trace ------------------------------------------


def test_personal_data_in_the_question_never_reaches_the_model(redactor: Redactor) -> None:
    model = FakeModel("It is $5 [1].")

    answer = _copilot(redactor, model).run(f"Customer at {PHONE} asks about the late fee.")

    assert PHONE not in model.calls[0][-1][1]
    assert "<PHONE_NUMBER_1>" in model.calls[0][-1][1]
    assert answer.guardrail_flags == ["pii_in_question:PHONE_NUMBER"]


def test_personal_data_in_history_never_reaches_the_model(redactor: Redactor) -> None:
    model = FakeModel("It is $5 [1].")

    _copilot(redactor, model).run(
        "And the late fee?", [{"role": "user", "content": f"My number is {PHONE}."}]
    )

    assert PHONE not in str(model.calls[0])


def test_personal_data_never_reaches_the_trace(redactor: Redactor) -> None:
    question = f"Customer Linda at {PHONE}, linda@example.com, asks about the late fee."

    _copilot(redactor, FakeModel("It is $5 [1].")).run(
        question, [{"role": "user", "content": f"Call me on {PHONE}."}]
    )

    recorded = _last_trace().to_json()
    assert PHONE not in recorded
    assert "linda@example.com" not in recorded
    assert "<PHONE_NUMBER_1>" in recorded


def test_trace_has_a_retriever_span_and_version_tags(redactor: Redactor) -> None:
    _copilot(redactor, FakeModel("It is $5 [1].")).run("How much is the late fee?")

    trace = _last_trace()
    spans = {span.name: span for span in trace.data.spans}
    assert set(spans) == {"run_copilot", "search_kb", "generate_answer"}
    assert spans["search_kb"].span_type == "RETRIEVER"
    assert spans["search_kb"].outputs[0]["metadata"]["doc_uri"].endswith("/late-payment-fee")
    assert spans["run_copilot"].inputs == {
        "question": "How much is the late fee?",
        "history_turns": 0,
    }
    assert spans["run_copilot"].outputs["answer"] == "It is $5 [1]."
    assert trace.info.tags["prompt_version"] == PROMPT_VERSION
    assert trace.info.tags["chunk_config"] == "B"
    assert trace.info.tags["query_type"] == "hybrid"


# --- module-level entry point ----------------------------------------------------------------


def test_run_copilot_uses_the_shared_copilot(
    monkeypatch: pytest.MonkeyPatch, redactor: Redactor
) -> None:
    shared = _copilot(redactor, FakeModel("It is $5 [1]."))
    monkeypatch.setattr(agent_module, "get_copilot", lambda: shared)

    assert run_copilot("Late fee?").answer == "It is $5 [1]."


def test_parts_are_built_on_first_use(monkeypatch: pytest.MonkeyPatch, redactor: Redactor) -> None:
    model = FakeModel("It is $5 [1].")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    def query(**_: Any) -> tuple[list[str], list[list[Any]]]:
        return NAMES, ROWS

    monkeypatch.setattr(agent_module, "get_redactor", lambda: redactor)
    monkeypatch.setattr(agent_module, "build_chat_model", lambda _settings: model)

    answer = Copilot(settings, retriever=Retriever(settings, query)).run("Late fee?")

    assert answer.answer == "It is $5 [1]."
    assert len(model.calls) == 1


def test_get_copilot_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    get_copilot.cache_clear()
    monkeypatch.setattr(agent_module, "get_settings", lambda: Settings(_env_file=None))  # type: ignore[call-arg]

    assert get_copilot() is get_copilot()

    get_copilot.cache_clear()
