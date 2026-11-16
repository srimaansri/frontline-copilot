"""Reading a saved wrap-up back, with a fake SQL runner."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from copilot.config import Settings
from copilot.schemas import FollowUp
from copilot.tools import ToolError
from copilot.wrapups import StoredWrapUp, latest_wrap_up

SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]
# A row as the warehouse returns it: the two lists as JSON text, the time as text.
ROW: dict[str, Any] = {
    "wrapup_id": "WRP-4F2A91C7",
    "saved_at": "2026-11-14 16:42:05",
    "disposition": "escalated",
    "category": "billing",
    "notes_json": json.dumps(["The customer disputed a late fee.", "Sent for review."]),
    "promises_json": json.dumps(["They will call <PHONE_NUMBER_1> if they need anything."]),
    "follow_up_owner": "team",
    "follow_up": "The billing team reviews the late fee.",
    "sentiment": "neutral",
}


class FakeSql:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, statement: str, parameters: Any) -> list[dict[str, Any]]:
        self.calls.append((statement, dict(parameters)))
        return self.rows


def test_the_newest_saved_wrap_up_of_a_call_is_read_back_as_it_was_stored() -> None:
    sql = FakeSql([ROW])

    stored = latest_wrap_up(sql, SETTINGS, " t0001 ")

    assert stored == StoredWrapUp(
        wrapup_id="WRP-4F2A91C7",
        transcript_id="T0001",
        disposition="escalated",
        category="billing",
        notes=["The customer disputed a late fee.", "Sent for review."],
        # A placeholder the output check put there when it was saved is kept as it is.
        promises=["They will call <PHONE_NUMBER_1> if they need anything."],
        follow_up=FollowUp(owner="team", action="The billing team reviews the late fee."),
        sentiment="neutral",
        recorded=True,
        saved_at="2026-11-14T16:42:05Z",
    )
    statement, parameters = sql.calls[0]
    assert "FROM frontline.ops.call_wrapups WHERE transcript_id = :transcript_id" in statement
    # A call saved twice has two rows. The later one is the record.
    assert "ORDER BY saved_at DESC, wrapup_id DESC LIMIT 1" in statement
    # The id is a bound value, and nothing but the wrap-ups table is read.
    assert parameters == {"transcript_id": ("STRING", "T0001")}
    assert "T0001" not in statement
    assert "silver" not in statement
    assert "bronze" not in statement


def test_a_call_with_no_saved_wrap_up_has_none() -> None:
    assert latest_wrap_up(FakeSql([]), SETTINGS, "T0002") is None


def test_a_record_with_nothing_left_to_do_and_nothing_promised_reads_back_that_way() -> None:
    row = {**ROW, "promises_json": "[]", "follow_up_owner": None, "follow_up": None}

    stored = latest_wrap_up(FakeSql([row]), SETTINGS, "T0001")

    assert stored is not None
    assert stored.promises == []
    assert stored.follow_up is None


def test_a_null_list_is_an_empty_list() -> None:
    stored = latest_wrap_up(FakeSql([{**ROW, "promises_json": None}]), SETTINGS, "T0001")

    assert stored is not None
    assert stored.promises == []


@pytest.mark.parametrize("bad_id", ["T12", "0002", "T0002; DROP TABLE x", ""])
def test_a_malformed_id_is_rejected_before_any_lookup(bad_id: str) -> None:
    sql = FakeSql([ROW])

    with pytest.raises(ToolError, match="not a valid transcript id"):
        latest_wrap_up(sql, SETTINGS, bad_id)
    assert sql.calls == []


def test_a_row_that_is_not_a_wrap_up_is_not_passed_on_as_one() -> None:
    # Only save_wrap_up writes the table, so this means the table was changed by hand.
    with pytest.raises(ValidationError):
        latest_wrap_up(FakeSql([{**ROW, "disposition": "abandoned"}]), SETTINGS, "T0001")
