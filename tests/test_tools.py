"""The four tools, with a fake SQL runner, a fake retriever and a fake model. No network."""

import json
import re
import types
from datetime import UTC, datetime
from typing import Any, get_args

import pytest

from copilot.config import Settings
from copilot.prompts import (
    PROMPT_VERSION,
    SUMMARY_PROMPT,
    WRAP_UP_PROMPT,
    WRAP_UP_PROMPT_VERSION,
)
from copilot.redaction import Redactor
from copilot.retriever import Retriever
from copilot.schemas import (
    CallCategory,
    CallWrapUp,
    Disposition,
    FollowUp,
    FollowUpOwner,
    KBHit,
)
from copilot.tools import (
    MAX_REASON_CHARS,
    MAX_WRAP_UP_CHARS,
    ToolError,
    Tools,
    clean_plan_name,
    new_ticket_id,
    new_wrapup_id,
    parse_json_object,
    sdk_sql_runner,
)
from data_gen.transcript_templates import CATEGORY_WEIGHTS, Resolution

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


# --- wrap_up_call ---------------------------------------------------------------------------

GOOD_WRAP_UP = {
    "disposition": "resolved",
    "category": "troubleshooting",
    "notes": ["The phone showed no service.", "The agent refreshed the SIM and it worked."],
    "promises": [],
    "follow_up": None,
    "sentiment": "positive",
}
# A call whose turns name neither its recorded category nor its recorded outcome.
LATE_FEE_TURNS = [
    {"speaker": "customer", "text": "Hi, this is <PERSON_1>. There's a late fee I don't owe."},
    {"speaker": "agent", "text": "I can't remove it myself, so I'm sending it to be reviewed."},
    {"speaker": "agent", "text": "They'll call you at <PHONE_NUMBER_1> in 3 to 5 business days."},
]


def late_fee_row() -> dict[str, Any]:
    """What the table holds for the call. The wrap-up must use the turns only."""
    return {
        "transcript_id": "T0003",
        "category": "billing",
        "resolution": "escalated",
        "turns_json": json.dumps(LATE_FEE_TURNS),
    }


def wrap_up_tools(reply: dict[str, Any] | str, **parts: Any) -> Tools:
    parts.setdefault("sql", FakeSql([transcript_row()]))
    parts.setdefault("retriever", FakeRetriever())
    text = reply if isinstance(reply, str) else json.dumps(reply)
    return make_tools(llm=FakeLlm(text), **parts)


def test_a_wrap_up_is_drafted_from_the_redacted_turns_with_its_own_prompt() -> None:
    sql = FakeSql([transcript_row()])
    retriever = FakeRetriever([hit("no-service", "No service"), hit("sim", "SIM")])
    reply = "```json\n" + json.dumps(GOOD_WRAP_UP) + "\n```"
    tools = wrap_up_tools(reply, sql=sql, retriever=retriever)

    wrap_up = tools.wrap_up_call(" t0002 ")

    statement, parameters = sql.calls[0]
    assert "frontline.silver.transcripts_redacted" in statement
    assert "bronze" not in statement
    assert parameters == {"transcript_id": ("STRING", "T0002")}
    assert len(sql.calls) == 1
    assert tools.llm.messages[0] == ("system", WRAP_UP_PROMPT)  # type: ignore[attr-defined]
    assert "<PERSON_1>" in tools.llm.messages[1][1]  # type: ignore[attr-defined]
    assert wrap_up.transcript_id == "T0002"
    assert wrap_up.disposition == "resolved"
    assert wrap_up.category == "troubleshooting"
    assert wrap_up.notes == GOOD_WRAP_UP["notes"]
    assert wrap_up.promises == []
    assert wrap_up.follow_up is None
    assert wrap_up.sentiment == "positive"
    # The articles are looked up from what the customer wanted: the first note.
    assert retriever.calls[0]["question"] == "The phone showed no service."
    assert [(c.number, c.title) for c in wrap_up.related_articles] == [
        (1, "No service"),
        (2, "SIM"),
    ]


def test_the_wrap_up_prompt_is_never_given_the_recorded_category_or_outcome() -> None:
    """The model must work both out. If it were told them, its accuracy would mean nothing."""
    sql = FakeSql([late_fee_row()])
    tools = wrap_up_tools(
        {**GOOD_WRAP_UP, "disposition": "escalated", "category": "billing"}, sql=sql
    )

    tools.wrap_up_call("T0003")

    # The lookup does not even read the two columns.
    statement = sql.calls[0][0]
    assert "category" not in statement
    assert "resolution" not in statement
    system, user = tools.llm.messages  # type: ignore[attr-defined]
    assert user == (
        "user",
        '<transcript id="T0003">\n'
        + "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in LATE_FEE_TURNS)
        + "\n</transcript>",
    )
    # The recorded labels of this call appear nowhere in what the model is sent for it.
    assert "billing" not in user[1]
    assert "escalated" not in user[1]
    assert "topic=" not in user[1]
    assert "recorded_outcome" not in user[1]
    # The system prompt is the same for every call: it lists every choice, so it tells
    # the model nothing about this one.
    assert system == ("system", WRAP_UP_PROMPT)
    assert "T0003" not in WRAP_UP_PROMPT


def test_the_wrap_up_prompt_offers_exactly_the_choices_of_the_schema() -> None:
    for choice in (*get_args(Disposition), *get_args(CallCategory), *get_args(FollowUpOwner)):
        assert f'"{choice}"' in WRAP_UP_PROMPT
    assert WRAP_UP_PROMPT_VERSION
    assert WRAP_UP_PROMPT_VERSION != PROMPT_VERSION


def test_the_wrap_up_choices_are_the_generators_own_labels() -> None:
    """The measurement compares a draft with the generator's labels, so the lists must agree."""
    assert set(get_args(Disposition)) == set(get_args(Resolution))
    assert set(get_args(CallCategory)) == set(CATEGORY_WEIGHTS)


def test_a_wrap_up_keeps_promises_and_the_follow_up_with_its_owner() -> None:
    written = {
        "disposition": "Escalated",
        "category": "Billing",
        "notes": ["The customer disputed a late fee.", "  ", "The agent sent it for review."],
        "promises": ["The billing team will call back in 3 to 5 business days."],
        "follow_up": {"owner": "Team", "action": "Review the late fee."},
        "sentiment": "Neutral",
    }
    tools = wrap_up_tools(written, sql=FakeSql([late_fee_row()]))

    wrap_up = tools.wrap_up_call("T0003", with_articles=False)

    assert wrap_up.disposition == "escalated"
    assert wrap_up.category == "billing"
    assert wrap_up.notes == ["The customer disputed a late fee.", "The agent sent it for review."]
    assert wrap_up.promises == ["The billing team will call back in 3 to 5 business days."]
    assert wrap_up.follow_up == FollowUp(owner="team", action="Review the late fee.")
    assert wrap_up.sentiment == "neutral"
    assert wrap_up.related_articles == []
    assert tools.retriever.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "follow_up",
    [None, "none", "None", "", {"owner": "customer", "action": "  "}, {"owner": "agent"}],
)
def test_a_wrap_up_with_nothing_left_to_do_has_no_follow_up(follow_up: Any) -> None:
    tools = wrap_up_tools({**GOOD_WRAP_UP, "follow_up": follow_up})

    assert tools.wrap_up_call("T0002", with_articles=False).follow_up is None


def test_a_wrap_up_with_one_note_as_a_string_and_no_promises_key_is_read() -> None:
    written = {key: value for key, value in GOOD_WRAP_UP.items() if key != "promises"}
    tools = wrap_up_tools({**written, "notes": "The agent refreshed the SIM."})

    wrap_up = tools.wrap_up_call("T0002", with_articles=False)

    assert wrap_up.notes == ["The agent refreshed the SIM."]
    assert wrap_up.promises == []


@pytest.mark.parametrize(
    "reply",
    [
        "I cannot do this.",
        "[1, 2]",
        json.dumps({**GOOD_WRAP_UP, "disposition": "transferred"}),
        json.dumps({**GOOD_WRAP_UP, "category": "roaming"}),
        json.dumps({**GOOD_WRAP_UP, "notes": []}),
        json.dumps({**GOOD_WRAP_UP, "notes": ["a"] * 7}),
        json.dumps({**GOOD_WRAP_UP, "sentiment": "furious"}),
        json.dumps({**GOOD_WRAP_UP, "follow_up": {"owner": "manager", "action": "Call back."}}),
        json.dumps({**GOOD_WRAP_UP, "follow_up": "Call the customer back."}),
        json.dumps({key: value for key, value in GOOD_WRAP_UP.items() if key != "disposition"}),
    ],
)
def test_a_wrap_up_fails_cleanly_on_a_bad_model_reply(reply: str) -> None:
    tools = wrap_up_tools(reply)

    with pytest.raises(ToolError):
        tools.wrap_up_call("T0002")


@pytest.mark.parametrize("bad_id", ["T12", "0007", "T0007; DROP TABLE x", ""])
def test_a_wrap_up_rejects_a_malformed_id_before_any_lookup(bad_id: str) -> None:
    sql = FakeSql()
    tools = wrap_up_tools(GOOD_WRAP_UP, sql=sql)

    with pytest.raises(ToolError, match="not a valid transcript id"):
        tools.wrap_up_call(bad_id)
    assert sql.calls == []


def test_a_wrap_up_of_an_unknown_call_says_so() -> None:
    tools = wrap_up_tools(GOOD_WRAP_UP, sql=FakeSql([]))

    with pytest.raises(ToolError, match="No transcript was found with the id T9999"):
        tools.wrap_up_call("T9999")


def test_every_text_field_of_a_wrap_up_gets_the_output_check(redactor: Redactor) -> None:
    turns = [
        {"speaker": "agent", "text": "You can also call us on 1-800-555-0199."},
        {"speaker": "customer", "text": "Thanks, my number is <PHONE_NUMBER_1>."},
    ]
    written = {
        **GOOD_WRAP_UP,
        "notes": [
            "The agent gave the support line, 1-800-555-0199.",
            "The customer can be reached on 480-555-0132.",
        ],
        "promises": ["A call back on 480-555-0132 tomorrow."],
        "follow_up": {"owner": "agent", "action": "Call the customer back on 480-555-0132."},
    }
    row = {**transcript_row(), "turns_json": json.dumps(turns)}
    tools = wrap_up_tools(written, sql=FakeSql([row]), redactor=redactor)

    wrap_up = tools.wrap_up_call("T0002", with_articles=False)

    # The support line is in the transcript, so it stays. The other number is not.
    assert "1-800-555-0199" in wrap_up.notes[0]
    assert "480-555-0132" not in wrap_up.model_dump_json()
    assert "<PHONE_NUMBER_1>" in wrap_up.notes[1]
    assert "<PHONE_NUMBER_1>" in wrap_up.promises[0]
    assert wrap_up.follow_up is not None
    assert "<PHONE_NUMBER_1>" in wrap_up.follow_up.action


def test_a_long_line_in_a_draft_is_cut_so_the_draft_can_be_saved() -> None:
    tools = wrap_up_tools({**GOOD_WRAP_UP, "notes": ["y" * (MAX_WRAP_UP_CHARS + 50)]})

    assert len(tools.wrap_up_call("T0002", with_articles=False).notes[0]) == MAX_WRAP_UP_CHARS


def test_a_wrap_up_line_is_one_line_of_plain_punctuation() -> None:
    """A model writes "3 to 5" with a non-breaking hyphen, which a search would then miss."""
    # Built from code points, so this file holds no look-alike characters.
    hyphen, dash, left, right = chr(0x2011), chr(0x2013), chr(0x201C), chr(0x201D)
    written = {
        **GOOD_WRAP_UP,
        "notes": [f"Told the customer 3{hyphen}5 business days {dash} by\n  phone."],
        "promises": [f"A call back {left}soon{right}."],
    }
    tools = wrap_up_tools(written)

    wrap_up = tools.wrap_up_call("T0002", with_articles=False)

    assert wrap_up.notes == ["Told the customer 3-5 business days - by phone."]
    assert wrap_up.promises == ['A call back "soon".']


def test_summarize_call_is_still_told_the_recorded_outcome() -> None:
    """The chat tool and the MCP server use the summary. The wrap-up did not change it."""
    llm = FakeLlm(json.dumps(GOOD_SUMMARY))
    tools = make_tools(sql=FakeSql([transcript_row()]), llm=llm, retriever=FakeRetriever())

    tools.summarize_call("T0002")

    assert llm.messages[0] == ("system", SUMMARY_PROMPT)
    assert 'topic="troubleshooting" recorded_outcome="resolved"' in llm.messages[1][1]


# --- save_wrap_up ---------------------------------------------------------------------------


def approved(**changes: Any) -> CallWrapUp:
    fields: dict[str, Any] = {
        "transcript_id": "T0003",
        "disposition": "escalated",
        "category": "billing",
        "notes": ["The customer disputed a late fee.", "The agent sent it for review."],
        "promises": ["The billing team will call back in 3 to 5 business days."],
        "follow_up": {"owner": "team", "action": "Review the late fee."},
        "sentiment": "neutral",
    }
    return CallWrapUp.model_validate({**fields, **changes})


def save_tools(*results: Any, **parts: Any) -> tuple[Tools, FakeSql]:
    sql = FakeSql([late_fee_row()], *results)
    parts.setdefault("wrapup_id", lambda: "WRP-TEST0001")
    return make_tools(sql=sql, **parts), sql


def test_saving_a_wrap_up_writes_one_parameterized_row() -> None:
    tools, sql = save_tools([])
    hostile = "x'); DROP TABLE call_wrapups; --"

    saved = tools.save_wrap_up(approved(notes=[hostile, "The agent sent it for review."]))

    # The call is read first, from the redacted table, to check the text against it.
    assert "frontline.silver.transcripts_redacted" in sql.calls[0][0]
    statement, parameters = sql.calls[1]
    assert statement.startswith("INSERT INTO frontline.ops.call_wrapups ")
    assert "DROP" not in statement
    assert hostile not in statement
    assert parameters == {
        "wrapup_id": ("STRING", "WRP-TEST0001"),
        "saved_at": ("TIMESTAMP", "2026-11-14 17:30:05"),
        "transcript_id": ("STRING", "T0003"),
        "disposition": ("STRING", "escalated"),
        "category": ("STRING", "billing"),
        "lists": (
            "STRING",
            json.dumps(
                {
                    "notes": [hostile, "The agent sent it for review."],
                    "promises": ["The billing team will call back in 3 to 5 business days."],
                }
            ),
        ),
        "follow_up_owner": ("STRING", "team"),
        "follow_up": ("STRING", "Review the late fee."),
        "sentiment": ("STRING", "neutral"),
    }
    # Every parameter in the statement is bound, and nothing else is.
    assert set(re.findall(r":(\w+)", statement)) == set(parameters)
    assert saved.wrapup_id == "WRP-TEST0001"
    assert saved.recorded is True
    assert saved.notes == [hostile, "The agent sent it for review."]


def test_what_the_agent_typed_is_redacted_again_before_it_is_stored(redactor: Redactor) -> None:
    tools, sql = save_tools([], redactor=redactor)

    saved = tools.save_wrap_up(
        approved(
            notes=["The customer, Linda Garcia, disputed a late fee. Her number is 480-555-0132."],
            promises=["A call back on 480-555-0132."],
            follow_up={"owner": "agent", "action": "Email linda.garcia@example.com the outcome."},
        )
    )

    stored = json.dumps(sql.calls[1][1])
    for secret in ("480-555-0132", "Linda Garcia", "linda.garcia@example.com"):
        assert secret not in stored
        assert secret not in saved.model_dump_json()
    assert "<PHONE_NUMBER_1>" in saved.notes[0]
    assert saved.follow_up is not None
    assert "<EMAIL_ADDRESS_1>" in saved.follow_up.action


def test_a_wrap_up_with_no_follow_up_and_no_promises_stores_nulls_and_an_empty_list() -> None:
    tools, sql = save_tools([])

    saved = tools.save_wrap_up(approved(promises=["  "], follow_up=None))

    parameters = sql.calls[1][1]
    assert parameters["follow_up_owner"] == ("STRING", None)
    assert parameters["follow_up"] == ("STRING", None)
    assert json.loads(parameters["lists"][1])["promises"] == []
    assert saved.promises == []
    assert saved.follow_up is None


def test_a_wrap_up_is_not_saved_for_a_call_that_does_not_exist() -> None:
    sql = FakeSql([])
    tools = make_tools(sql=sql)

    with pytest.raises(ToolError, match="No transcript was found with the id T0003"):
        tools.save_wrap_up(approved())
    assert len(sql.calls) == 1
    with pytest.raises(ToolError, match="not a valid transcript id"):
        tools.save_wrap_up(approved(transcript_id="T3; DROP"))


def test_a_wrap_up_whose_notes_are_all_blank_is_refused_and_nothing_is_written() -> None:
    tools, sql = save_tools([])

    with pytest.raises(ToolError, match="at least one note"):
        tools.save_wrap_up(approved(notes=["  ", ""]))
    assert len(sql.calls) == 1


def test_a_wrap_up_is_still_returned_when_the_write_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tools, _ = save_tools(RuntimeError("INSERT ... notes = 'secret text'"))

    with caplog.at_level("WARNING"):
        saved = tools.save_wrap_up(approved())

    assert saved.recorded is False
    assert saved.wrapup_id == "WRP-TEST0001"
    assert saved.notes == approved().notes
    # The failure is logged by its kind only: the message can quote the statement.
    assert "RuntimeError" in caplog.text
    assert "secret text" not in caplog.text


def test_a_dry_run_checks_the_wrap_up_and_writes_nothing(redactor: Redactor) -> None:
    settings = Settings(_env_file=None, record_wrapups=False)  # type: ignore[call-arg]
    tools, sql = save_tools([], settings=settings, redactor=redactor)

    saved = tools.save_wrap_up(approved(notes=["Call 480-555-0132."]))

    assert len(sql.calls) == 1
    assert "INSERT" not in sql.calls[0][0]
    assert saved.recorded is False
    assert saved.notes == ["Call <PHONE_NUMBER_1>."]


def test_a_saved_line_is_cut_to_a_fixed_length() -> None:
    tools, _ = save_tools([])

    saved = tools.save_wrap_up(approved(notes=["y" * (MAX_WRAP_UP_CHARS + 200)]))

    assert len(saved.notes[0]) == MAX_WRAP_UP_CHARS


def test_wrap_up_ids_are_short_and_differ() -> None:
    first, second = new_wrapup_id(), new_wrapup_id()

    assert first != second
    assert first.startswith("WRP-")
    assert len(first) == 12


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
