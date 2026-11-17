"""Reading redacted transcripts for display, with a fake SQL runner."""

import json
from typing import Any

import pytest

from copilot.config import Settings
from copilot.tools import ToolError
from copilot.transcripts import MAX_LISTED, get_transcript, list_calls, list_transcripts

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


class FakeSql:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, statement: str, parameters: Any) -> list[dict[str, Any]]:
        self.calls.append((statement, dict(parameters)))
        return self.rows


def test_listing_reads_only_the_redacted_table() -> None:
    sql = FakeSql([{"transcript_id": "T0001", "category": "billing", "resolution": "escalated"}])

    listed = list_transcripts(sql, SETTINGS)

    assert listed == [{"transcript_id": "T0001", "category": "billing", "resolution": "escalated"}]
    statement, parameters = sql.calls[0]
    assert "frontline.silver.transcripts_redacted" in statement
    assert "bronze" not in statement
    assert parameters == {}


def test_the_calls_list_joins_what_the_rule_check_found() -> None:
    sql = FakeSql(
        [
            {"transcript_id": "T0001", "category": "billing", "resolution": "escalated",
             "rules_json": "[]"},
            {"transcript_id": "T0207", "category": "billing", "resolution": "resolved",
             "rules_json": '["card_read_back", "unauthorized_promise"]'},
            {"transcript_id": "T0300", "category": "scam", "resolution": "unresolved",
             "rules_json": None},
        ]
    )  # fmt: skip

    listed = list_calls(sql, SETTINGS)

    assert [call["findings"] for call in listed] == [
        [],
        ["card_read_back", "unauthorized_promise"],
        # A call with no row in the insights table has not been checked.
        None,
    ]
    assert set(listed[0]) == {"transcript_id", "category", "resolution", "findings"}
    statement, parameters = sql.calls[0]
    assert "FROM frontline.silver.transcripts_redacted AS t" in statement
    assert "LEFT JOIN frontline.gold.call_insights AS i" in statement
    assert "bronze" not in statement
    assert "WHERE" not in statement
    assert f"LIMIT {MAX_LISTED}" in statement
    assert parameters == {}


def test_the_list_has_room_for_every_call() -> None:
    # 200 ordinary calls and 382 with a seeded breach.
    assert MAX_LISTED >= 582


def test_the_calls_list_filters_on_any_finding_or_on_one_rule_as_a_bound_value() -> None:
    sql = FakeSql([])

    list_calls(sql, SETTINGS, "any")
    list_calls(sql, SETTINGS, " Card_Read_Back ")

    any_statement, any_parameters = sql.calls[0]
    assert "WHERE i.n_findings > 0 ORDER BY" in any_statement
    assert any_parameters == {}
    rule_statement, rule_parameters = sql.calls[1]
    assert "WHERE array_contains(i.rules, :rule) ORDER BY" in rule_statement
    assert rule_parameters == {"rule": ("STRING", "card_read_back")}
    assert "card_read_back" not in rule_statement


@pytest.mark.parametrize("finding", ["", "none", "card_read_back' OR '1'='1", "rules"])
def test_a_filter_that_is_not_a_rule_is_rejected_before_any_lookup(finding: str) -> None:
    sql = FakeSql([])

    with pytest.raises(ToolError, match="must be one of: any, disclosure_before_verification"):
        list_calls(sql, SETTINGS, finding)
    assert sql.calls == []


def test_a_transcript_comes_back_as_speaker_and_text_turns() -> None:
    turns = [{"speaker": "customer", "text": "Hi, this is <PERSON_1>."}]
    sql = FakeSql([{"turns_json": json.dumps(turns)}])

    assert get_transcript(sql, SETTINGS, " t0002 ") == turns
    assert sql.calls[0][1] == {"transcript_id": ("STRING", "T0002")}
    assert "T0002" not in sql.calls[0][0]


@pytest.mark.parametrize("bad_id", ["T12", "0002", "T0002; DROP TABLE x", ""])
def test_a_malformed_id_is_rejected_before_any_lookup(bad_id: str) -> None:
    sql = FakeSql([])

    with pytest.raises(ToolError, match="four digits"):
        get_transcript(sql, SETTINGS, bad_id)
    assert sql.calls == []


def test_an_unknown_id_says_so() -> None:
    with pytest.raises(ToolError, match="No transcript was found with the id T9999"):
        get_transcript(FakeSql([]), SETTINGS, "T9999")
