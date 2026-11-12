"""Redaction behaviour.

These tests run on the small spaCy model so CI stays fast. Names are therefore
tested through the cue patterns, which do not depend on the model.
"""

import pytest

import copilot.redaction as redaction_module
from copilot.redaction import (
    ALL_ENTITY_TYPES,
    Entity,
    PlaceholderMap,
    Redactor,
    _Detection,
    _resolve_overlaps,
    _trim_greeting,
    get_redactor,
    redact,
)

TEST_MODEL = "en_core_web_sm"


@pytest.fixture(scope="session")
def redactor() -> Redactor:
    return Redactor(TEST_MODEL)


def _types(result: redaction_module.RedactionResult) -> list[str]:
    return [entity.entity_type for entity in result.entities]


# --- one case per entity type ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "entity_type", "secret"),
    [
        ("My name is Linda Garcia and I need help.", "PERSON", "Linda Garcia"),
        ("my name is linda garcia", "PERSON", "linda garcia"),
        ("Hi Linda, I'm Kelly.", "PERSON", "Kelly"),
        ("You're all set, Linda.", "PERSON", "Linda"),
        ("Northline support, Maria speaking.", "PERSON", "Maria"),
        ("You can reach me at 480-555-0132.", "PHONE_NUMBER", "480-555-0132"),
        ("My number is (480) 555-0132.", "PHONE_NUMBER", "(480) 555-0132"),
        ("It's 480.555.0132 if you need it.", "PHONE_NUMBER", "480.555.0132"),
        ("Dial +1 480 555 0132 tomorrow.", "PHONE_NUMBER", "+1 480 555 0132"),
        ("They will call you back at 4805550132 today.", "PHONE_NUMBER", "4805550132"),
        ("Send it to linda.garcia@example.com please.", "EMAIL_ADDRESS",
         "linda.garcia@example.com"),
        ("I live at 4821 Maple Street, Mesa, AZ 85201.", "ADDRESS",
         "4821 Maple Street, Mesa, AZ 85201"),
        ("Mail it to 77 Oak Ave Apt 4B.", "ADDRESS", "77 Oak Ave Apt 4B"),
        ("I was born on March 14, 1952.", "DATE_OF_BIRTH", "March 14, 1952"),
        ("DOB is 03/14/1952.", "DATE_OF_BIRTH", "03/14/1952"),
        ("My account number is 482913774.", "ACCOUNT_NUMBER", "482913774"),
        ("The IMEI is 490154203237518.", "IMEI", "490154203237518"),
        ("It shows 35 209900 176148 1 on the box.", "IMEI", "35 209900 176148 1"),
        ("The SIM says 8901260222112345678.", "ICCID", "8901260222112345678"),
        ("The last four of my social are 4821.", "SSN_LAST4", "4821"),
        ("My card is 4111 1111 1111 1111.", "CREDIT_CARD", "4111 1111 1111 1111"),
        ("Your bill last month was $84.12.", "CPNI_AMOUNT", "$84.12"),
        ("You used 412 minutes last month.", "CPNI_USAGE", "412 minutes"),
        ("You've used about 6.2 GB this month.", "CPNI_USAGE", "6.2 GB"),
    ],
)  # fmt: skip
def test_entity_is_detected_and_replaced(
    redactor: Redactor, text: str, entity_type: str, secret: str
) -> None:
    result = redactor.redact(text)

    assert entity_type in _types(result)
    assert secret not in result.text
    assert f"<{entity_type}_1>" in result.text


def test_every_entity_type_has_a_test_case() -> None:
    # Guards the parametrised list above against a new type being added untested.
    assert len(ALL_ENTITY_TYPES) == 12


# --- things that must be left alone -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The plan is $30/month.",
        "That plan is $30 a month.",
        "An Extra Line is $15 per month.",
        "The International Calling Pack includes 300 minutes.",
        "You can add a Data Top-Up of 5 GB for $10.",
        "You can forward scam texts to 7726.",
        "Please turn the phone off, wait 30 seconds, and turn it back on.",
        "Press and hold the 1 key, then follow the prompts.",
        "Thank you for calling Northline Wireless.",
        "I'm sorry to hear that.",
        "It's working now!",
        "",
        "   ",
    ],
)
def test_non_personal_text_is_unchanged(redactor: Redactor, text: str) -> None:
    result = redactor.redact(text)

    assert result.text == text
    assert result.entities == ()


def test_four_digits_alone_are_not_redacted(redactor: Redactor) -> None:
    assert redactor.redact("4821.").text == "4821."


# --- checksums ------------------------------------------------------------------------


def test_luhn_valid_fifteen_digits_is_an_imei_not_a_card(redactor: Redactor) -> None:
    assert _types(redactor.redact("It is 490154203237518.")) == ["IMEI"]


def test_luhn_valid_visa_is_a_card(redactor: Redactor) -> None:
    assert _types(redactor.redact("It is 4111111111111111.")) == ["CREDIT_CARD"]


def test_amex_shaped_number_is_a_card_not_an_imei(redactor: Redactor) -> None:
    assert _types(redactor.redact("It is 378282246310005.")) == ["CREDIT_CARD"]


def test_long_digit_run_with_a_bad_checksum_is_still_masked(redactor: Redactor) -> None:
    result = redactor.redact("The number is 4111111111111112.")

    assert "4111111111111112" not in result.text
    assert len(result.entities) == 1


def test_iccid_wins_over_card_for_a_number_starting_89(redactor: Redactor) -> None:
    assert _types(redactor.redact("89012602221123456789")) == ["ICCID"]


# --- conversations ------------------------------------------------------------------


def test_short_answer_borrows_the_question_as_context(redactor: Redactor) -> None:
    results = redactor.redact_turns(
        ["Can I get the last four digits of your Social Security number?", "4821."]
    )

    assert results[1].text == "<SSN_LAST4_1>."


def test_bare_answer_to_an_account_question_is_an_account_number(redactor: Redactor) -> None:
    results = redactor.redact_turns(["What's the account number?", "4829137740"])

    assert _types(results[1]) == ["ACCOUNT_NUMBER"]


def test_bare_ten_digits_default_to_a_phone_number(redactor: Redactor) -> None:
    assert _types(redactor.redact("4805550132")) == ["PHONE_NUMBER"]


def test_whole_turn_name_after_a_name_question(redactor: Redactor) -> None:
    results = redactor.redact_turns(["May I have your name?", "Linda Garcia."])

    assert results[1].text == "<PERSON_1>."


def test_long_turn_does_not_borrow_context(redactor: Redactor) -> None:
    long_turn = "Okay so I looked and the code on the back of the box says 4821 I think."

    results = redactor.redact_turns(["I'll need the last four of your social.", long_turn])

    assert results[1].text == long_turn


def test_placeholders_are_consistent_across_a_conversation(redactor: Redactor) -> None:
    results = redactor.redact_turns(
        [
            "My name is Linda Garcia.",
            "Thanks, Linda. What is the phone number?",
            "It's 480-555-0132.",
            "This is Robert Chen, her husband.",
            "So that is (480) 555-0132?",
        ]
    )

    assert results[0].text == "My name is <PERSON_1>."
    assert results[1].text.startswith("Thanks, <PERSON_1>.")
    assert results[2].text == "It's <PHONE_NUMBER_1>."
    assert results[3].text.startswith("This is <PERSON_2>")
    assert "<PHONE_NUMBER_1>" in results[4].text


# --- result shape ---------------------------------------------------------------------


def test_offsets_refer_to_the_original_text(redactor: Redactor) -> None:
    text = "Call 480-555-0132 or write to linda@example.com."

    result = redactor.redact(text)

    found = {entity.entity_type: text[entity.start : entity.end] for entity in result.entities}
    assert found == {"PHONE_NUMBER": "480-555-0132", "EMAIL_ADDRESS": "linda@example.com"}
    assert result.text == "Call <PHONE_NUMBER_1> or write to <EMAIL_ADDRESS_1>."
    assert result.entity_counts == {"PHONE_NUMBER": 1, "EMAIL_ADDRESS": 1}


def test_entity_does_not_carry_the_raw_value() -> None:
    assert set(Entity.__dataclass_fields__) == {
        "entity_type",
        "start",
        "end",
        "score",
        "placeholder",
    }


def test_allow_list_is_configurable() -> None:
    custom = Redactor(TEST_MODEL, allow_list=["Linda Garcia"])

    assert custom.redact("My name is Linda Garcia.").entities == ()


# --- helpers ----------------------------------------------------------------------------


def test_overlaps_keep_the_higher_score() -> None:
    kept = _resolve_overlaps(
        [_Detection("PHONE_NUMBER", 0, 10, 0.5), _Detection("ACCOUNT_NUMBER", 0, 10, 0.85)]
    )

    assert [d.entity_type for d in kept] == ["ACCOUNT_NUMBER"]


def test_overlaps_prefer_the_longer_span_on_equal_score() -> None:
    kept = _resolve_overlaps([_Detection("ADDRESS", 0, 10, 0.7), _Detection("ADDRESS", 0, 30, 0.7)])

    assert [(d.start, d.end) for d in kept] == [(0, 30)]


def test_overlaps_fall_back_to_type_priority() -> None:
    kept = _resolve_overlaps(
        [_Detection("ACCOUNT_NUMBER", 0, 10, 0.5), _Detection("PHONE_NUMBER", 0, 10, 0.5)]
    )

    assert [d.entity_type for d in kept] == ["PHONE_NUMBER"]


def test_non_overlapping_detections_are_all_kept_in_order() -> None:
    kept = _resolve_overlaps([_Detection("B", 20, 30, 0.5), _Detection("A", 0, 10, 0.9)])

    assert [d.entity_type for d in kept] == ["A", "B"]


def test_greeting_is_trimmed_from_a_person_span() -> None:
    text = "Hello Angel, welcome."

    trimmed = _trim_greeting(_Detection("PERSON", 0, 11, 0.85), text)

    assert text[trimmed.start : trimmed.end] == "Angel"


def test_greeting_trim_leaves_other_spans_alone() -> None:
    phone = _Detection("PHONE_NUMBER", 0, 5, 0.9)
    name = _Detection("PERSON", 0, 5, 0.9)

    assert _trim_greeting(phone, "Hello") is phone
    assert _trim_greeting(name, "Angel") is name
    # A span that is only a greeting is not shrunk to nothing.
    assert _trim_greeting(name, "Hello ") is name


def test_placeholder_map_numbers_values_by_type() -> None:
    mapping = PlaceholderMap()

    assert mapping.placeholder("PHONE_NUMBER", "480-555-0132") == "<PHONE_NUMBER_1>"
    assert mapping.placeholder("PHONE_NUMBER", "(480) 555-0132") == "<PHONE_NUMBER_1>"
    assert mapping.placeholder("PHONE_NUMBER", "602-555-0100") == "<PHONE_NUMBER_2>"
    assert mapping.placeholder("EMAIL_ADDRESS", "A@Example.com") == "<EMAIL_ADDRESS_1>"
    assert mapping.placeholder("EMAIL_ADDRESS", "a@example.com") == "<EMAIL_ADDRESS_1>"


def test_placeholder_map_links_first_name_to_full_name() -> None:
    mapping = PlaceholderMap()

    assert mapping.placeholder("PERSON", "Linda Garcia") == "<PERSON_1>"
    assert mapping.placeholder("PERSON", "Linda") == "<PERSON_1>"
    assert mapping.placeholder("PERSON", "Robert Chen") == "<PERSON_2>"
    assert mapping.placeholder("PERSON", "Robert") == "<PERSON_2>"


# --- module-level helpers ------------------------------------------------------------------


def test_get_redactor_is_cached() -> None:
    assert get_redactor(TEST_MODEL) is get_redactor(TEST_MODEL)


def test_redact_uses_the_default_redactor(
    monkeypatch: pytest.MonkeyPatch, redactor: Redactor
) -> None:
    monkeypatch.setattr(redaction_module, "get_redactor", lambda: redactor)

    assert redact("Call 480-555-0132.").text == "Call <PHONE_NUMBER_1>."
