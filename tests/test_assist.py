"""Call assist, on redacted turns written by hand. No network, no model, no Databricks.

The calls here follow the scripted ones, so the wording rules (the hint to hand
off, the reminders) are in-sample in these tests. ``eval/assist_eval.py``
measures the part that can be measured: which article comes up, and when.
"""

import json
import types
from typing import Any

import pytest

from copilot.assist import (
    ADOPT_SCORE,
    ASSIST_PROMPT,
    CHANGED_ARTICLE,
    CHANGED_HAND_OFF,
    CHANGED_IDENTITY,
    CHANGED_NEXT_STEP,
    CHANGED_REMINDER,
    MAX_PASSAGE_CHARS,
    MAX_STEP_CHARS,
    REMINDER_ACCOUNT_BEFORE_IDENTITY,
    SEARCH_TOP_K,
    STEP_FAILED,
    STEP_WITHHELD,
    SWITCH_MARGIN,
    WINDOW_TURNS,
    CallAssist,
    account_request,
    best_passage,
    check_step,
    follow,
    hand_off_hint,
    identity_checked_at,
    leader_takes_over,
    live_reminders,
    rank_articles,
    search_turns,
    topic_turns,
    window_query,
)
from copilot.compliance import RULE_CARD_READ_BACK, RULE_PROMISE
from copilot.config import Settings
from copilot.redaction import Redactor
from copilot.schemas import KBHit
from copilot.tools import ESCALATION_TEAMS, ToolError

Turns = list[dict[str, str]]


def call(*lines: str) -> Turns:
    """Turns from lines such as ``"a: Hello"`` and ``"c: Hi"``."""
    speakers = {"a": "agent", "c": "customer"}
    return [{"speaker": speakers[line[0]], "text": line[3:]} for line in lines]


# A call about a late fee, as the silver table would hold it. Turn numbers on the left.
LATE_FEE = call(
    "a: Thank you for calling Northline Wireless, this is <PERSON_1>. How can I help?",  # 0
    "c: Hi <PERSON_1>. My name is <PERSON_2> and I need some help.",  # 1
    "a: Of course, <PERSON_2>. What's going on?",  # 2
    "c: There's a late fee on my bill and I always pay on time.",  # 3
    "a: Let me pull up your account. First I need to verify a few things.",  # 4
    "a: Can I have your account number, please?",  # 5
    "c: Sure, it's <ACCOUNT_NUMBER_1>.",  # 6
    "a: And your date of birth?",  # 7
    "c: <DATE_OF_BIRTH_1>.",  # 8
    "a: I see a Late Payment Fee of $5 on your statement dated March 3.",  # 9
    "c: I mailed the check on time. I owed <CPNI_AMOUNT_1> and I paid all of it.",  # 10
    "a: I can't remove the fee myself, so I'm sending this to our billing team to review.",  # 11
    "c: Okay. Can I get my voicemail set up while I have you?",  # 12
    "a: Yes. Press and hold the 1 key, then follow the prompts.",  # 13
    "c: No, that's everything. Thank you.",  # 14
)

FEE_TEXT = (
    "Late payment fee - What the fee is\n"
    "# Late payment fee\n\n"
    "If you miss a payment, a small fee may be added to your bill.\n\n"
    "## What the fee is\n"
    "A **Late Payment Fee** is a $5 charge. It is added when a bill is more than 10 days "
    "past its due date.\n\n"
    "## How to ask for a waiver\n"
    "You can request that the $5 fee be removed one time.\n\n"
    "1. Dial **611** from your Northline phone.\n"
    "2. Tell the representative you want a **one-time waiver** of the Late Payment Fee.\n"
    "3. The billing team will review your request.\n\n"
    "## Need more help?\n"
    "Call Northline Wireless support at **611** or **1-800-555-0199**. Waiver, fee, bill, "
    "late, payment, pay, time.\n"
)


def hit(slug: str, score: float | None, title: str | None = None, text: str = "x") -> KBHit:
    return KBHit(
        chunk_id=f"{slug}#0",
        url=f"https://help.northline.example/articles/{slug}",
        title=title or slug.replace("-", " ").capitalize(),
        text=text,
        score=score,
    )


FEE = hit("late-payment-fee", 0.56, "Late payment fee", FEE_TEXT)
DISPUTE = hit("dispute-a-charge", 0.55, "Dispute a charge")
VOICEMAIL = hit("set-up-voicemail", 0.58, "Set up voicemail", "Set up voicemail - Steps\nHold 1.")
SUPPORT = hit("contact-support", 0.45, "Contact Northline support")


# --- the query ----------------------------------------------------------------------------------


def test_the_query_is_what_the_customer_said_in_their_last_two_turns() -> None:
    assert WINDOW_TURNS == 2
    assert window_query(LATE_FEE, 3) == (
        "Hi . My name is and I need some help. "
        "There's a late fee on my bill and I always pay on time."
    )
    # The agent's greeting, which names the company, is never part of a query.
    assert window_query(LATE_FEE, 1) == "Hi . My name is and I need some help."
    assert window_query(LATE_FEE, 0) == ""
    assert "<" not in window_query(LATE_FEE, 10)


def test_an_identity_answer_is_never_part_of_a_query() -> None:
    # Turns 6 and 8 answer identity questions. The turn before turn 10 that counts is turn 3.
    assert topic_turns(LATE_FEE, 10) == [1, 3, 10]
    assert window_query(LATE_FEE, 10) == (
        "There's a late fee on my bill and I always pay on time. "
        "I mailed the check on time. I owed and I paid all of it."
    )
    # A short reply is read with the issue it belongs to.
    turns = [*LATE_FEE[:9], *call("a: What kind of phone do you have?", "c: It's a Galaxy A15.")]
    assert window_query(turns, 10).startswith("There's a late fee on my bill")


def test_a_search_runs_when_the_customer_speaks_but_not_on_an_identity_answer() -> None:
    assert search_turns(LATE_FEE, len(LATE_FEE) - 1) == [1, 3, 10, 12, 14]
    # Up to a turn means up to that turn: nothing later is read.
    assert search_turns(LATE_FEE, 9) == [1, 3]
    assert search_turns(LATE_FEE, 0) == []


def test_a_customer_turn_that_is_only_a_placeholder_opens_no_search() -> None:
    turns = call("a: Who am I chatting with?", "c: <PERSON_1>", "a: Hello.", "c: My bill is high.")

    # The agent's question does not make a query of it.
    assert search_turns(turns, 1) == []
    assert search_turns(turns, 3) == [3]


# --- when the article on show changes -----------------------------------------------------------


def test_one_passage_is_kept_for_each_article_in_the_order_of_the_search() -> None:
    second = KBHit(chunk_id="late-payment-fee#1", url=FEE.url, title=FEE.title, text="y")

    assert rank_articles([FEE, second, DISPUTE]) == [FEE, DISPUTE]


def test_nothing_on_show_and_a_leader_above_the_floor_is_shown() -> None:
    assert leader_takes_over(None, [FEE, DISPUTE])
    assert not leader_takes_over(None, [])


def test_a_leader_under_the_floor_is_never_shown() -> None:
    weak = hit("contact-support", ADOPT_SCORE - 0.01)

    assert not leader_takes_over(None, [weak])
    assert not leader_takes_over(FEE.url, [weak, hit("pay-your-bill", 0.40)])
    assert leader_takes_over(None, [hit("contact-support", ADOPT_SCORE)])


def test_the_article_on_show_stays_when_it_still_leads() -> None:
    assert not leader_takes_over(FEE.url, [FEE, DISPUTE])


def test_a_new_leader_must_beat_the_article_on_show_by_the_margin() -> None:
    shown = hit("late-payment-fee", 0.550)

    assert not leader_takes_over(shown.url, [hit("dispute-a-charge", 0.565), shown])
    assert leader_takes_over(shown.url, [hit("dispute-a-charge", 0.550 + SWITCH_MARGIN), shown])


def test_an_article_that_left_the_results_is_held_at_the_lowest_score_in_them() -> None:
    close = [hit("set-up-voicemail", 0.560), hit("reset-voicemail-pin", 0.555)]
    clear = [hit("set-up-voicemail", 0.580), hit("reset-voicemail-pin", 0.555)]

    assert not leader_takes_over(FEE.url, close)
    assert leader_takes_over(FEE.url, clear)
    # With nothing else in the results there is nothing to hold it at.
    assert leader_takes_over(FEE.url, [hit("set-up-voicemail", 0.580)])


def test_without_scores_only_an_article_that_left_the_results_is_replaced() -> None:
    fee, dispute, voicemail = (hit(slug, None) for slug in ("fee", "dispute", "voicemail"))

    assert leader_takes_over(None, [fee])
    assert not leader_takes_over(fee.url, [dispute, fee])
    assert leader_takes_over(fee.url, [voicemail, dispute])


class Searches:
    """Stands in for the index: fixed results by turn, and a note of what was asked."""

    def __init__(self, by_turn: dict[int, list[KBHit]]) -> None:
        self.by_turn = by_turn
        self.asked: list[tuple[int, str]] = []

    def __call__(self, turn: int, query: str) -> list[KBHit]:
        self.asked.append((turn, query))
        return self.by_turn.get(turn, [SUPPORT])


LATE_FEE_RESULTS: dict[int, list[KBHit]] = {
    3: [FEE, DISPUTE],
    # The two swap places by a hair: the panel must not follow them.
    10: [hit("dispute-a-charge", 0.552), hit("late-payment-fee", 0.549, "Late payment fee")],
    12: [VOICEMAIL, hit("reset-voicemail-pin", 0.53)],
}


def test_following_a_call_changes_the_article_only_on_a_clear_change_of_topic() -> None:
    searches = Searches(LATE_FEE_RESULTS)

    track = follow(LATE_FEE, len(LATE_FEE) - 1, searches)

    assert track.searched == (1, 3, 10, 12, 14)
    assert [turn for turn, _ in searches.asked] == [1, 3, 10, 12, 14]
    # The greeting and the goodbye match nothing well; the near tie at turn 10 changes nothing.
    assert track.changed == (3, 12)
    assert track.shown is not None
    assert track.shown.hit == VOICEMAIL
    assert track.shown.since_turn == 12
    assert track.shown.query == window_query(LATE_FEE, 12)


def test_following_a_call_part_way_reads_nothing_after_that_turn() -> None:
    searches = Searches(LATE_FEE_RESULTS)

    track = follow(LATE_FEE, 11, searches)

    assert track.changed == (3,)
    assert track.shown is not None
    assert track.shown.hit == FEE
    assert max(turn for turn, _ in searches.asked) == 10
    assert follow(LATE_FEE, 2, Searches({})).shown is None


# --- the passage --------------------------------------------------------------------------------


def test_the_passage_is_the_section_that_shares_most_words_with_the_query() -> None:
    heading, passage = best_passage(FEE_TEXT, "Late payment fee", "can the fee be waived one time")

    assert heading == "How to ask for a waiver"
    assert passage.startswith("You can request that the $5 fee be removed one time.")
    # Markdown emphasis is gone, and the steps keep their lines.
    assert "**" not in passage
    assert "\n1. Dial 611 from your Northline phone." in passage


def test_the_passage_is_never_the_closing_section_and_a_tie_goes_to_the_first_heading() -> None:
    heading, _ = best_passage(FEE_TEXT, "Late payment fee", "waiver fee bill late payment pay time")
    assert heading != "Need more help?"

    # Nothing matches: the first section under a heading, not the line that repeats the title.
    heading, passage = best_passage(FEE_TEXT, "Late payment fee", "zebra")
    assert heading == "What the fee is"
    assert passage.startswith("A Late Payment Fee is a $5 charge.")

    # An article with no headings is all opening lines, and they are shown.
    assert best_passage("Title - \nJust one paragraph.", "Title", "zebra") == (
        None,
        "Just one paragraph.",
    )


def test_a_long_passage_is_cut_at_the_end_of_a_sentence() -> None:
    text = "Title - Part\n## Part\n" + "This sentence is about the fee. " * 40

    _, passage = best_passage(text, "Title", "fee")

    assert len(passage) <= MAX_PASSAGE_CHARS
    assert passage.endswith("the fee.")


def test_a_passage_with_no_text_is_empty() -> None:
    assert best_passage("Title - Part\n", "Title", "fee") == (None, "")


# --- reminders ----------------------------------------------------------------------------------


def test_a_call_in_which_no_rule_is_broken_raises_nothing_at_any_turn() -> None:
    for turn in range(len(LATE_FEE)):
        assert live_reminders(LATE_FEE, turn) == []


def test_the_identity_check_is_seen_at_the_turn_it_is_answered() -> None:
    assert identity_checked_at(LATE_FEE, 5) is None
    assert identity_checked_at(LATE_FEE, 6) == 6
    assert identity_checked_at(LATE_FEE, len(LATE_FEE) - 1) == 6


CARD = call(
    "a: Northline Wireless support. What can I do for you today?",  # 0
    "c: I'd like to pay my bill over the phone.",  # 1
    "a: Your balance due is <CPNI_AMOUNT_1>. Which card would you like to use?",  # 2
    "c: My Visa. The number is <CREDIT_CARD_1>.",  # 3
    "a: Thank you. Let me read that back: <CREDIT_CARD_1>. Is that right?",  # 4
    "c: Yes.",  # 5
    "a: Can I have your account number, please?",  # 6
    "c: It's <ACCOUNT_NUMBER_1>.",  # 7
)


def test_a_reminder_is_raised_at_the_turn_it_happens_and_not_before() -> None:
    assert live_reminders(CARD, 1) == []

    early = live_reminders(CARD, 2)
    assert [(reminder.rule, reminder.turn) for reminder in early] == [
        (REMINDER_ACCOUNT_BEFORE_IDENTITY, 2)
    ]
    assert early[0].title == "Account details before the identity check"

    later = live_reminders(CARD, 4)
    assert [(reminder.rule, reminder.turn) for reminder in later] == [
        (REMINDER_ACCOUNT_BEFORE_IDENTITY, 2),
        (RULE_CARD_READ_BACK, 4),
    ]
    assert later[1].title == "A card number was read back"


def test_a_reminder_is_not_taken_back_when_the_identity_check_comes_later() -> None:
    whole = live_reminders(CARD, len(CARD) - 1)

    assert identity_checked_at(CARD, len(CARD) - 1) == 7
    assert [(reminder.rule, reminder.turn) for reminder in whole] == [
        (REMINDER_ACCOUNT_BEFORE_IDENTITY, 2),
        (RULE_CARD_READ_BACK, 4),
    ]


def test_a_promise_to_waive_a_charge_is_a_reminder() -> None:
    turns = [*LATE_FEE[:11], *call("a: Don't worry, I've waived that fee for you.")]

    assert [(reminder.rule, reminder.turn) for reminder in live_reminders(turns, 11)] == [
        (RULE_PROMISE, 11)
    ]
    # Said before the identity check, the same words are two reminders at one turn.
    unchecked = call("c: There's a late fee on my bill.", "a: I've waived that fee for you.")
    assert [reminder.rule for reminder in live_reminders(unchecked, 1)] == [
        REMINDER_ACCOUNT_BEFORE_IDENTITY,
        RULE_PROMISE,
    ]


# --- the hint to hand off -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "category"),
    [
        ("I want to switch to a cheaper plan.", "plan_change"),
        ("I'd like to add a line for my husband.", "plan_change"),
        ("Can I put my daughter on my plan?", "plan_change"),
        ("I want to cancel my service and move my number to another company.", "cancellation"),
        ("My husband passed away and I need to cancel his line.", "cancellation"),
        ("My phone was stolen this morning. I need it turned off right away.", "device"),
        ("Could you waive the late fee on my bill?", "billing"),
        ("Please reset the PIN on my account.", "account_access"),
        ("Add that, please.", "other"),
    ],
)
def test_a_customer_asking_for_a_change_to_their_account_is_a_hint(
    said: str, category: str
) -> None:
    assert account_request(said) == category
    assert category in ESCALATION_TEAMS


@pytest.mark.parametrize(
    "said",
    [
        "There's a late fee on my bill and I always pay on time.",
        "My phone has said no service since yesterday.",
        "It works. Now how do I set up voicemail?",
        "How do I change my plan?",
        "I need to move my contacts and photos from my old phone to my new Pixel 8a.",
        "Okay, it's off. Can you call me to test? My number is <PHONE_NUMBER_1>.",
        "Yes, please do that.",
        "Can I get a new SIM in the meantime?",
        "I got a text saying my account is locked and to click a link. Is that from you?",
    ],
)
def test_a_question_or_a_complaint_is_not_a_hint(said: str) -> None:
    assert account_request(said) is None


def test_the_hint_is_the_customers_latest_request_and_names_who_would_take_it() -> None:
    turns = call(
        "a: How can I help?",
        "c: I want to switch to a cheaper plan.",
        "a: I want to cancel that for you.",  # the agent's words are never a request
        "c: Actually, I want to cancel my service.",
    )

    assert hand_off_hint(turns, 0) is None
    first = hand_off_hint(turns, 2)
    assert first is not None
    assert (first.category, first.team, first.turn) == ("plan_change", "the account team", 1)
    last = hand_off_hint(turns, 3)
    assert last is not None
    assert (last.category, last.turn) == ("cancellation", 3)


# --- the next step ------------------------------------------------------------------------------


class NoRedactor:
    """Finds nothing. For the tests that are not about personal data."""

    def redact(self, text: str) -> Any:
        return types.SimpleNamespace(text=text, entities=(), entity_counts={})


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


def checked(reply: str, redactor: Any = None, so_far: Turns | None = None) -> Any:
    return check_step(
        reply, redactor=redactor or NoRedactor(), so_far=so_far or LATE_FEE[:4], hit=FEE
    )


def test_a_next_step_is_plain_text_on_one_line() -> None:
    step = checked(
        '"Tell them the **$5** fee can be removed one time [1].\nThe billing team reviews it."'
    )

    assert step.text == "Tell them the $5 fee can be removed one time. The billing team reviews it."
    assert step.unsupported == ()
    assert not step.withheld


@pytest.mark.parametrize("reply", ["NONE", "none.", " None ", "", "**NONE**"])
def test_none_from_the_model_means_no_next_step(reply: str) -> None:
    step = checked(reply)

    assert step.text is None
    assert not step.withheld


def test_a_long_next_step_is_cut() -> None:
    step = checked("The fee is a charge on the bill. " * 30)

    assert step.text is not None
    assert len(step.text) <= MAX_STEP_CHARS
    assert step.text.endswith("on the bill.")


def test_a_figure_that_is_in_neither_the_article_nor_the_call_is_named() -> None:
    step = checked("The fee is $7 and it is added after 10 days.")

    assert step.text == "The fee is $7 and it is added after 10 days."
    assert step.unsupported == ("money",)
    assert checked("The fee is $5 and it is added after 10 days.").unsupported == ()


def test_a_next_step_that_promises_a_waiver_is_withheld() -> None:
    step = checked("Tell them: I've waived that fee for you, so you won't be charged.")

    assert step.text is None
    assert step.withheld


def test_personal_data_in_a_next_step_is_replaced_unless_the_sources_state_it(
    redactor: Redactor,
) -> None:
    step = checked(
        "Ask them to dial 611 or 1-800-555-0199. You can also reach Linda on 480-555-0132.",
        redactor,
    )

    assert step.text is not None
    # The support number is in the article. The other number is in no source.
    assert "1-800-555-0199" in step.text
    assert "480-555-0132" not in step.text
    assert "<PHONE_NUMBER_" in step.text


# --- the whole state, with fakes ----------------------------------------------------------------


class FakeSql:
    def __init__(self, calls: dict[str, Turns]) -> None:
        self.calls = calls
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, statement: str, parameters: Any) -> list[dict[str, Any]]:
        self.asked.append((statement, dict(parameters)))
        turns = self.calls.get(parameters["transcript_id"][1])
        return [] if turns is None else [{"turns_json": json.dumps(turns)}]


class FakeRetriever:
    """Answers by a word in the query, which is how the tests say what a turn is about."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, int | None]] = []

    def search(
        self, question: str, *, top_k: int | None = None, section: str | None = None
    ) -> list[KBHit]:
        self.asked.append((question, top_k))
        if "voicemail" in question:
            return [VOICEMAIL, hit("reset-voicemail-pin", 0.53)]
        if "mailed the check" in question:
            return LATE_FEE_RESULTS[10]
        if "late fee" in question:
            return [FEE, DISPUTE]
        return [SUPPORT]


class FakeLlm:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.prompts: list[list[tuple[str, str]]] = []

    def invoke(self, messages: list[tuple[str, str]]) -> Any:
        self.prompts.append(messages)
        reply = self.replies.pop(0) if self.replies else "NONE"
        if isinstance(reply, Exception):
            raise reply
        return types.SimpleNamespace(
            content=reply, usage_metadata={"input_tokens": 900, "output_tokens": 30}
        )

    def bind_tools(self, tools: Any) -> Any:
        return self


class FakeParts:
    def __init__(self, *replies: Any, calls: dict[str, Turns] | None = None) -> None:
        self.settings = Settings(_env_file=None)  # type: ignore[call-arg]
        self.sql = FakeSql(calls or {"T0001": LATE_FEE, "T0002": CARD})
        self.retriever = FakeRetriever()
        self.llm = FakeLlm(*replies)
        self.redactor = NoRedactor()


FEE_STEP = "Tell them the $5 fee can be removed one time. The billing team reviews the request."
VOICEMAIL_STEP = "Ask them to hold the 1 key and follow the prompts."


def assist_with(*replies: Any, calls: dict[str, Turns] | None = None) -> tuple[Any, FakeParts]:
    parts = FakeParts(*replies, calls=calls)
    return CallAssist(parts), parts  # type: ignore[arg-type]


def test_before_the_customer_states_the_issue_the_panel_is_empty() -> None:
    assist, parts = assist_with()

    state = assist.state("t0001", 2)

    assert state.transcript_id == "T0001"
    assert (state.turn, state.turns_total) == (2, len(LATE_FEE))
    assert state.article is None
    assert state.next_step is None
    assert state.step_problem is None
    assert state.identity_checked_at is None
    assert state.reminders == []
    assert state.hand_off is None
    assert state.changed == []
    assert state.cost.model_dump() == {"searches": 1, "model_calls": 0}
    assert parts.llm.prompts == []


def test_the_issue_turn_brings_up_the_article_the_passage_and_a_next_step() -> None:
    assist, parts = assist_with(FEE_STEP)

    state = assist.state("T0001", 3)

    assert state.article is not None
    assert state.article.title == "Late payment fee"
    assert state.article.url == FEE.url
    assert state.article.since_turn == 3
    assert state.article.score == 0.56
    # The section with most of the words of "a late fee on my bill ... pay on time".
    assert state.article.heading == "How to ask for a waiver"
    assert state.article.passage.startswith("You can request that the $5 fee be removed")
    assert state.next_step is not None
    assert state.next_step.text == FEE_STEP
    assert state.next_step.since_turn == 3
    assert state.changed == [CHANGED_ARTICLE, CHANGED_NEXT_STEP]
    assert state.cost.model_dump() == {"searches": 2, "model_calls": 1}
    assert [top_k for _, top_k in parts.retriever.asked] == [SEARCH_TOP_K, SEARCH_TOP_K]


def test_the_model_is_given_the_last_turns_and_the_article_and_nothing_later() -> None:
    assist, parts = assist_with(FEE_STEP)

    assist.state("T0001", 11)

    system, user = parts.llm.prompts[0]
    assert system == ("system", ASSIST_PROMPT)
    assert user[0] == "user"
    assert "customer: There's a late fee on my bill and I always pay on time." in user[1]
    assert "agent: Of course, <PERSON_2>. What's going on?" in user[1]
    assert '<article title="Late payment fee">' in user[1]
    assert "one-time waiver" in user[1]
    # The first step was written at turn 3. What was said after it is not in its prompt.
    assert "mailed the check" not in user[1]
    assert "Thank you for calling" not in user[1]


def test_a_call_followed_turn_by_turn_costs_one_model_call_for_each_change_of_article() -> None:
    assist, parts = assist_with(FEE_STEP, VOICEMAIL_STEP)

    states = [assist.state("T0001", turn) for turn in range(len(LATE_FEE))]

    assert len(parts.llm.prompts) == 2
    assert assist.usage.model_calls == 2
    assert assist.usage.input_tokens == 1800
    # One search for each turn the customer says something in, however often it is replayed.
    assert assist.searches == 5
    assert len(parts.retriever.asked) == 5
    assert len(parts.sql.asked) == 1
    assert [state.article.title if state.article else None for state in states] == (
        [None] * 3 + ["Late payment fee"] * 9 + ["Set up voicemail"] * 3
    )
    assert [state.next_step.text if state.next_step else None for state in states] == (
        [None] * 3 + [FEE_STEP] * 9 + [VOICEMAIL_STEP] * 3
    )
    assert [state.changed for state in states] == [
        [],
        [],
        [],
        [CHANGED_ARTICLE, CHANGED_NEXT_STEP],
        [],
        [],
        [CHANGED_IDENTITY],
        [],
        [],
        [],
        [],
        [],
        [CHANGED_ARTICLE, CHANGED_NEXT_STEP],
        [],
        [],
    ]
    assert states[-1].cost.model_dump() == {"searches": 5, "model_calls": 2}
    assert states[-1].identity_checked_at == 6

    # Asked again, in any order, nothing is paid for twice.
    again = [assist.state("T0001", turn) for turn in reversed(range(len(LATE_FEE)))]
    assert again[::-1] == states
    assert len(parts.llm.prompts) == 2
    assert len(parts.retriever.asked) == 5


def test_what_each_search_returned_is_kept_for_the_measurement() -> None:
    assist, parts = assist_with(FEE_STEP)

    assert assist.results("T0001", 3) == []  # not searched yet
    assist.state("T0001", 3)

    assert assist.results("t0001", 3) == [FEE, DISPUTE]
    assert assist.results("T0001", 2) == []  # the agent's turn: no search runs on it
    # Reading them back searches nothing.
    assert len(parts.retriever.asked) == 2


def test_asking_for_a_late_turn_first_writes_only_the_step_on_show() -> None:
    assist, parts = assist_with(VOICEMAIL_STEP)

    state = assist.state("T0001", 13)

    assert state.next_step is not None
    assert state.next_step.text == VOICEMAIL_STEP
    assert len(parts.llm.prompts) == 1
    # The count is what the call costs when it is followed turn by turn, as a live call is.
    assert state.cost.model_calls == 2


def test_an_article_the_model_finds_no_use_for_is_shown_without_a_next_step() -> None:
    assist, parts = assist_with("NONE")

    state = assist.state("T0001", 5)
    assist.state("T0001", 6)

    assert state.article is not None
    assert state.next_step is None
    assert state.step_problem is None
    assert state.changed == []
    assert len(parts.llm.prompts) == 1  # "nothing to say" is remembered too


def test_a_next_step_that_breaks_a_rule_is_withheld_and_the_panel_says_so() -> None:
    assist, _ = assist_with("Say: I've waived that fee for you.")

    state = assist.state("T0001", 3)

    assert state.article is not None
    assert state.next_step is None
    assert state.step_problem == STEP_WITHHELD
    assert state.changed == [CHANGED_ARTICLE]


def test_a_model_failure_leaves_the_article_and_is_tried_again_next_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failure = RuntimeError("the prompt said: There's a late fee on my bill")
    assist, parts = assist_with(failure, FEE_STEP)

    with caplog.at_level("WARNING"):
        first = assist.state("T0001", 3)
    second = assist.state("T0001", 4)

    assert first.article is not None
    assert first.next_step is None
    assert first.step_problem == STEP_FAILED
    assert second.next_step is not None
    assert second.next_step.text == FEE_STEP
    assert len(parts.llm.prompts) == 2
    # The kind of error is logged, never its message.
    assert "RuntimeError" in caplog.text
    assert "late fee" not in caplog.text


def test_reminders_the_identity_check_and_the_hint_arrive_with_their_turns() -> None:
    assist, _ = assist_with()

    at_two = assist.state("T0002", 2)
    at_four = assist.state("T0002", 4)
    at_seven = assist.state("T0002", 7)

    assert at_two.changed == [CHANGED_REMINDER]
    assert [reminder.rule for reminder in at_two.reminders] == [REMINDER_ACCOUNT_BEFORE_IDENTITY]
    assert at_two.identity_checked_at is None
    assert [reminder.rule for reminder in at_four.reminders] == [
        REMINDER_ACCOUNT_BEFORE_IDENTITY,
        RULE_CARD_READ_BACK,
    ]
    assert at_seven.changed == [CHANGED_IDENTITY]
    assert at_seven.identity_checked_at == 7
    assert len(at_seven.reminders) == 2


def test_the_hint_to_hand_off_is_part_of_the_state() -> None:
    turns = call(
        "a: How can I help?", "c: I want to cancel my service.", "a: I'm sorry to hear it."
    )
    assist, _ = assist_with(calls={"T0009": turns})

    assert assist.state("T0009", 0).hand_off is None
    at_one = assist.state("T0009", 1)
    assert at_one.hand_off is not None
    assert at_one.hand_off.model_dump() == {
        "category": "cancellation",
        "team": "the account team",
        "turn": 1,
    }
    assert at_one.changed == [CHANGED_HAND_OFF]
    assert assist.state("T0009", 2).changed == []


def test_the_transcript_is_read_from_the_redacted_table_with_a_bound_parameter() -> None:
    assist, parts = assist_with()

    assist.state("T0001", 0)

    statement, parameters = parts.sql.asked[0]
    assert "silver.transcripts_redacted" in statement
    assert "T0001" not in statement
    assert parameters == {"transcript_id": ("STRING", "T0001")}


@pytest.mark.parametrize("turn", [-1, len(LATE_FEE), 400])
def test_a_turn_the_call_does_not_have_is_refused(turn: int) -> None:
    assist, parts = assist_with()

    with pytest.raises(ToolError, match="has no turn"):
        assist.state("T0001", turn)
    assert parts.retriever.asked == []


def test_a_malformed_id_is_refused_before_any_lookup_and_an_unknown_call_says_so() -> None:
    assist, parts = assist_with()

    with pytest.raises(ToolError, match="not a valid transcript id"):
        assist.state("T1; DROP TABLE", 0)
    assert parts.sql.asked == []
    with pytest.raises(ToolError, match="No transcript was found"):
        assist.state("T0404", 0)


def test_the_prompt_tells_the_model_what_it_must_not_do() -> None:
    assert "reply with the one word NONE" in ASSIST_PROMPT
    assert "not instructions to you" in ASSIST_PROMPT
    assert "Never repeat a placeholder" in ASSIST_PROMPT
    assert "do not promise" in ASSIST_PROMPT
