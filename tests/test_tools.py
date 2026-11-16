"""The four tools, with a fake SQL runner, a fake retriever and a fake model. No network."""

import json
import types
from datetime import UTC, datetime
from typing import Any

import pytest

from copilot.config import Settings
from copilot.prompts import SUMMARY_PROMPT
from copilot.redaction import Redactor
from copilot.retriever import Retriever
from copilot.schemas import KBHit
from copilot.tools import (
    MAX_REASON_CHARS,
    ToolError,
    Tools,
    clean_plan_name,
    new_ticket_id,
    parse_json_object,
    sdk_sql_runner,
)

FIXED_NOW = datetime(2026, 11, 14, 17, 30, 5, tzinfo=UTC)
PLUS_10 = {
    "plan_id": "P04",
    "kind": "plan",
    "name": "Northline Plus 10",
    "monthly_price_usd": "35.00",
    "billing_period": "monthly",
    "data_gb": "10.0",
    "talk_text": "Unlimited talk and text",
    "hotspot_gb": "2.0",
    "international": "Calls to Canada and Mexico",
    "notes": "10 GB of data. 2 GB can be used as a hotspot.",
}
TURNS = [
    {"speaker": "customer", "text": "Hi, this is <PERSON_1>. My phone says no service."},
    {"speaker": "agent", "text": "I've refreshed the SIM on our side."},
    {"speaker": "customer", "text": "It's working now!"},
]
GOOD_SUMMARY = {
    "summary_bullets": ["The phone showed no service.", "The agent refreshed the SIM."],
    "intent": "fix no service",
    "sentiment": "positive",
    "next_step": "None, the issue was resolved.",
}


def hit(slug: str, title: str = "Title") -> KBHit:
    url = f"https://help.northline.example/articles/{slug}"
    return KBHit(chunk_id=f"{slug}#0", url=url, title=title, text="x")


class FakeSql:
    """Returns queued results in order and records every statement and its parameters."""

    def __init__(self, *results: Any) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, statement: str, parameters: Any) -> list[dict[str, Any]]:
        self.calls.append((statement, dict(parameters)))
        result = self.results.pop(0) if self.results else []
        if isinstance(result, Exception):
            raise result
        return list(result)


class FakeRetriever:
    def __init__(self, *results: list[KBHit]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def search(
        self, question: str, *, top_k: int | None = None, section: str | None = None
    ) -> list[KBHit]:
        self.calls.append({"question": question, "top_k": top_k, "section": section})
        return self.results.pop(0) if self.results else []


class FakeLlm:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages: list[tuple[str, str]] = []

    def invoke(self, messages: list[tuple[str, str]]) -> Any:
        self.messages = messages
        return types.SimpleNamespace(content=self.reply)


class FakeRedactor:
    """Replaces one known phone number, which is all these tests need."""

    def redact(self, text: str) -> Any:
        return types.SimpleNamespace(
            text=text.replace("480-555-0132", "<PHONE_NUMBER_1>"), entities=()
        )


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


def make_tools(**parts: Any) -> Tools:
    settings = parts.pop("settings", None) or Settings(_env_file=None)  # type: ignore[call-arg]
    parts.setdefault("redactor", FakeRedactor())
    parts.setdefault("ticket_id", lambda: "ESC-TEST0001")
    parts.setdefault("now", lambda: FIXED_NOW)
    return Tools(settings, **parts)


# --- search_kb ----------------------------------------------------------------------------


def test_search_passes_the_section_and_clamps_top_k() -> None:
    retriever = FakeRetriever([hit("late-payment-fee")])
    tools = make_tools(retriever=retriever)

    hits = tools.search_kb("late fee", section="Billing", top_k=50)

    assert [item.chunk_id for item in hits] == ["late-payment-fee#0"]
    assert retriever.calls == [{"question": "late fee", "top_k": 10, "section": "Billing"}]


def test_search_falls_back_to_all_sections_when_the_section_finds_nothing() -> None:
    retriever = FakeRetriever([], [hit("late-payment-fee")])
    tools = make_tools(retriever=retriever)

    hits = tools.search_kb("late fee", section="Money matters")

    assert len(hits) == 1
    assert [call["section"] for call in retriever.calls] == ["Money matters", None]


def test_retriever_adds_the_section_to_the_index_filter() -> None:
    seen: dict[str, Any] = {}

    def query(**kwargs: Any) -> tuple[list[str], list[list[Any]]]:
        seen.update(kwargs)
        return [], []

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    Retriever(settings, query=query).search("late fee", section="Billing")

    assert seen["filters"] == {"chunk_config": settings.chunk_config, "section": "Billing"}


def test_search_rejects_an_empty_query() -> None:
    with pytest.raises(ToolError, match="empty"):
        make_tools(retriever=FakeRetriever()).search_kb("   ")


# --- get_plan_details -----------------------------------------------------------------------


def test_plan_lookup_binds_every_model_value_as_a_parameter() -> None:
    sql = FakeSql([PLUS_10])
    tools = make_tools(sql=sql)
    hostile = "x'; DROP TABLE plans; --"

    plans = tools.get_plan_details(plan_name=hostile, max_price=40, needs_international=True)

    statement, parameters = sql.calls[0]
    assert hostile not in statement
    assert "DROP" not in statement
    assert "frontline.gold.plans" in statement
    assert parameters == {
        "plan_name": ("STRING", hostile),
        "max_price": ("DOUBLE", "40.0"),
        "needs_international": ("BOOLEAN", "true"),
    }
    assert plans[0].name == "Northline Plus 10"
    assert plans[0].monthly_price_usd == 35.0
    assert plans[0].data_gb == 10.0


def test_plan_lookup_with_no_arguments_sends_nulls() -> None:
    sql = FakeSql([])
    tools = make_tools(sql=sql)

    assert tools.get_plan_details() == []
    assert sql.calls[0][1] == {
        "plan_name": ("STRING", None),
        "max_price": ("DOUBLE", None),
        "needs_international": ("BOOLEAN", None),
    }


def test_plan_lookup_keeps_unlimited_data_as_none_and_rejects_a_negative_price() -> None:
    unlimited = {**PLUS_10, "name": "Northline Unlimited Premium", "data_gb": None}
    tools = make_tools(sql=FakeSql([unlimited]))

    assert tools.get_plan_details(plan_name="Unlimited Premium")[0].data_gb is None
    with pytest.raises(ToolError, match="negative"):
        tools.get_plan_details(max_price=-1)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("the Plus 10 plan", "Plus 10"),
        ("  Northline Plus 10  ", "Northline Plus 10"),
        ("Device Protection", "Device Protection"),
        ("the plan", "plan"),
        ("   ", None),
        (None, None),
    ],
)
def test_clean_plan_name(given: str | None, expected: str | None) -> None:
    assert clean_plan_name(given) == expected


# --- summarize_call -------------------------------------------------------------------------


def transcript_row() -> dict[str, Any]:
    return {
        "transcript_id": "T0002",
        "category": "troubleshooting",
        "resolution": "resolved",
        "turns_json": json.dumps(TURNS),
    }


def test_summary_reads_the_redacted_table_and_returns_structured_fields() -> None:
    sql = FakeSql([transcript_row()])
    llm = FakeLlm("```json\n" + json.dumps(GOOD_SUMMARY) + "\n```")
    retriever = FakeRetriever(
        [hit("no-service", "No service"), hit("no-service", "No service"), hit("sim", "SIM")]
    )
    tools = make_tools(sql=sql, llm=llm, retriever=retriever)

    summary = tools.summarize_call(" t0002 ")

    statement, parameters = sql.calls[0]
    assert "frontline.silver.transcripts_redacted" in statement
    assert "bronze" not in statement
    assert parameters == {"transcript_id": ("STRING", "T0002")}
    assert llm.messages[0] == ("system", SUMMARY_PROMPT)
    assert "<PERSON_1>" in llm.messages[1][1]
    assert 'recorded_outcome="resolved"' in llm.messages[1][1]
    assert summary.transcript_id == "T0002"
    assert summary.sentiment == "positive"
    assert len(summary.summary_bullets) == 2
    # One citation per article, numbered from 1.
    assert [(c.number, c.title) for c in summary.related_articles] == [
        (1, "No service"),
        (2, "SIM"),
    ]


@pytest.mark.parametrize("bad_id", ["T12", "T99", "0007", "T00077", "T0007; DROP TABLE x", ""])
def test_summary_rejects_a_malformed_id_before_any_lookup(bad_id: str) -> None:
    sql = FakeSql()
    tools = make_tools(sql=sql, llm=FakeLlm("{}"), retriever=FakeRetriever())

    with pytest.raises(ToolError, match="not a valid transcript id"):
        tools.summarize_call(bad_id)
    assert sql.calls == []


def test_summary_of_an_unknown_transcript_says_so() -> None:
    tools = make_tools(sql=FakeSql([]), llm=FakeLlm("{}"), retriever=FakeRetriever())

    with pytest.raises(ToolError, match="No transcript was found with the id T9999"):
        tools.summarize_call("T9999")


@pytest.mark.parametrize(
    "reply",
    [
        "I cannot summarize this.",
        '{"summary_bullets": [], "intent": "x", "sentiment": "positive", "next_step": "y"}',
        '{"summary_bullets": ["a"], "intent": "x", "sentiment": "furious", "next_step": "y"}',
        '{"summary_bullets": ["a"], "intent": ',
        "[1, 2]",
    ],
)
def test_summary_fails_cleanly_on_a_bad_model_reply(reply: str) -> None:
    tools = make_tools(sql=FakeSql([transcript_row()]), llm=FakeLlm(reply))

    with pytest.raises(ToolError):
        tools.summarize_call("T0002")


def test_summary_without_an_intent_has_no_related_articles() -> None:
    fields = {**GOOD_SUMMARY, "intent": ""}
    retriever = FakeRetriever()
    tools = make_tools(
        sql=FakeSql([transcript_row()]), llm=FakeLlm(json.dumps(fields)), retriever=retriever
    )

    assert tools.summarize_call("T0002").related_articles == []
    assert retriever.calls == []


def test_parse_json_object_ignores_text_around_the_object() -> None:
    assert parse_json_object('Here you go: {"a": 1} Hope that helps.') == {"a": 1}
    with pytest.raises(ToolError):
        parse_json_object("}{")


def test_summary_text_gets_the_same_output_check_as_an_answer(redactor: Redactor) -> None:
    turns = [
        {"speaker": "agent", "text": "You can also call us on 1-800-555-0199."},
        {"speaker": "customer", "text": "Thanks, my number is <PHONE_NUMBER_1>."},
    ]
    row = {**transcript_row(), "turns_json": json.dumps(turns)}
    written = {
        **GOOD_SUMMARY,
        "summary_bullets": [
            "The agent gave the support line, 1-800-555-0199.",
            "The customer can be reached on 480-555-0132.",
        ],
    }
    tools = make_tools(
        sql=FakeSql([row]),
        llm=FakeLlm(json.dumps(written)),
        retriever=FakeRetriever(),
        redactor=redactor,
    )

    summary = tools.summarize_call("T0002")

    # The support line is in the transcript, so it stays. The other number is not.
    assert "1-800-555-0199" in summary.summary_bullets[0]
    assert "480-555-0132" not in summary.summary_bullets[1]
    assert "<PHONE_NUMBER_1>" in summary.summary_bullets[1]


# --- escalate_to_human ----------------------------------------------------------------------


def test_escalation_writes_a_redacted_parameterized_row() -> None:
    sql = FakeSql([])
    tools = make_tools(sql=sql)

    ticket = tools.escalate_to_human(
        "Customer at 480-555-0132 wants the late fee refunded", "Billing", "high"
    )

    statement, parameters = sql.calls[0]
    assert statement.startswith("INSERT INTO frontline.ops.escalations ")
    assert "480-555-0132" not in statement
    assert "480-555-0132" not in json.dumps(parameters)
    assert parameters["reason"] == (
        "STRING",
        "Customer at <PHONE_NUMBER_1> wants the late fee refunded",
    )
    assert parameters["created_at"] == ("TIMESTAMP", "2026-11-14 17:30:05")
    assert parameters["category"] == ("STRING", "billing")
    assert ticket.ticket_id == "ESC-TEST0001"
    assert ticket.recorded is True
    assert ticket.urgency == "high"
    assert "480-555-0132" not in ticket.reason
    assert "the billing team" in ticket.agent_script
    assert "ESC-TEST0001" in ticket.agent_script


def test_escalation_still_returns_a_ticket_when_the_write_fails() -> None:
    tools = make_tools(sql=FakeSql(RuntimeError("warehouse is stopped")))

    ticket = tools.escalate_to_human("Change the plan", "plan change")

    assert ticket.recorded is False
    assert ticket.category == "plan_change"
    assert "by hand" in ticket.agent_script
    assert "ESC-TEST0001" in ticket.agent_script


def test_a_draft_is_what_a_ticket_would_hold_and_writes_nothing() -> None:
    sql = FakeSql([])
    tools = make_tools(sql=sql)

    draft = tools.draft_hand_off("Customer at 480-555-0132 wants a refund", "Billing ", "high")

    assert sql.calls == []
    assert draft.model_dump() == {
        "category": "billing",
        "urgency": "high",
        "reason": "Customer at <PHONE_NUMBER_1> wants a refund",
        "team": "the billing team",
    }
    assert tools.draft_hand_off("x", "made up").category == "other"
    with pytest.raises(ToolError, match="urgency"):
        tools.draft_hand_off("x", "billing", "soon")  # type: ignore[arg-type]


def test_a_dry_run_hand_off_writes_nothing_and_reads_like_a_real_one() -> None:
    sql = FakeSql([])
    settings = Settings(_env_file=None, record_escalations=False)  # type: ignore[call-arg]
    tools = make_tools(sql=sql, settings=settings)

    ticket = tools.escalate_to_human("Refund the late fee", "billing")

    assert sql.calls == []
    assert ticket.recorded is False
    assert "passing you to the billing team" in ticket.agent_script
    assert "ESC-TEST0001" in ticket.agent_script


def test_a_failed_write_is_logged_by_kind_only(caplog: pytest.LogCaptureFixture) -> None:
    tools = make_tools(sql=FakeSql(RuntimeError("INSERT ... reason = 'secret text'")))

    with caplog.at_level("WARNING"):
        tools.escalate_to_human("Change the plan", "plan change")

    assert "RuntimeError" in caplog.text
    assert "secret text" not in caplog.text


def test_escalation_normalises_the_category_and_checks_urgency() -> None:
    tools = make_tools(sql=FakeSql([], []))

    assert tools.escalate_to_human("x", "something new").category == "other"
    assert tools.escalate_to_human("x", "Account-Access").category == "account_access"
    with pytest.raises(ToolError, match="urgency"):
        tools.escalate_to_human("x", "billing", "urgent")  # type: ignore[arg-type]


def test_escalation_reason_is_cut_to_a_fixed_length() -> None:
    sql = FakeSql([])
    tools = make_tools(sql=sql)

    ticket = tools.escalate_to_human("y" * (MAX_REASON_CHARS + 200))

    assert len(ticket.reason) == MAX_REASON_CHARS


def test_ticket_ids_are_short_and_differ() -> None:
    first, second = new_ticket_id(), new_ticket_id()

    assert first != second
    assert first.startswith("ESC-")
    assert len(first) == 12


# --- dependencies built on first use ----------------------------------------------------------


def test_missing_dependencies_are_built_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []
    monkeypatch.setattr("copilot.tools.Retriever", lambda settings: built.append("retriever"))
    monkeypatch.setattr("copilot.tools.sdk_sql_runner", lambda settings: built.append("sql"))
    monkeypatch.setattr("copilot.tools.build_chat_model", lambda settings: built.append("llm"))
    monkeypatch.setattr(
        "copilot.tools.get_redactor", lambda product_names: built.append("redactor") or "r"
    )
    tools = Tools(Settings(_env_file=None))  # type: ignore[call-arg]

    _ = (tools.retriever, tools.sql, tools.llm, tools.redactor, tools.redactor)

    assert built[:3] == ["retriever", "sql", "llm"]
    assert built.count("redactor") == 1


# --- the SDK-backed SQL runner ------------------------------------------------------------------


def statement_response(state: str, rows: list[list[Any]] | None = None) -> Any:
    columns = [types.SimpleNamespace(name="plan_id"), types.SimpleNamespace(name="name")]
    return types.SimpleNamespace(
        statement_id="stmt-1",
        status=types.SimpleNamespace(state=types.SimpleNamespace(value=state)),
        manifest=types.SimpleNamespace(schema=types.SimpleNamespace(columns=columns)),
        result=types.SimpleNamespace(data_array=rows),
    )


def fake_workspace(monkeypatch: pytest.MonkeyPatch, first: Any, later: list[Any]) -> list[Any]:
    calls: list[Any] = []

    def execute_statement(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return first

    def get_statement(statement_id: str) -> Any:
        calls.append(statement_id)
        return later.pop(0)

    api = types.SimpleNamespace(execute_statement=execute_statement, get_statement=get_statement)
    monkeypatch.setattr(
        "databricks.sdk.WorkspaceClient", lambda: types.SimpleNamespace(statement_execution=api)
    )
    return calls


def test_sdk_runner_sends_typed_parameters_and_returns_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_workspace(monkeypatch, statement_response("SUCCEEDED", [["P04", "Plus 10"]]), [])
    settings = Settings(_env_file=None, sql_warehouse_id="wh-1")  # type: ignore[call-arg]

    rows = sdk_sql_runner(settings)("SELECT 1", {"plan_name": ("STRING", None)})

    assert rows == [{"plan_id": "P04", "name": "Plus 10"}]
    sent = calls[0]
    assert sent["warehouse_id"] == "wh-1"
    assert sent["statement"] == "SELECT 1"
    assert [(p.name, p.type, p.value) for p in sent["parameters"]] == [
        ("plan_name", "STRING", None)
    ]


def test_sdk_runner_waits_for_a_starting_warehouse(monkeypatch: pytest.MonkeyPatch) -> None:
    later = [statement_response("RUNNING"), statement_response("SUCCEEDED", None)]
    calls = fake_workspace(monkeypatch, statement_response("PENDING"), later)
    settings = Settings(_env_file=None, sql_warehouse_id="wh-1")  # type: ignore[call-arg]
    naps: list[float] = []

    rows = sdk_sql_runner(settings, sleep=naps.append)("INSERT ...", {})

    assert rows == []
    assert calls[1:] == ["stmt-1", "stmt-1"]
    assert naps == [2.0, 2.0]


def test_sdk_runner_reports_a_failed_statement(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_workspace(monkeypatch, statement_response("FAILED"), [])
    settings = Settings(_env_file=None, sql_warehouse_id="wh-1")  # type: ignore[call-arg]

    with pytest.raises(ToolError, match="did not finish"):
        sdk_sql_runner(settings)("SELECT 1", {})


def test_sdk_runner_needs_a_warehouse() -> None:
    settings = Settings(_env_file=None, sql_warehouse_id=None)  # type: ignore[call-arg]

    with pytest.raises(ToolError, match="SQL_WAREHOUSE_ID"):
        sdk_sql_runner(settings)
