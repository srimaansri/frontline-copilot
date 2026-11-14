"""How hard an answer is to read.

Used by the output guardrail, which rewrites an answer that is too hard, and by
the evaluation, which reports the grade of every answer.
"""

from __future__ import annotations

import re

import textstat

_CITATION_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_MARKDOWN_RE = re.compile(r"[*_`#>]+")
_LIST_MARKER_RE = re.compile(r"^[ \t]*(?:\d+[.)]|[-*])[ \t]+", re.MULTILINE)


def plain_text_for_reading_level(answer: str) -> str:
    """Strip citation markers and Markdown so they do not distort the reading grade."""
    text = _CITATION_RE.sub("", answer)
    text = _LIST_MARKER_RE.sub("", text)
    text = _MARKDOWN_RE.sub("", text)
    # Removing a citation leaves a space before the punctuation that followed it.
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def reading_grade(answer: str) -> float:
    """Flesch-Kincaid grade of an answer. Lower is easier to read."""
    text = plain_text_for_reading_level(answer)
    return float(textstat.flesch_kincaid_grade(text)) if text else 0.0
