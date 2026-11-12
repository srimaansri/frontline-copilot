"""Luhn checksum behaviour."""

import pytest

from copilot.luhn import luhn_check_digit, luhn_valid


@pytest.mark.parametrize(
    "number",
    [
        "4111111111111111",  # well-known Visa test number
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "490154203237518",  # IMEI example from the Luhn literature
        "79927398713",
    ],
)
def test_valid_numbers_pass(number: str) -> None:
    assert luhn_valid(number)


@pytest.mark.parametrize("number", ["4111111111111112", "490154203237519", "79927398710"])
def test_invalid_numbers_fail(number: str) -> None:
    assert not luhn_valid(number)


@pytest.mark.parametrize("text", ["", "abc", "-- --"])
def test_text_without_digits_is_not_valid(text: str) -> None:
    assert not luhn_valid(text)


@pytest.mark.parametrize(
    ("partial", "expected"),
    [("7992739871", "3"), ("49015420323751", "8"), ("411111111111111", "1")],
)
def test_check_digit(partial: str, expected: str) -> None:
    assert luhn_check_digit(partial) == expected
    assert luhn_valid(partial + expected)
