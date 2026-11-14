"""Checks applied to what goes into and comes out of the model.

Milestone 3 has two: redacting the agent's question before anything is traced,
and validating the citations in an answer. Intent and injection checks, the
reading-level rewrite and output redaction arrive with the agent in Milestone 4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from copilot.redaction import Redactor
from copilot.text import to_plain_punctuation

FLAG_PII_IN_QUESTION = "pii_in_question"
FLAG_INVALID_CITATION = "invalid_citation_removed"
FLAG_NO_CITATION = "no_citation"

# Matches [1], [2, 3] and [1][2].
_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# Some models write a citation as [1+source] or [1+L3-L7], with a dagger where the
# plus is. Anything after the number, up to the closing bracket, is dropped.
_DECORATED_CITATION_RE = re.compile(r"\[(\d+)[^\]\d,][^\]]*\]")


@dataclass(frozen=True)
class RedactedInput:
    """A question with personal data replaced, and what was found."""

    text: str
    flags: tuple[str, ...]


def redact_question(question: str, redactor: Redactor) -> RedactedInput:
    """Replace personal data in the agent's question with placeholders.

    This must run before the question reaches any traced function: MLflow
    records a traced function's inputs before its body runs.
    """
    result = redactor.redact(question)
    flags = tuple(
        f"{FLAG_PII_IN_QUESTION}:{entity_type}" for entity_type in sorted(result.entity_counts)
    )
    return RedactedInput(result.text, flags)


@dataclass(frozen=True)
class CheckedCitations:
    """An answer with only valid citation markers left in it."""

    text: str
    cited: tuple[int, ...]
    flags: tuple[str, ...]


def check_citations(answer: str, source_count: int) -> CheckedCitations:
    """Remove citation numbers that do not refer to a retrieved source.

    Args:
        answer: The model's answer, with ``[n]`` markers.
        source_count: How many sources were given to the model, numbered from 1.

    Returns:
        The cleaned answer, the valid source numbers in order of first use, and
        flags saying whether anything was removed or nothing was cited at all.
        Typographic punctuation in the answer is replaced with plain ASCII.
    """
    cited: list[int] = []
    removed = False

    def keep_valid(match: re.Match[str]) -> str:
        nonlocal removed
        numbers = [int(part) for part in match.group(1).split(",")]
        valid = [number for number in numbers if 1 <= number <= source_count]
        removed = removed or len(valid) != len(numbers)
        for number in valid:
            if number not in cited:
                cited.append(number)
        return "[" + ", ".join(str(number) for number in valid) + "]" if valid else ""

    # Bring every citation style the model uses to the plain [n] form first.
    answer = _DECORATED_CITATION_RE.sub(r"[\1]", to_plain_punctuation(answer))
    text = _CITATION_RE.sub(keep_valid, answer)
    # Removing a marker can leave a space before punctuation or a doubled space.
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    flags: list[str] = []
    if removed:
        flags.append(FLAG_INVALID_CITATION)
    if not cited:
        flags.append(FLAG_NO_CITATION)
    return CheckedCitations(text, tuple(cited), tuple(flags))
