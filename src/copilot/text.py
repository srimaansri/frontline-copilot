"""Small text helpers shared by the data generators and the copilot."""

from __future__ import annotations

# Language models like typographic punctuation. A phone number written with
# non-breaking hyphens no longer matches a keyword search for it, and cannot be
# pasted into a dialer, so model output is mapped to plain ASCII punctuation.
# Keyed by code point so this source file stays plain ASCII too.
_PLAIN_PUNCTUATION: dict[int, str] = {
    0x2010: "-",  # hyphen
    0x2011: "-",  # non-breaking hyphen
    0x2012: "-",  # figure dash
    0x2013: "-",  # en dash
    0x2014: " - ",  # em dash
    0x2018: "'",  # left single quote
    0x2019: "'",  # right single quote
    0x201C: '"',  # left double quote
    0x201D: '"',  # right double quote
    0x2026: "...",  # ellipsis
    0x2192: "->",  # rightwards arrow
    0x00A0: " ",  # no-break space
    0x202F: " ",  # narrow no-break space
    0x2009: " ",  # thin space
    0x3010: "[",  # left black lenticular bracket, used by some models for citations
    0x3011: "]",  # right black lenticular bracket
}


def to_plain_punctuation(text: str) -> str:
    """Replace typographic punctuation with its plain ASCII equivalent."""
    return text.translate(_PLAIN_PUNCTUATION)
