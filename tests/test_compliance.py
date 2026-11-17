"""The compliance checker, on redacted turns written by hand.

Every phrasing here comes from the scripted calls or the development wording,
so these cases are in-sample. ``eval/compliance_eval.py`` scores the checker on
wording it was not written against.
"""

import pytest

from copilot.compliance import (
    RULE_CARD_READ_BACK,
    RULE_DISCLOSURE,
    RULE_FULL_SSN,
    RULE_PROMISE,
    RULE_SKIPPED,
    RULES,
    Finding,
    check_call,
    identity_answer_turns,
    verification_turn,
)

Turns = list[dict[str, str]]


def call(*lines: str) -> Turns:
    """Turns from lines such as ``"a: Hello"`` and ``"c: Hi"``."""
    speakers = {"a": "agent", "c": "customer"}
    return [{"speaker": speakers[line[0]], "text": line[3:]} for line in lines]


OPENING = (
    "a: Thank you for calling Northline Wireless, this is <PERSON_1>. How can I help you today?",
    "c: Hi <PERSON_1>. My name is <PERSON_2> and I need some help.",
    "a: Of course, <PERSON_2>. What's going on?",
)
VERIFIED = (
    "a: Let me pull up your account. First I need to verify a few things.",
    "a: Can I have your account number, please?",
    "c: Sure, it's <ACCOUNT_NUMBER_1>.",
    "a: And your date of birth?",
    "c: <DATE_OF_BIRTH_1>.",
)
CLOSING = ("a: Is there anything else I can help you with today?", "c: No, thank you.")


def rules_found(turns: Turns) -> list[str]:
    return [finding.rule for finding in check_call(turns)]


# --- verification ------------------------------------------------------------------


def test_an_answered_identity_question_is_verification() -> None:
    turns = call(*OPENING, "c: My bill is high.", *VERIFIED)

    assert verification_turn(turns) == 6


def test_every_answered_identity_question_is_listed_and_the_first_is_verification() -> None:
    turns = call(
        *OPENING,
        "c: My bill is high.",
        *VERIFIED,
        "a: Thank you. The payment went through.",
        "a: Which email should I send the receipt to?",
        "c: <EMAIL_ADDRESS_1>",
    )

    # The email at the end is asked for in the ordinary course of the call, not to verify.
    assert identity_answer_turns(turns) == [6, 8]
    assert identity_answer_turns(turns[:7]) == [6]
    assert identity_answer_turns(call(*OPENING)) == []


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Which number are you calling about?", "My number is <PHONE_NUMBER_1>."),
        ("What is your home address?", "I live at <ADDRESS_1>."),
        ("Can I get an email for the confirmation?", "Yes, send it to <EMAIL_ADDRESS_1>."),
    ],
)
def test_an_everyday_question_counts_after_the_agent_says_they_are_verifying(
    question: str, answer: str
) -> None:
    lead_in = "a: Sure. Before I open the account I need to confirm who you are."

    assert verification_turn(call(lead_in, f"a: {question}", f"c: {answer}")) == 2
    assert verification_turn(call(f"a: {question}", f"c: {answer}")) is None


def test_an_everyday_question_counts_when_it_says_it_is_to_confirm() -> None:
    turns = call("a: Can you confirm the billing address on file?", "c: It's <ADDRESS_1>.")

    assert verification_turn(turns) == 1


@pytest.mark.parametrize(
    "lines",
    [
        # Asking where to send something is not asking who someone is.
        ("a: Where should I send the new SIM card?", "c: Send it to her, at <ADDRESS_1>."),
        ("a: What's a good number to reach you?", "c: Call my wife's phone, <PHONE_NUMBER_1>."),
        ("a: I can also email you a large-print guide. What's your email?", "c: <EMAIL_ADDRESS_1>"),
        # A warning about scam calls names the same items.
        (
            "a: We will never call and ask for your full Social Security number. "
            "Did you give it to them?",
            "c: Only the last four, <SSN_LAST4_1>.",
            "a: Okay. What number did they call from?",
            "c: <PHONE_NUMBER_1>.",
        ),
        # The question was asked and not answered.
        ("a: Can I have your account number, please?", "c: I don't have it with me."),
        # "On file" in a statement does not start a run of questions.
        (
            "a: For the record, the IMEI we have on file is <IMEI_1>.",
            "c: What do I do about a new phone?",
            "a: What's a good number to reach you?",
            "c: <PHONE_NUMBER_1>.",
        ),
    ],
)
def test_what_is_not_verification(lines: tuple[str, ...]) -> None:
    assert verification_turn(call(*lines)) is None


def test_a_pin_given_in_plain_digits_is_an_answer() -> None:
    turns = call("a: What is your account PIN?", "c: It's 4821.")

    assert verification_turn(turns) == 1


# --- disclosure before verification -------------------------------------------------


@pytest.mark.parametrize(
    ("line", "detail"),
    [
        ("Let me take a look. I see your current balance is <CPNI_AMOUNT_1>.", "a bill amount"),
        ("It shows you've used <CPNI_USAGE_1> so far this month.", "usage"),
        ("Looking at your line, you've gone through 16.3 GB already.", "usage"),
        ("I can see you're on the Northline Plus 10 plan.", "the plan"),
        ("The plan on your account is Northline Talk.", "the plan"),
        ("Your last payment came in on August 14.", "date"),
        ("Your next bill is due on September 3.", "date"),
        ("I see a Late Payment Fee of $5 on your statement dated October 8.", "date"),
        ("The email I have for you is <EMAIL_ADDRESS_1>.", "had not given"),
    ],
)
def test_an_account_detail_before_verification_is_a_disclosure(line: str, detail: str) -> None:
    turns = call(*OPENING, "c: My bill is high.", f"a: {line}", "c: Okay.", *VERIFIED, *CLOSING)

    findings = check_call(turns)

    assert [(f.rule, f.turn_index) for f in findings] == [(RULE_DISCLOSURE, 4)]
    assert detail in findings[0].reason


@pytest.mark.parametrize(
    "line",
    [
        "Just so you know, our Northline Unlimited Essentials plan is $50 a month.",
        "The International Calling Pack is $5 a month and includes 300 minutes.",
        "For anyone on a 5 GB plan, data slows down after 5 GB is used.",
        "Bills are due 21 days after they are issued. That's the same for everyone.",
        # The redactor replaces a public price that stands near "bill" or "due".
        "In general, a Late Payment Fee is <CPNI_AMOUNT_1>, and it's added when a bill is "
        "more than 10 days past due.",
        "Let me pull up your account.",
    ],
)
def test_public_information_before_verification_is_not_a_disclosure(line: str) -> None:
    turns = call(*OPENING, "c: My bill is high.", f"a: {line}", "c: Okay.", *VERIFIED, *CLOSING)

    assert check_call(turns) == []


def test_a_detail_after_verification_is_fine() -> None:
    turns = call(
        *OPENING,
        "c: My bill is high.",
        *VERIFIED,
        "a: I see your bill this month is <CPNI_AMOUNT_1>, and last month it was <CPNI_AMOUNT_2>.",
        "c: Right, that's a big jump.",
        *CLOSING,
    )

    assert check_call(turns) == []


def test_what_the_customer_says_about_their_own_bill_is_not_a_disclosure() -> None:
    turns = call(
        *OPENING,
        "c: My bill went up to <CPNI_AMOUNT_1> and my neighbor pays less.",
        "a: I'm sorry to hear that.",
        *VERIFIED,
        *CLOSING,
    )

    assert check_call(turns) == []


def test_a_value_the_customer_gave_first_is_not_from_the_account() -> None:
    turns = call(
        *OPENING,
        "c: I think it's Google. My email is <EMAIL_ADDRESS_1>.",
        "a: Thanks, I'll use <EMAIL_ADDRESS_1>.",
        *VERIFIED,
        *CLOSING,
    )

    assert check_call(turns) == []


# --- verification skipped -----------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Your balance due is <CPNI_AMOUNT_1>. Which card would you like to use?",
        "I'm so sorry. I'm suspending the line now so no one can use it.",
        "Thank you. I've refreshed the SIM on our side. Please restart once more.",
        "Thank you. Your iPhone 13 is now active on <PHONE_NUMBER_1>. Try making a call.",
        "I've started the transfer. It usually finishes within 24 hours.",
        "Done. I'll email the tracking number. Which email should I use?",
        "It's suspended. If you find it, call us and we'll turn it back on right away.",
        "I see Device Protection on your account. Our claims team will call you.",
        "You have the International Calling Pack on your Northline Talk plan.",
    ],
)
def test_account_work_with_no_verification_is_flagged_once(line: str) -> None:
    turns = call(
        *OPENING,
        "c: I need some help with my phone.",
        "a: Let me pull up your account.",
        f"a: {line}",
        "c: Okay.",
        "a: I've added the pass and sent a confirmation to <EMAIL_ADDRESS_1>.",
        *CLOSING,
    )

    findings = check_call(turns)

    assert [(f.rule, f.turn_index) for f in findings] == [(RULE_SKIPPED, 5)]
    assert "no identity question" in findings[0].reason


def test_how_to_help_with_no_verification_is_fine() -> None:
    turns = call(
        *OPENING,
        "c: The words on my screen are too small to read.",
        "a: Sure, I can help with that.",
        "a: We can make them bigger. Open Settings and tap Display.",
        "c: Okay.",
        "a: Tap Font Size and drag the slider to the right.",
        "c: Oh, that's much better.",
        "a: I can also email you a large-print guide. What's your email?",
        "c: <EMAIL_ADDRESS_1>",
        "a: Sent. It should arrive in a few minutes.",
        "a: You can see your bill in the app under Billing.",
        *CLOSING,
    )

    assert check_call(turns) == []


def test_a_call_is_never_both_skipped_and_a_disclosure() -> None:
    skipped = call(*OPENING, "c: My bill is high.", "a: Your balance is <CPNI_AMOUNT_1>.")
    late = [*skipped, *call(*VERIFIED)]

    assert rules_found(skipped) == [RULE_SKIPPED]
    assert rules_found(late) == [RULE_DISCLOSURE]


# --- card read back -------------------------------------------------------------------


def test_a_card_placeholder_in_an_agent_turn_is_a_read_back() -> None:
    turns = call(
        *OPENING,
        "c: I'd like to pay my bill over the phone.",
        *VERIFIED,
        "a: Your balance due is <CPNI_AMOUNT_1>. Which card would you like to use?",
        "c: My Visa. The number is <CREDIT_CARD_1>.",
        "a: Let me read that back: <CREDIT_CARD_1>. Is that right?",
        "c: Yes, that's right.",
        *CLOSING,
    )

    assert check_call(turns) == [
        Finding(RULE_CARD_READ_BACK, 11, "The agent says a full payment card number.")
    ]


@pytest.mark.parametrize(
    ("agent", "customer"),
    [
        ("Thank you. I have the card ending in 4821.", "That's the one."),
        ("Sorry, could you say the number once more?", "Sure. <CREDIT_CARD_1>."),
        ("Thanks. For your security I won't repeat the number.", "I appreciate that."),
    ],
)
def test_a_card_the_agent_does_not_repeat_is_fine(agent: str, customer: str) -> None:
    turns = call(
        *VERIFIED,
        "c: My Visa. The number is <CREDIT_CARD_1>.",
        f"a: {agent}",
        f"c: {customer}",
        *CLOSING,
    )

    assert check_call(turns) == []


# --- unauthorized promise -------------------------------------------------------------


@pytest.mark.parametrize(
    ("customer", "agent"),
    [
        (
            "There's a $5 late fee on my bill. Can you take that off?",
            "Sure, I've waived that fee for you.",
        ),
        ("Can I get a refund for the Activation Fee?", "Yes, I've refunded the $35 to your card."),
        (
            "I got a roaming charge I don't agree with.",
            "No problem, I'll take that charge off right now.",
        ),
        ("Can you do anything about the late fee?", "I went ahead and removed it."),
        ("That overage charge isn't fair.", "I'm going to refund that for you today."),
        ("there's a late fee on here too, can you remove it", "done, i waived it"),
        (
            "I'd like the late fee taken off, please.",
            "As a courtesy, I've applied a <CPNI_AMOUNT_3> credit to cover it.",
        ),
        (
            "Can you take off the paper bill charge?",
            "That charge has been removed. I took care of it myself.",
        ),
        ("What about the fee from last month?", "Consider it gone. I just reversed it."),
        (
            "Can I get my money back for that day pass?",
            "Yes, you'll get the full refund. I guarantee it.",
        ),
        (
            "The late fee again. Can you help?",
            "I can waive that for you. There, it's off your bill.",
        ),
        ("Can you knock off that late fee?", "Sure thing, I knocked the $5 off."),
        ("That fee shouldn't be there.", "We'll credit it back to you. You have my word."),
        ("Is the late fee still on there?", "Don't worry, I've waived the fee."),
        ("Can that fee come off?", "Let me waive that for you."),
    ],
)
def test_an_agent_who_removes_a_charge_themselves_is_flagged(customer: str, agent: str) -> None:
    turns = call(*VERIFIED, f"c: {customer}", f"a: {agent}", *CLOSING)

    assert [(f.rule, f.turn_index) for f in check_call(turns)] == [(RULE_PROMISE, 6)]


@pytest.mark.parametrize(
    ("customer", "agent"),
    [
        (
            "Can you take that late fee off?",
            "I can't waive it myself, but the billing team can. I've sent them the request.",
        ),
        (
            "Can I get a refund for the Activation Fee?",
            "Only our billing team can approve a refund. I'm sending them your request now.",
        ),
        ("I was charged twice last month.", "I'm not able to credit your account from this desk."),
        (
            "I want that roaming charge refunded.",
            "I've opened a dispute. If the billing team approves it, the charge will be refunded.",
        ),
        (
            "can you waive the late fee",
            "i can't waive fees, sorry. billing can, so i've asked them to look at it",
        ),
        (
            "Will the fee be removed?",
            "I can't promise that. The billing team will look at it and call you.",
        ),
        (
            "I'd like the overage charge taken off.",
            "I've asked billing to review the charge. They may waive it, but they decide.",
        ),
        ("Can you refund the late fee?", "Refunds and waivers are handled by our billing team."),
        (
            "There's a late fee on my bill.",
            "I can't remove the fee myself, so I'm sending this to our billing team to review.",
        ),
        # Removing something that is not a charge.
        (
            "My sister moved back home.",
            "I've taken the pack off. It stays active until the end of this billing month.",
        ),
        ("And the $5 stops after that?", "Yes, it won't be on your next bill."),
        ("Will there be a charge?", "I've suspended the line. There is no charge for that."),
        ("Yes, please do that.", "I can add the International Calling Pack for $5 a month."),
    ],
)
def test_an_agent_who_leaves_it_to_the_billing_team_is_not_flagged(
    customer: str, agent: str
) -> None:
    turns = call(*VERIFIED, f"c: {customer}", f"a: {agent}", *CLOSING)

    assert RULE_PROMISE not in rules_found(turns)


def test_a_customer_who_says_a_fee_was_waived_is_not_the_agent() -> None:
    turns = call(*VERIFIED, "c: Last time they said I've waived my right to a refund.", *CLOSING)

    assert check_call(turns) == []


# --- full Social Security number ---------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "I'll need your full Social Security number to verify.",
        "Can I have your whole Social Security number, please?",
        "Please read me all nine digits of your Social.",
        "can you type your full ssn for me",
        "I need the full Social Security number, not just the last four.",
        "Your SSN, all of it, please.",
        "I know we don't usually ask, but I need your complete Social Security number.",
    ],
)
def test_asking_for_a_full_social_security_number_is_flagged(question: str) -> None:
    turns = call(
        "a: For your security, I have a couple of questions.",
        f"a: {question}",
        "c: I only give the last four, <SSN_LAST4_1>.",
        *CLOSING,
    )

    assert [(f.rule, f.turn_index) for f in check_call(turns)] == [(RULE_FULL_SSN, 1)]


@pytest.mark.parametrize(
    "line",
    [
        "Can I get the last four digits of your Social Security number?",
        "I only need the last four of your Social. Never give anyone the full number.",
        "Please don't give me your full Social Security number. The last four digits are enough.",
        "We never ask for your whole Social Security number, only the last four.",
        "I don't need the complete number, just the last four of your Social Security number.",
        "We will never call and ask for your full Social Security number. Did you give it to them?",
    ],
)
def test_asking_for_the_last_four_or_warning_about_the_full_number_is_fine(line: str) -> None:
    turns = call(
        "a: For your security, I have a couple of questions.",
        f"a: {line}",
        "c: <SSN_LAST4_1>.",
        *CLOSING,
    )

    assert check_call(turns) == []


def test_a_customer_who_mentions_their_full_number_is_not_the_agent_asking() -> None:
    turns = call(
        *VERIFIED,
        "c: Someone called and asked for my full Social Security number.",
        "a: Please do not give that out.",
    )

    assert check_call(turns) == []


# --- the whole call ---------------------------------------------------------------------


def test_findings_come_in_turn_order_and_name_a_known_rule() -> None:
    turns = call(
        *VERIFIED,
        "c: My Visa. The number is <CREDIT_CARD_1>.",
        "a: So that's <CREDIT_CARD_1>?",
        "c: Yes. And can you take the late fee off?",
        "a: Sure, I've waived that fee for you.",
    )

    findings = check_call(turns)

    assert [f.rule for f in findings] == [RULE_CARD_READ_BACK, RULE_PROMISE]
    assert [f.turn_index for f in findings] == [6, 8]
    assert all(f.rule in RULES and f.reason.endswith(".") for f in findings)


def test_an_empty_call_and_odd_speakers_do_not_break_it() -> None:
    assert check_call([]) == []
    assert check_call([{"speaker": "Agent ", "text": "So that's <CREDIT_CARD_1>?"}]) == [
        Finding(RULE_CARD_READ_BACK, 0, "The agent says a full payment card number.")
    ]
    assert check_call([{"speaker": "system", "text": "<CREDIT_CARD_1>"}, {"text": "hello"}]) == []
