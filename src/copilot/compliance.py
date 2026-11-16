"""Check a redacted call for a small set of rule breaches.

The input is a call as the silver table holds it: a list of turns, each with a
speaker (``agent`` or ``customer``) and text in which personal data has already
been replaced by typed placeholders such as ``<CREDIT_CARD_1>``. Nothing here
reads unredacted text and nothing here calls a model.

Most of the work is done by what the redactor has already decided and by the
order of the turns:

* a ``<CREDIT_CARD_n>`` placeholder in an agent turn is a card number read back;
* a ``<CPNI_AMOUNT_n>`` in an agent turn before any identity question has been
  answered is a bill amount disclosed before verification;
* a call with no answered identity question in which the agent states account
  details or changes something is a call where verification was skipped.

Two rules have no placeholder to lean on and are matched on wording: an agent
who says they waived, refunded or credited a charge themselves, and an agent
who asks for a full Social Security number. Wording rules miss phrasings nobody
thought of. ``eval/compliance_eval.py`` measures how often.

A finding is a reason for a supervisor to open the call. It is not a verdict.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

RULE_DISCLOSURE = "disclosure_before_verification"
RULE_SKIPPED = "verification_skipped"
RULE_CARD_READ_BACK = "card_read_back"
RULE_PROMISE = "unauthorized_promise"
RULE_FULL_SSN = "full_ssn_requested"
RULES: tuple[str, ...] = (
    RULE_DISCLOSURE,
    RULE_SKIPPED,
    RULE_CARD_READ_BACK,
    RULE_PROMISE,
    RULE_FULL_SSN,
)

AGENT = "agent"
CUSTOMER = "customer"

_FLAGS = re.IGNORECASE


@dataclass(frozen=True)
class Finding:
    """One possible breach: which rule, at which turn, and why in one line."""

    rule: str
    turn_index: int
    reason: str


def _speaker(turn: Mapping[str, str]) -> str:
    return turn.get("speaker", "").strip().lower()


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


# --- identity verification -----------------------------------------------------

# What a customer's answer to an identity question looks like after redaction.
# A PIN has no placeholder of its own, so a bare run of digits also counts.
_IDENTITY_ANSWER_RE = re.compile(
    r"<(?:ACCOUNT_NUMBER|DATE_OF_BIRTH|SSN_LAST4|PHONE_NUMBER|ADDRESS|EMAIL_ADDRESS)_\d+>"
    r"|(?<![\d$.])\d{4,}(?!\d|\.\d)"
)
# Items that are only ever asked for to prove who someone is.
_STRONG_QUESTION_RE = re.compile(
    r"\baccount number\b|\bdate of birth\b|\bbirth ?date\b|\bbirthday\b|\bdob\b|\bsocial\b|"
    r"\bssn\b|\bpin\b|\bpasscode\b",
    _FLAGS,
)
# Items that are also asked for in the ordinary course of a call ("which email
# should I use?"). They count as verification only when the agent says so, or
# inside a run of identity questions.
_WEAK_QUESTION_RE = re.compile(r"\bnumber\b|\baddress\b|\be-?mail\b", _FLAGS)
_VERIFY_CUE_RE = re.compile(
    r"\bverif\w*|\bconfirm\b|(?<!social )\bsecurity\b|\bon file\b|\bon the account\b|"
    r"\bwho you are\b|\bidentity\b",
    _FLAGS,
)
# The agent says identity questions are coming.
_LEAD_IN_RE = re.compile(
    r"\bverif\w*|\bfor (?:your )?security\b|\bsecurity questions?\b|\bconfirm who you are\b|"
    r"\bconfirm your identity\b|\b(?:couple|few) (?:of )?(?:quick )?questions\b",
    _FLAGS,
)
# A warning about what scammers ask for mentions the same items and is not a question.
_NOT_A_QUESTION_RE = re.compile(r"\bnever\b|\bto them\b|\bgave them\b", _FLAGS)


def _asks_for_identity(text: str, in_run: bool) -> bool:
    for sentence in _sentences(text):
        if _NOT_A_QUESTION_RE.search(sentence):
            continue
        if _STRONG_QUESTION_RE.search(sentence):
            return True
        if _WEAK_QUESTION_RE.search(sentence) and (in_run or _VERIFY_CUE_RE.search(sentence)):
            return True
    return False


def identity_answer_turns(turns: Sequence[Mapping[str, str]]) -> list[int]:
    """The index of every customer turn that answers an identity question, in order.

    An identity question is an agent turn that asks for an account number, a
    date of birth, a Social Security number or a PIN, or that asks for a
    number, address or email while saying it is to verify or confirm, or as
    part of a run of such questions. It is answered when the customer's next
    turn holds a redacted value of one of those kinds.
    """
    answered: list[int] = []
    in_run = False
    for index, turn in enumerate(turns):
        if _speaker(turn) != AGENT:
            continue
        text = turn.get("text", "")
        asks = _asks_for_identity(text, in_run)
        if asks and index + 1 < len(turns):
            answer = turns[index + 1]
            if _speaker(answer) == CUSTOMER and _IDENTITY_ANSWER_RE.search(answer.get("text", "")):
                answered.append(index + 1)
        # A run starts when the agent says verification is coming and lasts
        # while each agent turn is another identity question.
        in_run = asks or (bool(_LEAD_IN_RE.search(text)) and not _NOT_A_QUESTION_RE.search(text))
    return answered


def verification_turn(turns: Sequence[Mapping[str, str]]) -> int | None:
    """The index of the customer turn that first answers an identity question.

    ``identity_answer_turns`` says what counts as one. Returns ``None`` when no
    identity question is answered anywhere in the call.
    """
    answered = identity_answer_turns(turns)
    return answered[0] if answered else None


# --- account details and account actions ------------------------------------------

_AMOUNT_RE = re.compile(r"<CPNI_AMOUNT_\d+>")
_USAGE_RE = re.compile(r"<CPNI_USAGE_\d+>")
_PLAN_ON_ACCOUNT_RE = re.compile(
    r"\byou(?:'re| are)\b[^.?!]*\bon\b[^.?!]*\b(?:plan\b|northline \w+)"
    r"|\byour (?:current )?plan is\b"
    r"|\bplan on (?:your|the) account\b"
    r"|\byou (?:currently |still |now )?have (?:the )?northline \w+"
    r"|\byou(?:'ve| have| currently have| also have)\b[^.?!]*\bon (?:your|the) "
    r"(?:\w+ ){0,4}?(?:plan|account|line)\b"
    r"|\bI (?:can )?(?:see|show)\b[^.?!]*\bplan\b",
    _FLAGS,
)
_MONTH_DAY = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|"
    r"december)\s\d{1,2}\b"
)
_DATE_CUE = (
    r"(?:due|payments?|paid|statements?|bill(?:ed|ing)?|bills|posted|balance|charged|autopay)"
)
_ACCOUNT_DATE_RE = re.compile(
    rf"\b{_DATE_CUE}\b[^.?!]*\b{_MONTH_DAY}|\b{_MONTH_DAY}[^.?!]*\b{_DATE_CUE}\b", _FLAGS
)
# A value the agent can only have read from the account, unless the customer said it first.
_ON_FILE_VALUE_RE = re.compile(
    r"<(?:ACCOUNT_NUMBER|DATE_OF_BIRTH|ADDRESS|EMAIL_ADDRESS|IMEI|ICCID)_\d+>"
)

# Things an agent can only see by opening the account.
_RECORD_NOUN = (
    r"(?:account|line|plan|pass|pack|add-on|bill|billing|balance|statement|payment|order|case|"
    r"claim|protection|usage|charge|fee|on file|<[A-Z_0-9]+>)"
)
# Things an agent changes when they act on the account.
_ACCOUNT_NOUN = (
    r"(?:account|line|service|plan|pass|pack|add-on|sim|number|bill|billing|payment|order|case|"
    r"claim|device|reminder|note|security|pin|voicemail|transfer|protection)"
)
_ACCOUNT_SEEN_RE = re.compile(
    r"\bI(?:'m| am)? (?:can |do )?(?:see|seeing|show|showing|looking at)\b(?!,)[^.?!,]*"
    rf"{_RECORD_NOUN}"
    rf"|\b(?:it|the account|your account|the system|my screen) (?:shows|says)\b"
    r"|\bwe have on file\b|\bon your account\b[^.?!]*\b(?:is|at|shows)\b",
    _FLAGS,
)
# "I've suspended", "I have reset": a past participle after "I have", which sets
# it apart from "I have a couple of questions". Verbs that only report or pass
# on information are left out.
_PARTICIPLE = (
    r"(?!asked\b|heard\b|seen\b|been\b|had\b|got\b|gotten\b|sent\b|emailed\b|texted\b|"
    r"found\b|known\b|told\b|explained\b|shared\b|noticed\b|read\b|ten\b|seven\b|eleven\b|"
    r"even\b|then\b|when\b|often\b|open\b)"
    r"(?:\w+ed|\w+en|\w+wn|\w+ne|set|reset|put|made|cut|shut|paid|sold|left|kept|built|begun|"
    r"brought|run|held)\b"
)
_ACCOUNT_ACTION_RE = re.compile(
    rf"\bI(?:'ve| have)(?: just| also| already| now| gone ahead and)? {_PARTICIPLE}"
    rf"|\bI(?:'m| am)(?: also| now| just)? (?!sorry\b|going\b|not\b|afraid\b)\w+ing\b[^.?!]*"
    rf"{_ACCOUNT_NOUN}"
    r"|(?:^|[.!?]\s)Done\b"
    r"|\b(?:it|that|your \w+(?: \w+)?)(?:'s| is| has been| are)(?: now| all| back)? "
    r"(?:suspended|active|activated|blocked|cancel+ed|added|removed|set up|turned (?:on|off)|"
    r"unlocked|reset|restored|paused|switched|updated|on its way)\b"
    r"|\bpayment went through\b",
    _FLAGS,
)


# The redactor also replaces a public price that stands near a word such as
# "bill" or "due". A figure is account data only when the sentence is about
# this customer.
_ABOUT_THE_CUSTOMER_RE = re.compile(
    r"\byou(?:r|rs|'ve|'re|'ll)?\b|\baccount\b|\bbalance\b|\bstatement\b|\bon file\b|"
    r"\bI (?:can |do )?(?:see|show)\b|\blast (?:month|bill|payment)\b|\bthis month\b",
    _FLAGS,
)
# A usage figure the redactor left in clear text, said about the customer's own use.
_QUANTITY = r"\b\d[\d.,]*\s?(?:minutes|mins|gb|gigs|gigabytes|mb|megabytes|texts|messages)\b"
_RAW_USAGE_RE = re.compile(
    rf"\byou(?:'ve| have)\b[^.?!]{{0,40}}?{_QUANTITY}"
    rf"|\byour (?:data |talk |text )?(?:use|usage)\b[^.?!]{{0,30}}?{_QUANTITY}"
    rf"|\byou(?:'re| are) at\b[^.?!]{{0,15}}?{_QUANTITY}",
    _FLAGS,
)


def _account_detail(text: str) -> str | None:
    """What account detail an agent turn states, in words, if any."""
    for sentence in _sentences(text):
        if not _ABOUT_THE_CUSTOMER_RE.search(sentence):
            continue
        if _AMOUNT_RE.search(sentence):
            return "a bill amount"
        if _USAGE_RE.search(sentence):
            return "usage"
    if _RAW_USAGE_RE.search(text):
        return "usage"
    if _PLAN_ON_ACCOUNT_RE.search(text):
        return "the plan the customer is on"
    if _ACCOUNT_DATE_RE.search(text):
        return "a payment or statement date"
    return None


def _on_file_value(text: str, said_by_customer: set[str]) -> bool:
    return any(match.group(0) not in said_by_customer for match in _ON_FILE_VALUE_RE.finditer(text))


def _check_verification(turns: Sequence[Mapping[str, str]]) -> list[Finding]:
    verified_at = verification_turn(turns)
    findings: list[Finding] = []
    said_by_customer: set[str] = set()
    for index, turn in enumerate(turns):
        text = turn.get("text", "")
        if _speaker(turn) != AGENT:
            said_by_customer.update(re.findall(r"<[A-Z_0-9]+>", text))
            continue
        if verified_at is not None and index > verified_at:
            break
        detail = _account_detail(text)
        if detail is None and _on_file_value(text, said_by_customer):
            detail = "a detail from the account that the customer had not given"
        if verified_at is not None:
            if detail is not None:
                findings.append(
                    Finding(
                        RULE_DISCLOSURE,
                        index,
                        f"The agent states {detail} before the customer has answered "
                        "an identity question.",
                    )
                )
            continue
        if detail is not None:
            reason = f"The agent states {detail}"
        elif _ACCOUNT_SEEN_RE.search(text):
            reason = "The agent reads from the account"
        elif _ACCOUNT_ACTION_RE.search(text):
            reason = "The agent makes a change for the customer"
        else:
            continue
        # One finding is enough: the breach is the missing verification, not each turn.
        return [
            Finding(
                RULE_SKIPPED,
                index,
                f"{reason} and no identity question is answered anywhere in the call.",
            )
        ]
    return findings


# --- card read back ---------------------------------------------------------------

_CARD_RE = re.compile(r"<CREDIT_CARD_\d+>")


def _check_card(turns: Sequence[Mapping[str, str]]) -> list[Finding]:
    return [
        Finding(
            RULE_CARD_READ_BACK,
            index,
            "The agent says a full payment card number.",
        )
        for index, turn in enumerate(turns)
        if _speaker(turn) == AGENT and _CARD_RE.search(turn.get("text", ""))
    ]


# --- unauthorized promise -----------------------------------------------------------

_CHARGE = (
    r"(?:\b(?:fees?|charges?|refunds?|credits?(?! card)|overages?|amount|money back|waiver)\b|"
    r"\$\s?\d+|<CPNI_AMOUNT_\d+>)"
)
_CHARGE_RE = re.compile(_CHARGE, _FLAGS)
_PRONOUN = r"(?:it|that|this|them|those|these)"
_FIRST_PERSON = (
    r"(?:\b(?:I|we)(?:'ve| have|'ll| will|'m| am|'re| are| can| just| already| did|"
    r"'d be (?:happy|glad) to| would be (?:happy|glad) to)?|\blet me)"
    r"(?: just| already| now| also| went ahead and| gone ahead and| go ahead and| going to|"
    r" gonna)*"
)
_MONEY_VERB = (
    r"(?:waiv\w+|refund\w*|credit(?:ed|ing)?(?! card)|revers\w+|remov\w+|cancel\w+|void\w*|"
    r"comp(?:ed|ing)|knock\w*|wip\w+|eras\w+|delet\w+|clear(?:ed|ing)?|"
    r"t(?:ake|aking|ook|aken)\b[^.?!]{0,30}?\boff|t(?:ake|aking|ook|aken) care of)"
)
_GIVE_VERB = r"(?:appl\w+|process\w*|issu\w+|giv\w+|gave|put|add\w*|post\w*)"
_MONEY_BACK = r"(?:credits?(?! card)|refunds?)(?! request)"
# "I've waived that fee", "I'll take that charge off", "I went ahead and removed it".
_DID_IT_RE = re.compile(rf"{_FIRST_PERSON} (?P<verb>{_MONEY_VERB})\b", _FLAGS)
# "removed it", "take that off", "took care of it": the verb's object is a pronoun.
_PRONOUN_OBJECT_RE = re.compile(rf"^\w+(?: care of)? {_PRONOUN}\b", _FLAGS)
# The words that can hold the verb's object: up to the next comma.
_OBJECT_WINDOW_RE = re.compile(r"[^.?!,;]{0,45}")
# "I've applied a $5 credit", "I've processed the refund".
_GAVE_IT_RE = re.compile(rf"{_FIRST_PERSON} {_GIVE_VERB}\b[^.?!]{{0,40}}?\b{_MONEY_BACK}", _FLAGS)
# "That charge has been removed", "it's off your bill", "consider it gone".
_IS_GONE_RE = re.compile(
    rf"(?P<object>{_CHARGE}|\b{_PRONOUN}\b)[^.?!]{{0,25}}?(?:\bhas been|\bhave been|\bis|'s|"
    r"'s been|\bwas|\bare|\bwere|\bwill be|'ll be|\bis going to be)(?: now| already| all)? "
    r"(?:waived|removed|refunded|credited|reversed|gone|off\b|cancel+ed|taken off|"
    r"taken care of|wiped|cleared|deleted)"
    rf"|\bconsider (?P<considered>{_PRONOUN}|the {_CHARGE}) "
    r"(?:gone|done|waived|removed|refunded|taken care of)",
    _FLAGS,
)
# "You'll get the full refund", "I guarantee it", "you have my word".
_GUARANTEE_RE = re.compile(
    r"\byou(?:'ll| will| should|'re going to| are going to)(?: definitely)? "
    rf"(?:get|see|receive|have)\b[^.?!]{{0,30}}?\b{_MONEY_BACK}"
    r"|\byou (?:won't|will not) (?:be charged|have to pay|owe)\b"
    r"|\b(?:I|we) (?:guarantee|promise)\b|\byou have my word\b",
    _FLAGS,
)
# The agent is saying what they cannot do, or what depends on someone else. The
# refusal has to be about the act itself: "don't worry, I've waived it" is a claim.
_NOT_A_CLAIM_RE = re.compile(
    r"\b(?:can'?t|cannot|can not|couldn't|not able to|unable to|not allowed to|"
    r"not authori[sz]ed to|won't be able to|don't have the \w+ to)\b"
    r"|\bif\b|\bonce\b|\bmay\b|\bmight\b"
    r"|\bbilling (?:team|department|group|can|will|has|have|decides|handles|reviews|would)\b"
    r"|\b(?:to|by|from|with|ask|asked|asking) (?:the |our )?billing\b"
    r"|\brequest\w*|\bdispute\w*|\breview\w*|\bescalat\w+|\bsubmit\w*|\bsupervisor\b",
    _FLAGS,
)


def _claims_charge_removed(sentence: str, charge_in_context: bool) -> bool:
    if _NOT_A_CLAIM_RE.search(sentence):
        return False
    charge_here = bool(_CHARGE_RE.search(sentence))
    for match in _DID_IT_RE.finditer(sentence):
        # "I've taken the pack off" is not about a charge. "I've taken it off" is,
        # when a charge is what the customer has just asked about.
        after = sentence[match.start("verb") :]
        window = _OBJECT_WINDOW_RE.match(after)
        if window is not None and _CHARGE_RE.search(window.group(0)):
            return True
        if _PRONOUN_OBJECT_RE.search(after) and charge_in_context:
            return True
    if _IS_GONE_RE.search(sentence) and (charge_here or charge_in_context):
        return True
    if _GAVE_IT_RE.search(sentence):
        return True
    return bool(_GUARANTEE_RE.search(sentence)) and (charge_here or charge_in_context)


def _check_promise(turns: Sequence[Mapping[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for index, turn in enumerate(turns):
        if _speaker(turn) != AGENT:
            continue
        text = turn.get("text", "")
        before = turns[index - 1] if index > 0 else None
        asked = (
            before is not None
            and _speaker(before) == CUSTOMER
            and bool(_CHARGE_RE.search(before.get("text", "")))
        )
        charge_in_context = asked or bool(_CHARGE_RE.search(text))
        if any(
            _claims_charge_removed(sentence, charge_in_context) for sentence in _sentences(text)
        ):
            findings.append(
                Finding(
                    RULE_PROMISE,
                    index,
                    "The agent says they removed, refunded or credited a charge themselves, "
                    "or promises it. Only the billing team can.",
                )
            )
    return findings


# --- full Social Security number -----------------------------------------------------

_SSN_RE = re.compile(r"\bsocial\b|\bssn\b", _FLAGS)
_WHOLE = (
    r"(?:\bfull\b|\bwhole\b|\bcomplete\b|\bentire\b|\ball (?:nine|9)\b|\b(?:nine|9)[- ]digits?\b|"
    r"\ball of it\b)"
)
_WHOLE_RE = re.compile(_WHOLE, _FLAGS)
# "We never ask for your whole number": the refusal comes before the word, in the same clause.
_NOT_A_REQUEST_RE = re.compile(
    r"\b(?:never|don't|do not|won't|doesn't|shouldn't|no need|not need)\b"
    rf"[^.?!,;]{{0,40}}?{_WHOLE}",
    _FLAGS,
)


def _check_full_ssn(turns: Sequence[Mapping[str, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for index, turn in enumerate(turns):
        text = turn.get("text", "")
        if _speaker(turn) != AGENT or not _SSN_RE.search(text):
            continue
        if any(
            _WHOLE_RE.search(sentence) and not _NOT_A_REQUEST_RE.search(sentence)
            for sentence in _sentences(text)
        ):
            findings.append(
                Finding(
                    RULE_FULL_SSN,
                    index,
                    "The agent asks for a full Social Security number, not the last four digits.",
                )
            )
    return findings


def check_call(turns: Sequence[Mapping[str, str]]) -> list[Finding]:
    """Every possible breach in one redacted call, in turn order.

    Args:
        turns: The call, each turn a mapping with ``speaker`` (``agent`` or
            ``customer``) and ``text`` (redacted).

    Returns:
        The findings, earliest turn first. An empty list means no rule fired,
        which is not proof that the call is clean.
    """
    findings = [
        *_check_verification(turns),
        *_check_card(turns),
        *_check_promise(turns),
        *_check_full_ssn(turns),
    ]
    return sorted(findings, key=lambda finding: (finding.turn_index, RULES.index(finding.rule)))
