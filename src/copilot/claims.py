"""Check that the figures in an answer are figures the copilot was given.

A model can write "$7" where its source says "$5", and nothing about the answer
looks wrong. The citation check does not catch it: the marker still points at a
real source. This module reads the checkable values out of an answer (prices,
amounts with a unit, percentages, phone numbers, short codes and web
addresses) and looks for each one in the evidence: the retrieved text, the tool
results and the question.

It is deterministic and makes no model call, so it runs on every answer.

What it does not do:

- It checks that a value is present in the evidence, not that it is attached to
  the right thing. "$10" passes if any source mentions $10.
- It does not read numbers written as words ("five dollars").
- A value the model worked out ("two lines at $25 is $50") is not in the
  evidence and is reported, although it may be right.

How often it catches a changed figure, and how often it reports a correct one,
is measured by ``eval/claim_check_eval.py``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

ClaimKind = Literal["money", "quantity", "percent", "phone", "code", "url"]

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# Spellings of each unit. The first group of a match is normalised to the key.
_UNITS: dict[str, str] = {
    "gb": r"gb|gigabytes?|gigs?",
    "mb": r"mb|megabytes?",
    "mbps": r"mbps",
    "second": r"seconds?|secs?",
    "minute": r"minutes?|mins?",
    "hour": r"hours?|hrs?",
    "day": r"days?",
    "week": r"weeks?",
    "month": r"months?",
    "year": r"years?",
    "digit": r"digits?",
    "line": r"lines?",
}
_UNIT_PATTERN = "|".join(f"(?P<{name}>{spelling})" for name, spelling in _UNITS.items())

_URL_RE = re.compile(
    r"(?<![@\w.-])(?:https?://)?(?:[a-z0-9-]+\.)+(?:example|com|net|org|gov|io)(?:/[\w\-./%#?=&]*)?",
    re.IGNORECASE,
)
# Seven or more digits, however they are grouped: a phone number.
_PHONE_RE = re.compile(r"(?<![\w$])\+?\d[\d\s().-]{5,}\d(?!\w)")
_MONEY_RE = re.compile(rf"\$\s?({_NUMBER})|\b({_NUMBER})\s*(?:dollars?|usd)\b", re.IGNORECASE)
_PERCENT_RE = re.compile(rf"\b({_NUMBER})\s?(?:%|percent\b)", re.IGNORECASE)
# "10 days", "35 GB", "4-6 digits", "4- to 6-digit", "24-hour".
_QUANTITY_RE = re.compile(
    rf"\b({_NUMBER})(?:\s*-?\s*(?:to|-)\s*({_NUMBER}))?[\s-]*(?:{_UNIT_PATTERN})\b",
    re.IGNORECASE,
)
# A short number someone is told to dial or text, such as 611.
_CODE_RE = re.compile(
    r"\b(?:dial|dialing|call|calling|text|texting)\s+\**(\d{3,6})\b", re.IGNORECASE
)
_STANDALONE_NUMBER_RE = re.compile(rf"(?<![\w.]){_NUMBER}(?![\w])")
# In a catalogue row, the key says what a bare number is.
_MONEY_KEY_RE = re.compile(r"price|usd|fee|cost", re.IGNORECASE)


@dataclass(frozen=True)
class Claim:
    """One checkable value in a piece of text."""

    kind: ClaimKind
    # The value as it was written, for showing to a person.
    text: str
    # The value in a form that can be compared: "5", "1200.5", digits, a bare address.
    value: str
    # For a quantity, its unit ("gb", "day"). Empty otherwise.
    unit: str = ""
    start: int = 0
    end: int = 0

    @property
    def key(self) -> tuple[str, str, str]:
        """What makes two claims the same claim."""
        return (self.kind, self.value, self.unit)


def normal_number(text: str) -> str:
    """A number as a canonical string: "5.00" and "5" are "5", "1,200" is "1200"."""
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return text
    if number == number.to_integral_value():
        return str(number.to_integral_value())
    return str(number.normalize())


def _normal_url(text: str) -> str:
    address = re.sub(r"^https?://", "", text.lower().rstrip(".,;:!?)"))
    return address.removeprefix("www.").rstrip("/")


def _unit(match: re.Match[str]) -> str:
    return next(name for name in _UNITS if match.group(name))


def extract_claims(text: str) -> list[Claim]:
    """The checkable values in ``text``, in the order they appear.

    Each stretch of text yields at most one claim: once a web address or a phone
    number has been read, the digits inside it are not read again as an amount.
    """
    claims: list[Claim] = []
    taken = [False] * len(text)

    def free(start: int, end: int) -> bool:
        return not any(taken[start:end])

    def take(claim: Claim) -> None:
        claims.append(claim)
        taken[claim.start : claim.end] = [True] * (claim.end - claim.start)

    for match in _URL_RE.finditer(text):
        take(Claim("url", match.group(0), _normal_url(match.group(0)), "", *match.span()))
    for match in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 7 and free(*match.span()):
            take(Claim("phone", match.group(0), digits, "", *match.span()))
    for match in _MONEY_RE.finditer(text):
        if free(*match.span()):
            number = match.group(1) or match.group(2)
            take(Claim("money", match.group(0), normal_number(number), "", *match.span()))
    for match in _PERCENT_RE.finditer(text):
        if free(*match.span()):
            value = normal_number(match.group(1))
            take(Claim("percent", match.group(0), value, "", *match.span()))
    for match in _QUANTITY_RE.finditer(text):
        if free(*match.span()):
            unit = _unit(match)
            take(
                Claim(
                    "quantity", match.group(0), normal_number(match.group(1)), unit, *match.span()
                )
            )
            if match.group(2):
                # The far end of a range, "4-6 digits", is a second claim with the same unit.
                claims.append(
                    Claim(
                        "quantity",
                        match.group(0),
                        normal_number(match.group(2)),
                        unit,
                        *match.span(),
                    )
                )
    for match in _CODE_RE.finditer(text):
        if free(*match.span(1)):
            take(Claim("code", match.group(1), match.group(1), "", *match.span(1)))
    return sorted(claims, key=lambda claim: (claim.start, claim.value))


class Evidence:
    """Everything the copilot was given to answer from, indexed for lookup."""

    def __init__(self, texts: Sequence[str]) -> None:
        """Read the values out of each piece of evidence."""
        self._lowered = [text.lower() for text in texts]
        self._digits = [re.sub(r"\D", "", text) for text in texts]
        self._claims: set[tuple[str, str, str]] = set()
        self._numbers: set[str] = set()
        for text in texts:
            self._claims.update(claim.key for claim in extract_claims(text))
            self._numbers.update(
                normal_number(match.group(0)) for match in _STANDALONE_NUMBER_RE.finditer(text)
            )
            self._read_rows(text)

    def _read_rows(self, text: str) -> None:
        """Read catalogue rows: JSON objects whose keys say what each number is.

        A plan arrives as ``{"monthly_price_usd": 15.0, "data_gb": 5, ...}``. The
        answer says "$15" and "5 GB", so the key supplies the dollar sign and the unit.
        """
        for line in text.splitlines():
            line = line.strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if isinstance(value, bool) or not isinstance(value, int | float):
                    continue
                number = normal_number(str(value))
                if _MONEY_KEY_RE.search(key):
                    self._claims.add(("money", number, ""))
                for unit in _UNITS:
                    if re.search(rf"(?:^|_){unit}(?:_|$)", key, re.IGNORECASE):
                        self._claims.add(("quantity", number, unit))

    def supports(self, claim: Claim) -> bool:
        """Is this value written in the evidence?"""
        if claim.kind == "url":
            return any(claim.value in text for text in self._lowered)
        if claim.kind == "phone":
            return any(claim.value in digits for digits in self._digits)
        if claim.kind == "code":
            return claim.value in self._numbers
        return claim.key in self._claims


def unsupported_claims(answer: str, evidence: Sequence[str]) -> list[Claim]:
    """The checkable values in ``answer`` that are not in ``evidence``, each once."""
    index = Evidence(evidence)
    seen: set[tuple[str, str, str]] = set()
    missing: list[Claim] = []
    for claim in extract_claims(answer):
        if claim.key in seen:
            continue
        seen.add(claim.key)
        if not index.supports(claim):
            missing.append(claim)
    return missing


def same_claims(first: str, second: str) -> bool:
    """Do two texts state the same set of checkable values?

    Used on a rewrite: making an answer easier to read must not change, add or
    drop a figure.
    """
    return {claim.key for claim in extract_claims(first)} == {
        claim.key for claim in extract_claims(second)
    }
