"""The row the pipeline writes for each call, and what must never be in it."""

import json
from typing import Any

import pytest

from copilot.call_insights import finding_fields, findings_of, insight_row, rules_fired
from copilot.compliance import (
    RULE_CARD_READ_BACK,
    RULE_DISCLOSURE,
    RULE_FULL_SSN,
    RULE_PROMISE,
    RULE_SKIPPED,
    RULES,
    Finding,
    check_call,
)

Turns = list[dict[str, str]]


def call(*lines: str) -> Turns:
    """Turns from lines such as ``"a: Hello"`` and ``"c: Hi"``."""
    speakers = {"a": "agent", "c": "customer"}
    return [{"speaker": speakers[line[0]], "text": line[3:]} for line in lines]


VERIFIED = (
    "a: First I need to verify a few things. Can I have your account number, please?",
    "c: Sure, it's <ACCOUNT_NUMBER_1>.",
)
# One call for each rule, in the wording the checker's own tests use.
BREACHES: dict[str, Turns] = {
    RULE_DISCLOSURE: call(
        "c: My bill looks wrong, zebra.",
        "a: I can see your balance is <CPNI_AMOUNT_1> this month.",
        *VERIFIED,
    ),
    RULE_SKIPPED: call(
        "c: My bill looks wrong, zebra.",
        "a: I can see your balance is <CPNI_AMOUNT_1> this month.",
        "c: Thanks, zebra.",
    ),
    RULE_CARD_READ_BACK: call(
        *VERIFIED,
        "c: The card is <CREDIT_CARD_1>, zebra.",
        "a: Thanks, zebra. I have <CREDIT_CARD_1>.",
    ),
    RULE_PROMISE: call(
        *VERIFIED,
        "c: Can you take the late fee off, zebra?",
        "a: I've waived that fee for you, zebra.",
    ),
    RULE_FULL_SSN: call(
        "a: For security, zebra, can I have your full Social Security number?",
        "c: It's <ACCOUNT_NUMBER_1>.",
    ),
}
CLEAN = call(*VERIFIED, "c: How do I set up voicemail?", "a: Hold the 1 key, then follow the menu.")


@pytest.mark.parametrize("rule", RULES)
def test_a_call_that_breaks_a_rule_gets_a_row_that_names_it(rule: str) -> None:
    row = insight_row("T0201", BREACHES[rule])

    assert row["transcript_id"] == "T0201"
    assert row["n_turns"] == len(BREACHES[rule])
    assert row["rules"] == [rule]
    assert row["n_findings"] == len(row["findings"]) >= 1
    assert {finding["rule"] for finding in row["findings"]} == {rule}
    assert all(0 <= finding["turn_index"] < row["n_turns"] for finding in row["findings"])


def test_a_call_in_which_no_rule_fires_still_has_a_row() -> None:
    assert insight_row("T0001", CLEAN) == {
        "transcript_id": "T0001",
        "n_turns": 4,
        "n_findings": 0,
        "rules": [],
        "findings": [],
    }


@pytest.mark.parametrize("rule", RULES)
def test_a_row_holds_no_text_from_the_call(rule: str) -> None:
    turns = BREACHES[rule]
    row = insight_row("T0201", turns)
    written = json.dumps(row)

    # Every turn carries the word "zebra" or a placeholder. Neither may reach the row.
    assert "zebra" not in written
    assert "<" not in written
    said = {turn["text"] for turn in turns}
    assert not said & {finding["reason"] for finding in row["findings"]}
    # A row is exactly these columns, so a new one cannot bring text in unnoticed.
    assert set(row) == {"transcript_id", "n_turns", "n_findings", "rules", "findings"}
    assert all(set(finding) == {"rule", "turn_index", "reason"} for finding in row["findings"])


def test_the_row_is_what_the_checker_found_and_nothing_more() -> None:
    turns = BREACHES[RULE_PROMISE]

    assert findings_of(turns) == check_call(turns)
    assert insight_row("T0201", turns)["findings"] == [
        {"rule": finding.rule, "turn_index": finding.turn_index, "reason": finding.reason}
        for finding in check_call(turns)
    ]


def test_the_rules_that_fired_are_listed_once_each_in_the_checkers_order() -> None:
    findings = [
        Finding(RULE_PROMISE, 9, "x"),
        Finding(RULE_CARD_READ_BACK, 4, "x"),
        Finding(RULE_PROMISE, 12, "x"),
    ]

    assert rules_fired(findings) == [RULE_CARD_READ_BACK, RULE_PROMISE]
    assert rules_fired([]) == []
    assert finding_fields(findings[0]) == {"rule": RULE_PROMISE, "turn_index": 9, "reason": "x"}


class Row:
    """A turn as Spark hands it to a pandas function: read by key, with no ``get``."""

    def __init__(self, **fields: Any) -> None:
        self._fields = fields

    def __getitem__(self, key: str) -> Any:
        return self._fields[key]


def test_turns_from_a_table_are_read_by_key_and_a_null_is_an_empty_turn() -> None:
    turns = [
        Row(speaker="customer", text="The card is <CREDIT_CARD_1>."),
        Row(speaker="agent", text=None),
        Row(speaker=None, text="I have <CREDIT_CARD_1>."),
        Row(speaker="agent", text="I have <CREDIT_CARD_1>."),
    ]

    row = insight_row("T0300", turns)  # type: ignore[arg-type]

    # Only the last turn is an agent's with a card in it. A turn with no speaker is nobody's.
    assert [(f["rule"], f["turn_index"]) for f in row["findings"]] == [(RULE_CARD_READ_BACK, 3)]
    assert row["n_turns"] == 4
