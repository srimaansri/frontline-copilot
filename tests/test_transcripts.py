"""Reading redacted transcripts for display, with a fake SQL runner."""

import json
from typing import Any

import pytest

from copilot.config import Settings
from copilot.tools import ToolError
from copilot.transcripts import get_transcript, list_transcripts

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
