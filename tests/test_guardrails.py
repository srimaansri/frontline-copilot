"""Question redaction and citation checking."""

import pytest

from copilot.guardrails import (
    FLAG_INVALID_CITATION,
    FLAG_NO_CITATION,
    check_citations,
    redact_question,
)
from copilot.redaction import Redactor


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


# --- redacting the question ------------------------------------------------------------


def test_personal_data_in_a_question_is_replaced_and_flagged(redactor: Redactor) -> None:
    result = redact_question(
        "The customer at 480-555-0132, linda@example.com, asks about roaming.", redactor
    )

    assert "480-555-0132" not in result.text
    assert "linda@example.com" not in result.text
    assert "<PHONE_NUMBER_1>" in result.text
    assert result.flags == ("pii_in_question:EMAIL_ADDRESS", "pii_in_question:PHONE_NUMBER")


def test_an_ordinary_question_is_unchanged(redactor: Redactor) -> None:
    question = "How do I set up voicemail on a new phone?"

    result = redact_question(question, redactor)

    assert result.text == question
    assert result.flags == ()


# --- citations ---------------------------------------------------------------------------


def test_valid_citations_are_kept_in_order_of_first_use() -> None:
    checked = check_citations("Pay in the app [2]. AutoPay is free [1]. See also [2].", 3)

    assert checked.text == "Pay in the app [2]. AutoPay is free [1]. See also [2]."
    assert checked.cited == (2, 1)
    assert checked.flags == ()


def test_a_citation_to_a_source_that_was_not_given_is_removed() -> None:
    checked = check_citations("The fee is $5 [1]. It is waived on request [7].", 3)

    assert checked.text == "The fee is $5 [1]. It is waived on request."
    assert checked.cited == (1,)
    assert checked.flags == (FLAG_INVALID_CITATION,)


def test_zero_is_not_a_valid_source_number() -> None:
    checked = check_citations("The fee is $5 [0].", 3)

    assert checked.text == "The fee is $5."
    assert checked.flags == (FLAG_INVALID_CITATION, FLAG_NO_CITATION)


def test_grouped_citations_keep_only_their_valid_numbers() -> None:
    checked = check_citations("Dial 611 [1, 5] or use the app [2][9].", 2)

    assert checked.text == "Dial 611 [1] or use the app [2]."
    assert checked.cited == (1, 2)
    assert checked.flags == (FLAG_INVALID_CITATION,)


def test_an_answer_without_citations_is_flagged() -> None:
    checked = check_citations("I do not know.", 3)

    assert checked.text == "I do not know."
    assert checked.cited == ()
    assert checked.flags == (FLAG_NO_CITATION,)


def test_lenticular_and_decorated_citations_are_read_as_plain_ones() -> None:
    left, right, dagger = chr(0x3010), chr(0x3011), chr(0x2020)
    answer = f"The fee is $5{left}1{right}. Ask for a waiver {left}2{dagger}L3-L7{right}."

    checked = check_citations(answer, 2)

    assert checked.text == "The fee is $5[1]. Ask for a waiver [2]."
    assert checked.cited == (1, 2)
    assert checked.flags == ()


def test_typographic_punctuation_in_an_answer_becomes_ascii() -> None:
    nb_hyphen, quote = chr(0x2011), chr(0x2019)
    answer = f"Dial 1{nb_hyphen}800{nb_hyphen}555{nb_hyphen}0199. It{quote}s free [1]."

    checked = check_citations(answer, 1)

    assert checked.text == "Dial 1-800-555-0199. It's free [1]."
    assert checked.text.isascii()


def test_brackets_that_are_not_citations_are_left_alone() -> None:
    checked = check_citations("Tap [Settings] then Display [1].", 1)

    assert checked.text == "Tap [Settings] then Display [1]."
    assert checked.cited == (1,)
