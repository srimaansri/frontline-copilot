"""Punctuation normalisation."""

from copilot.text import to_plain_punctuation


def test_typographic_punctuation_is_replaced() -> None:
    raw = (
        f"1{chr(0x2011)}800 {chr(0x2014)} it{chr(0x2019)}s {chr(0x201C)}free{chr(0x201D)}"
        f"{chr(0x2026)} Settings {chr(0x2192)} Display{chr(0x00A0)}now {chr(0x3010)}1{chr(0x3011)}"
    )

    assert to_plain_punctuation(raw) == '1-800  -  it\'s "free"... Settings -> Display now [1]'


def test_plain_text_is_unchanged() -> None:
    text = "Dial 611 from your phone. It's free [1]."

    assert to_plain_punctuation(text) == text
