"""Luhn checksum, used by card numbers, IMEIs and ICCIDs."""

from __future__ import annotations


def _digits(value: str) -> list[int]:
    return [int(char) for char in value if char.isdigit()]


def luhn_valid(number: str) -> bool:
    """Return True if the digits in ``number`` pass the Luhn check.

    Spaces and dashes are ignored. A string with no digits is not valid.
    """
    digits = _digits(number)
    if not digits:
        return False
    total = 0
    for position, digit in enumerate(reversed(digits)):
        if position % 2 == 1:
            doubled = digit * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += digit
    return total % 10 == 0


def luhn_check_digit(partial: str) -> str:
    """Return the digit that, appended to ``partial``, makes it Luhn-valid."""
    # Exactly one of the ten digits always satisfies the check.
    return next(digit for digit in "0123456789" if luhn_valid(partial + digit))
