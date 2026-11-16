"""Checks applied to what goes into and comes out of the model.

On the way in: personal data is redacted before anything is traced, then the
redacted question is checked for a request to act on a customer's account and
for an attempt to override the copilot's instructions.

On the way out: an answer that is too hard to read is rewritten once, its
citations are validated, and personal data is removed from it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from copilot.claims import same_claims, unsupported_claims
from copilot.readability import reading_grade
from copilot.redaction import PlaceholderMap, Redactor
from copilot.text import to_plain_punctuation

FLAG_PII_IN_QUESTION = "pii_in_question"
FLAG_INVALID_CITATION = "invalid_citation_removed"
FLAG_NO_CITATION = "no_citation"
FLAG_ACCOUNT_ACTION = "account_action_requested"
FLAG_INJECTION = "injection_suspected"
FLAG_SIMPLIFIED = "answer_simplified"
FLAG_PII_IN_ANSWER = "pii_removed_from_answer"
# The model router could not be reached or read, so the rules decided.
FLAG_ROUTER_FALLBACK = "router_unavailable"
# A figure in the answer that is in none of the text the copilot was given.
FLAG_UNSUPPORTED_CLAIM = "unsupported_claim"
# A plainer rewrite was thrown away because it changed, dropped or added a figure.
FLAG_REWRITE_CHANGED_FACTS = "rewrite_changed_facts"

# An answer is rewritten only when it is well above the target grade, so that
# an answer a little over the line is not sent round the model a second time.
REWRITE_MARGIN = 2.0

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


FLAG_HISTORY_DROPPED = "history_turn_dropped"
# How much of a conversation the model is given: the last six exchanges.
MAX_HISTORY_TURNS = 12
MAX_HISTORY_TURN_CHARS = 2000


@dataclass(frozen=True)
class SafeConversation:
    """A question and the turns before it, ready to be traced and sent to the model."""

    question: str
    # (role, text) pairs, oldest first. The role is "user" or "assistant".
    history: tuple[tuple[str, str], ...]
    flags: tuple[str, ...]


def redact_conversation(
    question: str, history: Sequence[Mapping[str, str]], redactor: Redactor
) -> SafeConversation:
    """Redact a question together with the conversation it continues.

    The earlier turns come from the caller, so they are treated like the
    question itself, not like something the copilot said:

    - One placeholder map is used for the whole conversation, so ``<PERSON_1>``
      means the same person in every turn. Redacting each turn alone would give
      two different people the same placeholder.
    - A short turn is redacted with the turn before it as context, as a
      transcript is. "4821." alone is a number; after "the last four of the
      social?" it is part of a Social Security number. This applies to the
      question as well, which is often a short reply to the turn before.
    - A turn that tries to override the instructions is left out, with the reply
      that followed it. The check on the question alone would miss it.
    - Citation markers are removed from earlier answers. Source numbers start
      again at 1 with every answer, so an old ``[1]`` would point at a new source.
    - Only the last ``MAX_HISTORY_TURNS`` turns are kept, each cut to
      ``MAX_HISTORY_TURN_CHARS`` after it is redacted. Cutting first could split
      a phone number and leave half of it undetected.

    Like ``redact_question``, this must run before anything is traced.
    """
    placeholders = PlaceholderMap()
    kept: list[tuple[str, str]] = []
    dropped = False
    skip_reply = False
    turns = list(history)
    # The turn just before the ones that are kept still supplies context to the first of them.
    earlier = turns[: -MAX_HISTORY_TURNS or None][-1:] if len(turns) > MAX_HISTORY_TURNS else []
    previous = earlier[0].get("content", "") if earlier else ""
    for turn in turns[-MAX_HISTORY_TURNS:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        said = turn.get("content", "")
        text = redactor.redact_after(said, previous, placeholders).text
        previous = said
        if role == "assistant":
            if skip_reply:
                skip_reply = False
                continue
            text = _CITATION_RE.sub("", _DECORATED_CITATION_RE.sub("", text))
            text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
        skip_reply = False
        if is_override_attempt(text):
            dropped = True
            skip_reply = role == "user"
            continue
        text = text.strip()[:MAX_HISTORY_TURN_CHARS]
        if text:
            kept.append((role, text))
    result = redactor.redact_after(question, previous, placeholders)
    flags = [
        f"{FLAG_PII_IN_QUESTION}:{entity_type}" for entity_type in sorted(result.entity_counts)
    ]
    if dropped:
        flags.append(FLAG_HISTORY_DROPPED)
    return SafeConversation(result.text, tuple(kept), tuple(flags))


# --- input: what is the agent asking for? -------------------------------------------------

Route = Literal["agent", "escalate", "refuse"]

# A request to do something, as opposed to a question about how something is done.
# It may open the message or follow an earlier sentence ("She is upset. Waive the fee ...").
_ACTION_VERB_RE = re.compile(
    r"(?:^|[.!?;:]\s+|\n)\s*(?:please\s+)?"
    r"(?:can you\s+|could you\s+|go ahead and\s+|i need you to\s+)?"
    r"(change|switch|move|upgrade|downgrade|refund|credit|waive|remove|cancel|close|suspend|"
    r"unsuspend|restore|reset|unlock|unblock|block|activate|deactivate|add|apply|update|port|"
    r"transfer|issue|process)\b",
    re.IGNORECASE,
)
# The request is about one particular customer, not customers in general.
_THIS_ACCOUNT_RE = re.compile(
    r"\b(?:this|that)\s+(?:customer|caller|account|line|bill)\b"
    r"|\b(?:this|that|the)\s+(?:customer|caller)'s\b"
    r"|\bon\s+(?:this|their|his|her)\s+account\b",
    re.IGNORECASE,
)
# One customer named by a pronoun: "waive the fee for her", "change his plan". This only
# counts next to a request to act. In a question, "their" is usually customers in general
# ("how do customers check their balance?").
_PRONOUN_ACCOUNT_RE = re.compile(
    r"\bfor\s+(?:him|her|them)\b"
    r"|\b(?:his|her|their)\s+(?:account|line|bill|plan|phone|number|fee|charge|service)\b",
    re.IGNORECASE,
)
# Details only an account system holds. "Use" and "minutes" alone are not on the list:
# "how much data can this customer use on the Plus plan?" is a question about the plan.
_ACCOUNT_DATA_RE = re.compile(
    r"\b(?:pin|password|passcode|usage|used|balance|owes?|owed|address|card number|"
    r"payment history|call log|call history|last payment|"
    r"minutes\s+(?:used|left|remaining))\b"
    r"|\bdid\s+(?:this|that|the)\s+(?:customer|caller)\s+use\b",
    re.IGNORECASE,
)
# A question about how something is done. It is answered from the help articles even when
# it mentions one customer: "this customer forgot their PIN, how do they reset it?"
_HOW_TO_RE = re.compile(
    r"\bhow\s+(?:do|does|can|could|should|would|to)\b"
    r"|\bwhat\s+(?:are|is)\s+the\s+steps?\b|\bsteps\s+to\b|\bis\s+there\s+a\s+way\b",
    re.IGNORECASE,
)
# An attempt to override the copilot's instructions. Each pattern needs the words to be
# aimed at the copilot ("your rules", "the instructions you were given"). Words that are
# only mentioned are not enough: "show me the rules for roaming", "the phone shows a
# system message" and "should the customer ignore the instructions in that text?" are
# support questions, and the first version of these patterns refused all three.
_OVERRIDE_VERBS = r"(?:ignore|disregard|forget|override)"
_YOUR_RULES = r"(?:instructions?|rules?|prompts?|guidelines?)"
_INJECTION_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\b{_OVERRIDE_VERBS}\s+(?:(?:all|any|every)\s+(?:of\s+)?)?"
        r"(?:(?:your|my|previous|prior|earlier|above|these|those|system|"
        r"the\s+(?:above|previous|prior|earlier|system))\s+){1,3}"
        rf"(?:\w+\s+){{0,2}}?{_YOUR_RULES}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b{_OVERRIDE_VERBS}\s+(?:all|any|every)\s+(?:\w+\s+){{0,2}}?{_YOUR_RULES}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b{_OVERRIDE_VERBS}\s+(?:the\s+)?{_YOUR_RULES}\s+"
        r"(?:above|so far|you\s+(?:were|are|have|follow))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:system|developer|hidden)\s+prompt\b"
        r"|\b(?:developer|hidden)\s+(?:message|instructions?)\b"
        r"|\byour\s+(?:system|initial|original)\s+(?:message|instructions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|print|show|repeat|output|tell me|what are)\b.{0,30}"
        rf"(?:\byour\s+{_YOUR_RULES}\b"
        rf"|\bthe\s+{_YOUR_RULES}\s+(?:above|you\s+(?:were|are|have|follow))\b)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\byou(?:'re|\s+are)\s+now\b.{0,30}"
        r"\b(?:mode|no longer|unrestricted|free of|free from|a different|"
        r"an?\s+(?:ai|assistant|bot|model))\b"
        r"|\byou(?:'re|\s+are)\b.{0,20}\bdeveloper mode\b"
        r"|\bjailbreak\s+(?:you|yourself|this\s+(?:bot|assistant|ai|copilot))\b",
        re.IGNORECASE,
    ),
)
# Checked in order; the first match names the kind of hand-off.
_CATEGORY_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("account_access", re.compile(r"\b(?:pin|password|passcode)\b", re.IGNORECASE)),
    # Before "usage", so "unlock the phone so they can use it" is a device request.
    ("device", re.compile(r"\b(?:unlock|unblock|imei)\b", re.IGNORECASE)),
    ("usage", re.compile(r"\b(?:usage|used?|minutes|call log|call history)\b", re.IGNORECASE)),
    ("cancellation", re.compile(r"\b(?:cancel|close)\b", re.IGNORECASE)),
    ("billing", re.compile(r"\b(?:refund|credit|waive|fee|bill|charge|payment)\b", re.IGNORECASE)),
    ("device", re.compile(r"\b(?:unlock|unblock|block|imei|phone|device|sim)\b", re.IGNORECASE)),
    (
        "plan_change",
        re.compile(r"\b(?:plan|upgrade|downgrade|switch|add-on|line)\b", re.IGNORECASE),
    ),
)
# What the copilot says it cannot do, by kind of request.
CANNOT_DO: dict[str, str] = {
    "account_access": "I can't give out a transfer PIN, a password or any other account secret.",
    "usage": "I can't see a specific customer's usage or any other account details.",
    "cancellation": "I can't cancel or close an account myself.",
    "billing": "I can't refund, credit or waive a charge myself.",
    "device": "I can't unlock, block or change a customer's device myself.",
    "plan_change": "I can't change a customer's plan myself.",
    "other": "I can't see or change a customer's account myself.",
}
REFUSAL_ANSWER = (
    "I can't help with that. I can answer Northline support questions, look up plans, "
    "and summarize a call."
)


@dataclass(frozen=True)
class InputCheck:
    """Where a question should go, and why.

    ``route`` is ``escalate`` for a request to act on, or read from, one
    customer's account; ``refuse`` for an attempt to override the copilot's
    instructions; and ``agent`` for everything else. ``category`` names the
    kind of account request and is ``other`` when there is none.
    """

    route: Route
    flags: tuple[str, ...]
    category: str = "other"


def is_override_attempt(text: str) -> bool:
    """Does the text try to change, or read out, the copilot's instructions?"""
    return any(pattern.search(text) for pattern in _INJECTION_RES)


def check_input(text: str) -> InputCheck:
    """Decide where an already-redacted question goes.

    These are plain rules so they behave the same every time and cost nothing.
    They catch the clear cases; the model can still call the hand-off tool
    itself for a request the rules do not recognise.
    """
    if is_override_attempt(text):
        return InputCheck("refuse", (FLAG_INJECTION,))
    about_this_account = bool(_THIS_ACCOUNT_RE.search(text))
    wants_action = bool(_ACTION_VERB_RE.search(text)) and (
        about_this_account or bool(_PRONOUN_ACCOUNT_RE.search(text))
    )
    wants_account_data = (
        about_this_account and bool(_ACCOUNT_DATA_RE.search(text)) and not _HOW_TO_RE.search(text)
    )
    if wants_action or wants_account_data:
        category = next((name for name, pattern in _CATEGORY_RES if pattern.search(text)), "other")
        return InputCheck("escalate", (FLAG_ACCOUNT_ACTION,), category)
    return InputCheck("agent", ())


# --- output: citations ----------------------------------------------------------------------


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


# --- output: personal data --------------------------------------------------------------------


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def appears_in_sources(value: str, sources: Sequence[str]) -> bool:
    """Is ``value`` written out in the text the copilot was given to answer from?

    A phone number counts as the same number however it is punctuated, so
    "1-800-555-0199" in an answer matches "1 (800) 555-0199" in an article.
    """
    needle = " ".join(value.lower().split())
    if not needle:
        return False
    digits = _digits(value)
    for source in sources:
        if needle in " ".join(source.lower().split()):
            return True
        if len(digits) >= 7 and digits in _digits(source):
            return True
    return False


@dataclass(frozen=True)
class RedactedAnswer:
    """An answer with personal data removed, and the kinds of data that were removed."""

    text: str
    removed: tuple[str, ...]


def redact_answer(answer: str, redactor: Redactor, sources: Sequence[str]) -> RedactedAnswer:
    """Remove personal data from an answer, keeping what the sources state openly.

    The support phone number, a price or a web address that is written in a
    help article or a catalogue row is public information the answer is meant
    to contain. Anything else the redactor finds is replaced with a placeholder.
    """
    result = redactor.redact(answer)
    pieces: list[str] = []
    removed: list[str] = []
    cursor = 0
    for entity in result.entities:
        value = answer[entity.start : entity.end]
        pieces.append(answer[cursor : entity.start])
        if appears_in_sources(value, sources):
            pieces.append(value)
        else:
            pieces.append(entity.placeholder)
            removed.append(entity.entity_type)
        cursor = entity.end
    pieces.append(answer[cursor:])
    return RedactedAnswer("".join(pieces), tuple(sorted(set(removed))))


# --- output: the whole check --------------------------------------------------------------------


@dataclass(frozen=True)
class CheckedAnswer:
    """An answer that has passed every output check."""

    text: str
    cited: tuple[int, ...]
    flags: tuple[str, ...]


def check_output(
    answer: str,
    *,
    source_count: int,
    redactor: Redactor,
    sources: Sequence[str],
    target_grade: float,
    simplify: Callable[[str], str] | None = None,
    evidence: Sequence[str] | None = None,
) -> CheckedAnswer:
    """Run the output checks in the order that keeps each one valid.

    1. Reading level. An answer more than ``REWRITE_MARGIN`` grades above the
       target is rewritten once by ``simplify``. The rewrite is kept only if it
       is easier to read and states the same figures as the draft.
    2. Citations, after the rewrite, because a rewrite can drop or renumber them.
    3. Personal data, so nothing a rewrite adds is missed.
    4. Figures, last, on the text the agent will see: every price, amount, phone
       number and web address must be in ``evidence``. One that is not is
       flagged by kind. The answer is not changed: how often this check is
       wrong is measured before it is allowed to block anything.

    Args:
        answer: The model's answer.
        source_count: How many numbered sources the model was given.
        redactor: The redactor used on questions and transcripts.
        sources: The text the answer was written from: retrieved chunks and tool results.
        target_grade: The reading grade answers should be at or below.
        simplify: Rewrites an answer in plainer language. None skips the rewrite.
        evidence: Everything the answer may take a figure from: the sources and the
            conversation. None skips the check on figures.
    """
    flags: list[str] = []
    text = answer
    if simplify is not None and text.strip():
        grade = reading_grade(text)
        if grade > target_grade + REWRITE_MARGIN:
            rewritten = simplify(text).strip()
            if rewritten and reading_grade(rewritten) < grade:
                if same_claims(text, rewritten):
                    text = rewritten
                    flags.append(FLAG_SIMPLIFIED)
                else:
                    flags.append(FLAG_REWRITE_CHANGED_FACTS)
    citations = check_citations(text, source_count)
    flags.extend(citations.flags)
    redacted = redact_answer(citations.text, redactor, sources)
    flags.extend(f"{FLAG_PII_IN_ANSWER}:{entity_type}" for entity_type in redacted.removed)
    if evidence is not None:
        kinds = sorted({claim.kind for claim in unsupported_claims(redacted.text, evidence)})
        flags.extend(f"{FLAG_UNSUPPORTED_CLAIM}:{kind}" for kind in kinds)
    return CheckedAnswer(redacted.text, citations.cited, tuple(flags))
