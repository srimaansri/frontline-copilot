"""PII and CPNI redaction, built on Microsoft Presidio.

Design, in order of importance:

* **Recall before precision.** A long unexplained number in a support
  transcript is far more likely to be a phone, account or device identifier than
  anything harmless, so those patterns are redacted even with no cue word nearby.
  Short or ambiguous values (four digits, a dollar amount, a usage figure) need a
  cue word, because redacting every such value would destroy the text.
* **Cue words can come from the previous turn.** "Last four of your social?" /
  "4821." is the normal shape of a verification exchange. ``redact_turns`` passes
  each turn the words of the turn before it.
* **Raw values never leave this module.** An ``Entity`` holds a type, a span and
  a placeholder, not the text it replaced.

Placeholders are numbered per transcript (``<PERSON_1>``, ``<PERSON_2>``) so a
redacted conversation stays readable.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from presidio_analyzer import (
    AnalyzerEngine,
    EntityRecognizer,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
)
from presidio_analyzer.context_aware_enhancers import LemmaContextAwareEnhancer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import EmailRecognizer, SpacyRecognizer

from copilot.luhn import luhn_valid

DEFAULT_SPACY_MODEL = "en_core_web_md"
DEFAULT_SCORE_THRESHOLD = 0.5

PII_ENTITY_TYPES: tuple[str, ...] = (
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "ADDRESS",
    "DATE_OF_BIRTH",
    "ACCOUNT_NUMBER",
    "IMEI",
    "ICCID",
    "SSN_LAST4",
    "CREDIT_CARD",
)
CPNI_ENTITY_TYPES: tuple[str, ...] = ("CPNI_AMOUNT", "CPNI_USAGE")
ALL_ENTITY_TYPES: tuple[str, ...] = PII_ENTITY_TYPES + CPNI_ENTITY_TYPES

# Words a named-entity model may tag as a person but which are not personal
# data. Callers add their own product names.
DEFAULT_ALLOW_LIST: tuple[str, ...] = ("Northline", "Northline Wireless")

# When two detections of equal score and length overlap, the earlier type wins.
_TYPE_PRIORITY: dict[str, int] = {name: rank for rank, name in enumerate(
    (
        "CREDIT_CARD",
        "ICCID",
        "IMEI",
        "EMAIL_ADDRESS",
        "ADDRESS",
        "DATE_OF_BIRTH",
        "PHONE_NUMBER",
        "ACCOUNT_NUMBER",
        "SSN_LAST4",
        "PERSON",
        "CPNI_AMOUNT",
        "CPNI_USAGE",
    )
)}  # fmt: skip

# Presidio compiles patterns with IGNORECASE by default. Capitalisation carries
# signal for names and street addresses, so every recognizer below is built with
# these flags instead, and individual patterns opt back in with (?i:...). The
# flags are a per-recognizer setting: AnalyzerEngine.analyze(regex_flags=...)
# only affects allow-list matching.
_REGEX_FLAGS = re.MULTILINE | re.DOTALL

# A turn this short is usually an answer to the previous turn ("4821." or
# "It's 4821."), so it borrows that turn's words as cue words. Longer turns
# carry their own cues, and borrowing would only add false positives.
_MAX_WORDS_FOR_BORROWED_CONTEXT = 8

_MONTH = (
    r"(?i:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_PAST_YEAR = r"(?:19\d{2}|200\d)"

# USPS street suffixes (Publication 28, primary names) and common abbreviations.
_STREET_SUFFIX = (
    r"(?:Alley|Avenue|Bend|Boulevard|Branch|Bridge|Brook|Burg|Bypass|Camp|Canyon|Cape|"
    r"Causeway|Center|Circle|Cliff|Club|Common|Corner|Course|Court|Cove|Creek|Crescent|"
    r"Crest|Crossing|Crossroad|Curve|Dale|Dam|Divide|Drive|Estate|Expressway|Extension|"
    r"Fall|Ferry|Field|Flat|Ford|Forest|Forge|Fork|Fort|Freeway|Garden|Gateway|Glen|Green|"
    r"Grove|Harbor|Haven|Height|Highway|Hill|Hollow|Inlet|Island|Isle|Junction|Key|Knoll|"
    r"Lake|Land|Landing|Lane|Light|Loaf|Lock|Lodge|Loop|Mall|Manor|Meadow|Mews|Mill|"
    r"Mission|Motorway|Mount|Mountain|Neck|Orchard|Oval|Overpass|Park|Parkway|Pass|"
    r"Passage|Path|Pike|Pine|Place|Plain|Plaza|Point|Port|Prairie|Radial|Ramp|Ranch|Rapid|"
    r"Rest|Ridge|River|Road|Route|Row|Rue|Run|Shoal|Shore|Skyway|Spring|Spur|Square|"
    r"Station|Stravenue|Stream|Street|Summit|Terrace|Throughway|Trace|Track|Trafficway|"
    r"Trail|Tunnel|Turnpike|Underpass|Union|Valley|Viaduct|View|Village|Ville|Vista|Walk|"
    r"Wall|Way|Well)s?"
    r"|(?:St|Ave|Blvd|Rd|Dr|Ln|Ct|Pl|Cir|Pkwy|Hwy|Ter|Trl)\b\.?"
)
_UNIT = r"(?:,?\s(?:Apt|Apartment|Suite|Ste|Unit|#)\.?\s?[A-Za-z0-9-]+)?"
_CITY = r"[A-Z][A-Za-z.'-]+(?:\s[A-Z][A-Za-z.'-]+){0,2}"
_STATE_ZIP = r"[A-Z]{2}\s\d{5}(?:-\d{4})?"
# A street-name word: capitalised ("Maple", "N") or a numbered street ("44th").
_STREET_WORDS = r"(?:(?:[A-Z][A-Za-z'.-]*|\d{1,3}(?:st|nd|rd|th))\s){1,4}"
_CITY_STATE_ZIP = rf"(?:,\s{_CITY},\s{_STATE_ZIP})"
_HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Dr)\b\.?"

# Card issuers by leading digits -> allowed lengths.
_CARD_RULES: tuple[tuple[re.Pattern[str], frozenset[int]], ...] = (
    (re.compile(r"4"), frozenset({13, 16, 19})),  # Visa
    (re.compile(r"5[1-5]|2[2-7]"), frozenset({16})),  # Mastercard
    (re.compile(r"3[47]"), frozenset({15})),  # American Express
    (re.compile(r"6011|65"), frozenset({16})),  # Discover
)


def _digits_only(text: str) -> str:
    return "".join(char for char in text if char.isdigit())


def _looks_like_card(digits: str) -> bool:
    return any(rule.match(digits) and len(digits) in lengths for rule, lengths in _CARD_RULES)


class _CreditCardRecognizer(PatternRecognizer):
    """A digit run is a card when it passes Luhn and fits a known issuer."""

    def validate_result(self, pattern_text: str) -> bool | None:
        digits = _digits_only(pattern_text)
        if luhn_valid(digits) and _looks_like_card(digits):
            return True
        # Not provably a card (a misheard digit breaks the checksum). The base
        # score still redacts it: a 13 to 19 digit run is sensitive either way.
        return None


class _GroupedAccountRecognizer(PatternRecognizer):
    """Digit groups read out with pauses ("6617 20984") that add up to 9 or 10 digits."""

    def validate_result(self, pattern_text: str) -> bool | None:
        # False drops the match; None keeps the pattern's base score.
        return None if len(_digits_only(pattern_text)) in {9, 10} else False


class _ImeiRecognizer(PatternRecognizer):
    """Fifteen digits that pass Luhn are an IMEI, unless they fit a card issuer."""

    def validate_result(self, pattern_text: str) -> bool | None:
        digits = _digits_only(pattern_text)
        if luhn_valid(digits) and not _looks_like_card(digits):
            return True
        return None


def _build_recognizers() -> list[EntityRecognizer]:
    phone = PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        global_regex_flags=_REGEX_FLAGS,
        name="us_phone",
        patterns=[
            Pattern(
                "formatted",
                r"(?<![\d-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\d)",
                0.75,
            ),
            # "call" is a stop word, which Presidio's cue-word boost ignores, so
            # "call you back at 4805550132" is matched directly.
            Pattern(
                "bare_ten_digits_after_call_at",
                r"(?<=(?i:\b(?:call|called|text|texted|reach|reached)\s"
                r"(?:(?:you|me|him|her|us|them)\s)?(?:back\s)?(?:at|on)\s))\d{10}(?!\d)",
                0.9,
            ),
            # Ten bare digits with no cue: still treated as a phone number.
            Pattern("bare_ten_digits", r"(?<!\d)\d{10}(?!\d)", 0.5),
        ],
        context=["phone", "call", "cell", "mobile", "reach", "text", "dial", "line"],
    )
    account = PatternRecognizer(
        supported_entity="ACCOUNT_NUMBER",
        global_regex_flags=_REGEX_FLAGS,
        name="account_number",
        patterns=[Pattern("nine_or_ten_digits", r"(?<!\d)\d{9,10}(?!\d)", 0.5)],
        context=["account", "acct", "statement"],
    )
    account_grouped = _GroupedAccountRecognizer(
        supported_entity="ACCOUNT_NUMBER",
        global_regex_flags=_REGEX_FLAGS,
        name="account_number_grouped",
        # Two or three groups. The phone pattern scores higher, so a 3-3-4
        # grouping is still labeled as a phone number.
        patterns=[
            Pattern("digit_groups", r"(?<![\d$.-])\d{2,6}(?:[ -]\d{2,6}){1,2}(?![\d-])", 0.5)
        ],
        context=["account", "acct", "statement"],
    )
    imei = _ImeiRecognizer(
        supported_entity="IMEI",
        global_regex_flags=_REGEX_FLAGS,
        name="imei",
        patterns=[
            Pattern("fifteen_digits", r"(?<!\d)\d{15}(?!\d)", 0.5),
            Pattern("grouped", r"(?<!\d)\d{2}[ -]\d{6}[ -]\d{6}[ -]\d(?!\d)", 0.5),
        ],
        context=["imei", "serial", "device"],
    )
    iccid = PatternRecognizer(
        supported_entity="ICCID",
        global_regex_flags=_REGEX_FLAGS,
        name="iccid",
        # Printed on the card in groups of four, so separators are allowed.
        patterns=[Pattern("starts_with_89", r"(?<!\d)89(?:[ -]?\d){17,18}(?!\d)", 0.9)],
        context=["sim", "iccid"],
    )
    credit_card = _CreditCardRecognizer(
        supported_entity="CREDIT_CARD",
        global_regex_flags=_REGEX_FLAGS,
        name="credit_card",
        patterns=[Pattern("digit_run", r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)", 0.5)],
        context=["card", "visa", "mastercard", "amex", "debit", "credit"],
    )
    ssn_last4 = PatternRecognizer(
        supported_entity="SSN_LAST4",
        global_regex_flags=_REGEX_FLAGS,
        name="ssn_last4",
        patterns=[Pattern("four_digits", r"(?<![\d$./-])\d{4}(?![\d/-])", 0.2)],
        context=["social", "ssn"],
    )
    date_of_birth = PatternRecognizer(
        supported_entity="DATE_OF_BIRTH",
        global_regex_flags=_REGEX_FLAGS,
        name="date_of_birth",
        patterns=[
            # A full date in a past year is treated as a birth date without a cue.
            Pattern(
                "numeric_past_year",
                rf"(?<![\d/-])\d{{1,2}}[/-]\d{{1,2}}[/-]{_PAST_YEAR}(?![\d/-])",
                0.6,
            ),
            Pattern(
                "text_past_year",
                rf"\b{_MONTH}\.?\s\d{{1,2}}(?:st|nd|rd|th)?,?\s{_PAST_YEAR}(?!\d)",
                0.6,
            ),
            Pattern("iso_past_year", rf"(?<!\d){_PAST_YEAR}-\d{{2}}-\d{{2}}(?!\d)", 0.6),
            # Any other date needs a cue such as "born" or "date of birth".
            Pattern(
                "numeric_any",
                r"(?<![\d/-])\d{1,2}[/-]\d{1,2}[/-]\d{2}(?:\d{2})?(?![\d/-])",
                0.3,
            ),
            Pattern("text_any", rf"\b{_MONTH}\.?\s\d{{1,2}}(?:st|nd|rd|th)?,?\s\d{{4}}(?!\d)", 0.3),
        ],
        context=["birth", "born", "birthday", "birthdate", "dob"],
    )
    address = PatternRecognizer(
        supported_entity="ADDRESS",
        global_regex_flags=_REGEX_FLAGS,
        name="us_street_address",
        patterns=[
            Pattern(
                "po_box",
                rf"(?i:P\.?\s?O\.?\sBox)\s\d{{1,6}}{_CITY_STATE_ZIP}?",
                0.85,
            ),
            Pattern(
                "rural_route_box",
                rf"(?:Rural\sRoute|RR|HC)\s\d{{1,4}},?\sBox\s\d{{1,6}}{_CITY_STATE_ZIP}?",
                0.85,
            ),
            Pattern(
                "street_city_state_zip",
                rf"(?<![\d$])\d{{1,6}}\s{_STREET_WORDS}?[A-Z][A-Za-z'.-]*{_UNIT},\s{_CITY},\s"
                rf"{_STATE_ZIP}",
                0.85,
            ),
            Pattern(
                "street_with_suffix",
                rf"(?<![\d$])\d{{1,6}}\s{_STREET_WORDS}(?:{_STREET_SUFFIX}){_UNIT}"
                rf"(?:,\s{_CITY}(?:,\s{_STATE_ZIP})?)?",
                0.7,
            ),
            # Number plus capitalised words: an address only next to a cue word.
            Pattern(
                "number_and_capitalised_words",
                rf"(?<![\d$])\d{{1,6}}\s[A-Z][a-z'.-]+(?:\s[A-Z][a-z'.-]+){{0,3}}{_UNIT}"
                rf"(?:,\s{_CITY})?",
                0.3,
            ),
        ],
        context=["address", "live", "mail", "send", "ship", "residence", "street"],
    )
    person_cue = PatternRecognizer(
        supported_entity="PERSON",
        global_regex_flags=_REGEX_FLAGS,
        name="person_after_cue",
        patterns=[
            Pattern(
                "capitalised_after_cue",
                r"(?<=(?i:\bmy name is|\bname is|\bname's|\bthis is|\bspeaking with|"
                r"\bchatting with|\bi am|\bi'm)\s)"
                r"[A-Z][a-z]+(?:[ ][A-Z][a-z'-]+){0,2}",
                0.7,
            ),
            # "It's Google" is as likely as "It's Linda", so this one needs a cue
            # such as a preceding "may I have your name?".
            Pattern(
                "capitalised_after_its",
                r"(?<=(?i:\bit's|\bit is)\s)[A-Z][a-z]+(?:[ ][A-Z][a-z'-]+){0,2}",
                0.3,
            ),
            Pattern(
                "after_greeting",
                r"(?<=(?i:\bhi|\bhello|\bhey|\bthanks|\bthank you|\bof course),?\s)"
                r"(?!There\b|Again\b|Everyone\b)[A-Z][a-z]+(?=[.,!?]|\s*$)",
                0.7,
            ),
            # "You're all set, Linda." A capitalised word between a comma and the
            # end of a sentence is usually the person being addressed.
            Pattern("closing_vocative", r"(?<=,\s)[A-Z][a-z]+(?=[.!?](?:\s|$))", 0.55),
            Pattern("before_speaking", r"\b[A-Z][a-z]+(?=\sspeaking\b)", 0.7),
            # "Mr. Okafor", "Mrs Whitfield". Scores above the named-entity model
            # so the title and the name stay one span.
            Pattern(
                "honorific_and_name",
                rf"\b{_HONORIFIC}\s[A-Z][a-z'-]+(?:\s[A-Z][a-z'-]+)?",
                0.9,
            ),
            # Chat users often type their name in lower case.
            Pattern(
                "any_case_after_strong_cue",
                r"(?<=(?i:\bmy name is|\bname's)\s)"
                r"(?!(?:on|in|not|the|a|an|spelled|listed|under)\b)"
                r"[A-Za-z]+(?:[ ][A-Za-z'-]+)?",
                0.6,
            ),
            # A turn that is nothing but a name, answering "may I have your name?".
            Pattern(
                "whole_turn_name",
                r"^[A-Z][a-z]+(?:[ ][A-Z][a-z'-]+){1,2}(?=[.!]?$)",
                0.3,
            ),
        ],
        context=["name", "speaking", "chatting"],
    )
    cpni_amount = PatternRecognizer(
        supported_entity="CPNI_AMOUNT",
        global_regex_flags=_REGEX_FLAGS,
        name="cpni_amount",
        patterns=[
            Pattern(
                "dollar_amount_not_a_rate",
                r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?!\d)(?!\.\d)"
                r"(?!\s?(?:/\s?|per\s|a\s|each\s)(?:mo\b|month|day|line|year))",
                0.3,
            )
        ],
        context=["bill", "balance", "owe", "due", "charge", "statement", "total"],
    )
    quantity = (
        r"\d{1,4}(?:[.,]\d{1,3})?\s?"
        r"(?i:minutes|mins|gigabytes|gigs|gb|megabytes|mb|texts|messages|calls)\b"
    )
    cpni_usage = PatternRecognizer(
        supported_entity="CPNI_USAGE",
        global_regex_flags=_REGEX_FLAGS,
        name="cpni_usage",
        patterns=[
            # "used" and "made" are stop words, which Presidio's cue-word boost
            # ignores, so the verb is matched directly.
            Pattern(
                "quantity_after_usage_verb",
                r"(?<=(?i:\b(?:used|use|using|made|sent|went\sover)\s"
                r"(?:about\s|around\s|up\s|over\s|by\s|like\s)?))" + quantity,
                0.6,
            ),
            Pattern(
                "quantity_with_unit",
                r"(?<![\d.$])"
                + quantity
                # A quantity that is priced or described as part of a plan is a
                # product attribute, not someone's usage.
                + r"(?!\s(?:for\s\$|in\s(?:your|the)\splan|included))",
                0.3,
            ),
        ],
        context=["usage", "consume"],
    )
    return [
        SpacyRecognizer(supported_entities=["PERSON"]),
        EmailRecognizer(),
        phone,
        account,
        account_grouped,
        imei,
        iccid,
        credit_card,
        ssn_last4,
        date_of_birth,
        address,
        person_cue,
        cpni_amount,
        cpni_usage,
    ]


@dataclass(frozen=True)
class Entity:
    """One redacted value. Offsets refer to the original, unredacted text."""

    entity_type: str
    start: int
    end: int
    score: float
    placeholder: str


@dataclass(frozen=True)
class RedactionResult:
    """Redacted text and what was replaced."""

    text: str
    entities: tuple[Entity, ...]

    @property
    def entity_counts(self) -> dict[str, int]:
        """Number of redacted values per entity type."""
        return dict(Counter(entity.entity_type for entity in self.entities))


class PlaceholderMap:
    """Gives the same value the same numbered placeholder within one transcript."""

    def __init__(self) -> None:
        """Start with no values seen."""
        self._seen: dict[str, dict[str, int]] = {}

    def placeholder(self, entity_type: str, raw: str) -> str:
        """Return the placeholder for ``raw``, allocating a new number if needed."""
        known = self._seen.setdefault(entity_type, {})
        key = self._key(entity_type, raw)
        number = known.get(key)
        if number is None and entity_type == "PERSON":
            number = self._same_person(known, key)
        if number is None:
            number = max(known.values(), default=0) + 1
        known[key] = number
        return f"<{entity_type}_{number}>"

    @staticmethod
    def _key(entity_type: str, raw: str) -> str:
        if entity_type in {"PERSON", "EMAIL_ADDRESS", "ADDRESS", "DATE_OF_BIRTH"}:
            return " ".join(raw.lower().split())
        return _digits_only(raw) or raw.lower()

    @staticmethod
    def _same_person(known: dict[str, int], key: str) -> int | None:
        """Treat "Linda" and "Linda Garcia" as one person."""
        tokens = set(key.split())
        for other, number in known.items():
            other_tokens = set(other.split())
            if tokens <= other_tokens or other_tokens <= tokens:
                return number
        return None


@dataclass(frozen=True)
class _Detection:
    entity_type: str
    start: int
    end: int
    score: float


def _resolve_overlaps(detections: Iterable[_Detection]) -> list[_Detection]:
    """Keep the best detection wherever several overlap."""
    ranked = sorted(
        detections,
        key=lambda d: (-d.score, -(d.end - d.start), _TYPE_PRIORITY.get(d.entity_type, 99)),
    )
    kept: list[_Detection] = []
    for candidate in ranked:
        if all(candidate.end <= other.start or candidate.start >= other.end for other in kept):
            kept.append(candidate)
    return sorted(kept, key=lambda d: d.start)


_GREETING_RE = re.compile(r"(?:hello|hi|hey|dear|thanks|thank you),?\s+", re.IGNORECASE)


def _trim_greeting(detection: _Detection, text: str) -> _Detection:
    """Drop a leading greeting that a named-entity model folded into a name.

    spaCy sometimes tags "Hello Angel" as one person. Keeping the greeting in
    the span would redact a harmless word and misplace the entity boundary.
    """
    if detection.entity_type != "PERSON":
        return detection
    match = _GREETING_RE.match(text, detection.start, detection.end)
    if match is None or match.end() >= detection.end:
        return detection
    return _Detection(detection.entity_type, match.end(), detection.end, detection.score)


_WORD_RE = re.compile(r"[a-z']+")


def _context_words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


class Redactor:
    """Detects and replaces PII and CPNI. Building one loads a spaCy model, so reuse it."""

    def __init__(
        self,
        spacy_model: str = DEFAULT_SPACY_MODEL,
        *,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        allow_list: Sequence[str] = DEFAULT_ALLOW_LIST,
    ) -> None:
        """Load the spaCy model and register the recognizers.

        Args:
            spacy_model: Name of an installed spaCy English pipeline.
            score_threshold: Detections scoring below this are dropped.
            allow_list: Exact strings that are never treated as personal data.
        """
        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": spacy_model}],
            }
        ).create_engine()
        registry = RecognizerRegistry(supported_languages=["en"])
        for recognizer in _build_recognizers():
            registry.add_recognizer(recognizer)
        self._analyzer = AnalyzerEngine(
            registry=registry,
            nlp_engine=nlp_engine,
            supported_languages=["en"],
            default_score_threshold=score_threshold,
            context_aware_enhancer=LemmaContextAwareEnhancer(
                context_prefix_count=5, context_suffix_count=3
            ),
        )
        self._allow_list = list(allow_list)
        self.spacy_model = spacy_model
        self.score_threshold = score_threshold

    def _detect(self, text: str, context: Sequence[str]) -> list[_Detection]:
        if not text.strip():
            return []
        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=list(ALL_ENTITY_TYPES),
            context=list(context) or None,
            allow_list=self._allow_list,
        )
        return _resolve_overlaps(
            _trim_greeting(
                _Detection(result.entity_type, result.start, result.end, float(result.score)),
                text,
            )
            for result in results
        )

    def redact(
        self,
        text: str,
        *,
        context: Sequence[str] = (),
        placeholders: PlaceholderMap | None = None,
    ) -> RedactionResult:
        """Replace every detected value in ``text`` with a typed placeholder.

        Args:
            text: The text to redact.
            context: Extra cue words, usually the words of the previous turn.
            placeholders: Shared numbering for a transcript. A fresh map is used if omitted.

        Returns:
            The redacted text and the entities that were replaced.
        """
        mapping = placeholders if placeholders is not None else PlaceholderMap()
        pieces: list[str] = []
        entities: list[Entity] = []
        cursor = 0
        for detection in self._detect(text, context):
            placeholder = mapping.placeholder(
                detection.entity_type, text[detection.start : detection.end]
            )
            pieces.append(text[cursor : detection.start])
            pieces.append(placeholder)
            cursor = detection.end
            entities.append(
                Entity(
                    detection.entity_type,
                    detection.start,
                    detection.end,
                    detection.score,
                    placeholder,
                )
            )
        pieces.append(text[cursor:])
        return RedactionResult("".join(pieces), tuple(entities))

    def redact_turns(self, turns: Sequence[str]) -> list[RedactionResult]:
        """Redact a conversation, turn by turn.

        A short turn borrows the previous turn's words as cue words, and
        placeholder numbers are shared across the whole conversation.
        """
        mapping = PlaceholderMap()
        results: list[RedactionResult] = []
        previous: list[str] = []
        for turn in turns:
            words = _context_words(turn)
            borrowed = previous if len(words) <= _MAX_WORDS_FOR_BORROWED_CONTEXT else []
            results.append(self.redact(turn, context=borrowed, placeholders=mapping))
            previous = words
        return results


@lru_cache(maxsize=2)
def get_redactor(spacy_model: str = DEFAULT_SPACY_MODEL) -> Redactor:
    """Return a shared ``Redactor`` for ``spacy_model``, building it on first use."""
    return Redactor(spacy_model)


def redact(text: str) -> RedactionResult:
    """Redact a single piece of text with the default redactor."""
    return get_redactor().redact(text)
