"""Retriever and chat-model helpers, with fakes in place of Databricks."""

import json
import sys
import types
from typing import Any

import pytest

from copilot.config import Settings
from copilot.llm import build_chat_model, message_text
from copilot.prompts import build_user_message, format_context
from copilot.retriever import RETURN_COLUMNS, Retriever, hit_to_document, sdk_index_query
from copilot.schemas import KBHit

NAMES = ["chunk_id", "url", "title", "section", "heading", "text", "score"]
ROWS = [
    ["c1", "https://help.northline.example/articles/late-payment-fee", "Late payment fee",
     "Billing", "What the fee is", "Late payment fee - What the fee is\nThe fee is $5.", 0.81],
    ["c2", "https://help.northline.example/articles/set-up-autopay", "Set up AutoPay",
     "Billing", "", "Set up AutoPay\nAutoPay is free.", 0.42],
]  # fmt: skip


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


class FakeQuery:
    def __init__(self, rows: list[list[Any]] = ROWS) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> tuple[list[str], list[list[Any]]]:
        self.calls.append(kwargs)
        return NAMES, self.rows


# --- retriever ----------------------------------------------------------------------------


def test_search_passes_the_configured_index_filter_and_query_type() -> None:
    query = FakeQuery()
    settings = _settings(catalog="demo", chunk_config="B", query_type="hybrid", top_k=4)

    Retriever(settings, query).search("How much is the late fee?")

    assert query.calls == [
        {
            "index_name": "demo.gold.kb_chunks_index",
            "query_text": "How much is the late fee?",
            "columns": RETURN_COLUMNS,
            "num_results": 4,
            "filters": {"chunk_config": "B"},
            "query_type": "hybrid",
        }
    ]


def test_rows_become_hits_best_first() -> None:
    hits = Retriever(_settings(), FakeQuery()).search("q")

    assert [hit.chunk_id for hit in hits] == ["c1", "c2"]
    assert hits[0].title == "Late payment fee"
    assert hits[0].score == pytest.approx(0.81)
    assert hits[0].heading == "What the fee is"
    assert hits[1].heading is None  # an empty heading is "no heading"


def test_top_k_can_be_overridden_per_call() -> None:
    query = FakeQuery()

    Retriever(_settings(top_k=5), query).search("q", top_k=2)

    assert query.calls[0]["num_results"] == 2


def test_hits_below_the_minimum_score_are_dropped() -> None:
    hits = Retriever(_settings(min_retrieval_score=0.5), FakeQuery()).search("q")

    assert [hit.chunk_id for hit in hits] == ["c1"]


def test_no_rows_gives_no_hits() -> None:
    assert Retriever(_settings(), FakeQuery(rows=[])).search("q") == []


def test_hit_converts_to_the_document_shape_mlflow_judges_read() -> None:
    document = hit_to_document(Retriever(_settings(), FakeQuery()).search("q")[0])

    assert document.page_content.endswith("The fee is $5.")
    assert document.metadata["doc_uri"].endswith("/late-payment-fee")
    assert document.metadata["chunk_id"] == "c1"
    assert document.id == "c1"


def test_sdk_query_translates_arguments_and_reads_the_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeIndexes:
        def query_index(self, **kwargs: Any) -> Any:
            seen.update(kwargs)
            return types.SimpleNamespace(
                manifest=types.SimpleNamespace(
                    columns=[types.SimpleNamespace(name=name) for name in NAMES]
                ),
                result=types.SimpleNamespace(data_array=ROWS),
            )

    fake_sdk = types.ModuleType("databricks.sdk")
    fake_sdk.WorkspaceClient = lambda: types.SimpleNamespace(  # type: ignore[attr-defined]
        vector_search_indexes=FakeIndexes()
    )
    monkeypatch.setitem(sys.modules, "databricks.sdk", fake_sdk)

    names, rows = sdk_index_query()(
        index_name="demo.gold.kb_chunks_index",
        query_text="q",
        columns=RETURN_COLUMNS,
        num_results=3,
        filters={"chunk_config": "A"},
        query_type="hybrid",
    )

    assert names == NAMES
    assert rows == ROWS
    assert seen["query_type"] == "HYBRID"
    assert json.loads(seen["filters_json"]) == {"chunk_config": "A"}
    assert seen["columns"] == list(RETURN_COLUMNS)
    assert seen["num_results"] == 3


def test_retriever_builds_the_sdk_query_when_none_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = FakeQuery()
    monkeypatch.setattr("copilot.retriever.sdk_index_query", lambda: query)

    hits = Retriever(_settings()).search("q")

    assert len(hits) == 2
    assert len(query.calls) == 1


# --- prompts -----------------------------------------------------------------------------


def test_context_numbers_the_sources_from_one() -> None:
    hits = [
        KBHit(chunk_id="a", url="u1", title="First", text="Alpha."),
        KBHit(chunk_id="b", url="u2", title="Second", text="Beta."),
    ]

    context = format_context(hits)

    assert context.startswith("<context>\n")
    assert context.endswith("\n</context>")
    assert '<source number="1" title="First">\nAlpha.\n</source>' in context
    assert '<source number="2" title="Second">\nBeta.\n</source>' in context


def test_user_message_puts_the_question_after_the_sources() -> None:
    message = build_user_message("How?", [KBHit(chunk_id="a", url="u", title="T", text="X.")])

    assert message.index("</context>") < message.index("Agent's question: How?")


# --- chat model ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("  Plain answer.  ", "Plain answer."),
        ([{"type": "reasoning", "summary": "thinking"}, {"type": "text", "text": "Answer."}],
         "Answer."),
        (["Part one. ", {"type": "text", "text": "Part two."}], "Part one. Part two."),
        ([], ""),
        (None, ""),
    ],
)  # fmt: skip
def test_message_text_keeps_the_answer_and_drops_reasoning(content: Any, expected: str) -> None:
    assert message_text(types.SimpleNamespace(content=content)) == expected


def test_message_text_accepts_a_bare_string() -> None:
    assert message_text("Just text") == "Just text"


def test_chat_model_is_built_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    class FakeChatDatabricks:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)

    fake_module = types.ModuleType("databricks_langchain")
    fake_module.ChatDatabricks = FakeChatDatabricks  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "databricks_langchain", fake_module)

    model = build_chat_model(_settings(llm_endpoint="my-endpoint", llm_max_tokens=321))

    assert isinstance(model, FakeChatDatabricks)
    assert created == {
        "endpoint": "my-endpoint",
        "temperature": 0.1,
        "max_tokens": 321,
        # A stalled endpoint must not hold a request open for ever.
        "timeout": 60.0,
        "max_retries": 2,
    }
