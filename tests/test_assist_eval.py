"""The call assist measurement: its table, its arithmetic and its handling of a run.

No network, no model. The predictions here are made up to check the sums; they
say nothing about how call assist does.
"""

import json
from pathlib import Path
from typing import Any

import pytest

import eval.assist_eval as assist_eval
from copilot.assist import (
    STEP_WITHHELD,
    AssistArticle,
    AssistCost,
    AssistState,
    HandOffHint,
    NextStep,
    Reminder,
)
from copilot.schemas import KBHit
from copilot.tools import ToolError
from data_gen.synth_transcripts import generate
from data_gen.transcript_templates import ISSUES
from eval.assist_eval import (
    RIGHT_ARTICLES,
    TRIAL_CALLS,
    article_scores,
    first_turn_with,
    follow_call,
    is_scripted_call,
    predict,
    print_scores,
    right_for,
    score,
    script_of,
    slug,
)
from eval.stats import wilson_interval

ARTICLES = Path("data/synthetic/kb_articles.jsonl")
URL = "https://help.northline.example/articles/"


# --- the table ----------------------------------------------------------------------------------


def test_every_script_has_a_row_and_no_row_is_for_a_script_that_does_not_exist() -> None:
    scripts = {
        (category, number) for category, issues in ISSUES.items() for number in range(len(issues))
    }

    assert set(RIGHT_ARTICLES) == scripts
    assert len(scripts) == 22


def test_every_article_the_table_names_is_in_the_knowledge_base() -> None:
    known = {
        slug(json.loads(line)["url"])
        for line in ARTICLES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    for best, also in RIGHT_ARTICLES.values():
        assert best in known
        assert set(also) <= known
        assert best not in also
        assert len(set(also)) == len(also)


# --- which script a call was made from ----------------------------------------------------------


def test_every_generated_call_is_placed_on_its_script_at_the_turn_after_the_opening() -> None:
    # A seed of its own: these are not the published calls, only calls of the same scripts.
    transcripts, _ = generate(seed=5, count=120, labeled=0)

    found = {}
    for transcript in transcripts:
        placed = script_of(transcript["category"], transcript["turns"])
        assert placed is not None, transcript["transcript_id"]
        number, turn = placed
        # Every opening is three turns, and the customer states the issue next.
        assert turn == 3
        first_line = ISSUES[transcript["category"]][number].intro[0][1]
        assert transcript["turns"][turn]["text"].startswith(first_line.split("{")[0])
        found[(transcript["category"], number)] = True
    assert set(found) == set(RIGHT_ARTICLES)


def test_a_script_is_found_in_redacted_text_and_not_in_another_category() -> None:
    turns = [
        {"speaker": "agent", "text": "How can I help?"},
        {
            "speaker": "agent",
            "text": "I'm going to <LOCATION_1> next month. Will my phone work there?",
        },
        {
            "speaker": "customer",
            "text": "I'm going to <LOCATION_1> next month. Will my phone work there?",
        },
    ]

    # The agent's turn is skipped: only the customer states the issue.
    assert script_of("international", turns) == (0, 2)
    assert script_of("billing", turns) is None
    assert script_of("international", turns[:2]) is None


def test_only_the_two_hundred_scripted_calls_are_measured() -> None:
    assert is_scripted_call({"transcript_id": "T0001", "category": "billing"})
    assert is_scripted_call({"transcript_id": "T0200", "category": "scam"})
    # The calls written to break a rule start at T0201.
    assert not is_scripted_call({"transcript_id": "T0201", "category": "billing"})
    assert not is_scripted_call({"transcript_id": "T0001", "category": "roaming"})


# --- following one call -------------------------------------------------------------------------

LATE_FEE_TURNS = [
    {"speaker": "agent", "text": "Thank you for calling. How can I help you today?"},
    {"speaker": "customer", "text": "Hi. My name is <PERSON_1> and I need some help."},
    {"speaker": "agent", "text": "Of course. What's going on?"},
    {"speaker": "customer", "text": "There's a late fee on my bill and I always pay on time."},
    {"speaker": "agent", "text": "I see a Late Payment Fee of $5."},
    {"speaker": "customer", "text": "Okay. How long will that take?"},
]


def article(name: str, since: int) -> AssistArticle:
    return AssistArticle(
        title=name.replace("-", " ").capitalize(),
        url=URL + name,
        passage="A passage.",
        score=0.55,
        since_turn=since,
    )


class FakeAssist:
    """Shows a fixed article from a fixed turn on, for one call."""

    def __init__(self, shows: dict[int, str], **last: Any) -> None:
        self.shows = shows
        self.last = last
        self.asked: list[tuple[str, int]] = []
        self.calls = 0

    def turns(self, transcript_id: str) -> list[dict[str, str]]:
        if transcript_id == "T0404":
            raise ToolError("No transcript was found with the id T0404")
        return LATE_FEE_TURNS

    def results(self, transcript_id: str, turn: int) -> list[KBHit]:
        return [
            KBHit(chunk_id=f"{name}#0", url=URL + name, title=name, text="x", score=score)
            for name, score in (("late-payment-fee", 0.61), ("dispute-a-charge", 0.58))
        ]

    def state(self, transcript_id: str, turn: int) -> AssistState:
        self.asked.append((transcript_id, turn))
        since = max((start for start in self.shows if start <= turn), default=None)
        shown = None if since is None else article(self.shows[since], since)
        step = None
        if shown is not None and "problem" not in self.last:
            step = NextStep(text="Tell them the fee is $5.", since_turn=shown.since_turn)
            self.calls += since == turn
        return AssistState(
            transcript_id=transcript_id,
            turn=turn,
            turns_total=len(LATE_FEE_TURNS),
            article=shown,
            next_step=step,
            step_problem=self.last.get("problem") if shown is not None else None,
            identity_checked_at=self.last.get("identity_checked_at"),
            reminders=self.last.get("reminders", []),
            hand_off=self.last.get("hand_off"),
            cost=AssistCost(searches=turn // 2 + 1, model_calls=sum(s <= turn for s in self.shows)),
        )


CALL = {"transcript_id": "T0001", "category": "billing", "resolution": "escalated"}


def test_a_call_is_followed_turn_by_turn_and_what_was_on_show_is_kept() -> None:
    assist = FakeAssist({3: "dispute-a-charge", 5: "late-payment-fee"}, identity_checked_at=4)

    prediction = follow_call(CALL, assist)

    assert assist.asked == [("T0001", turn) for turn in range(6)]
    assert prediction["script"] == 2
    assert prediction["issue_turn"] == 3
    assert prediction["turns"] == 6
    assert prediction["on_show"] == [
        None,
        None,
        None,
        "dispute-a-charge",
        "dispute-a-charge",
        "late-payment-fee",
    ]
    assert [(change["turn"], change["article"]) for change in prediction["changes"]] == [
        (3, "dispute-a-charge"),
        (5, "late-payment-fee"),
    ]
    assert prediction["changes"][0]["next_step"] == "Tell them the fee is $5."
    assert prediction["changes"][0]["score"] == 0.55
    assert prediction["model_calls"] == 2
    assert prediction["searches"] == 3
    # Every search is kept with what it returned, as names and scores and no text.
    assert [search["turn"] for search in prediction["searched"]] == [1, 3, 5]
    assert prediction["searched"][1]["results"] == [
        ["late-payment-fee", 0.61],
        ["dispute-a-charge", 0.58],
    ]
    assert prediction["identity_checked_at"] == 4
    assert prediction["reminders"] == []
    assert prediction["hand_off"] is None
    # "also" at the issue turn, "best" two turns later.
    best, right = right_for(prediction)
    assert best == "late-payment-fee"
    assert first_turn_with(prediction, right) == 0
    assert first_turn_with(prediction, frozenset({best})) == 2
    assert first_turn_with(prediction, frozenset({"pay-your-bill"})) is None


def test_reminders_the_hint_and_a_withheld_step_are_kept_with_the_prediction() -> None:
    assist = FakeAssist(
        {3: "late-payment-fee"},
        problem=STEP_WITHHELD,
        reminders=[Reminder(rule="card_read_back", title="t", detail="d", turn=4)],
        hand_off=HandOffHint(category="billing", team="the billing team", turn=3),
    )

    prediction = follow_call(CALL, assist)

    assert prediction["reminders"] == [{"rule": "card_read_back", "turn": 4}]
    assert prediction["hand_off"] == {"category": "billing", "team": "the billing team", "turn": 3}
    assert prediction["changes"][0]["next_step"] is None
    assert prediction["changes"][0]["problem"] == STEP_WITHHELD


def test_a_call_whose_script_is_not_found_is_followed_but_has_no_issue_turn() -> None:
    prediction = follow_call({**CALL, "category": "scam"}, FakeAssist({3: "late-payment-fee"}))

    assert prediction["script"] is None
    assert prediction["issue_turn"] is None
    assert prediction["on_show"][3] == "late-payment-fee"


# --- a run --------------------------------------------------------------------------------------


def test_each_call_is_followed_once_with_its_share_of_the_model_work() -> None:
    assist = FakeAssist({3: "late-payment-fee"})
    seen: list[str] = []
    waits: list[float] = []
    calls = [CALL, {**CALL, "transcript_id": "T0404"}, {**CALL, "transcript_id": "T0003"}]
    done = {"T0003": {"transcript_id": "T0003", "category": "billing", "kept": True}}

    predictions = predict(
        calls,
        assist,
        usage=lambda: {"model_calls": assist.calls, "input_tokens": assist.calls * 900},
        done=done,
        on_prediction=lambda prediction: seen.append(prediction["transcript_id"]),
        pause=2.0,
        sleep=waits.append,
    )

    assert [p["transcript_id"] for p in predictions] == ["T0001", "T0404", "T0003"]
    assert predictions[0]["usage"] == {"model_calls": 1, "input_tokens": 900}
    assert predictions[0]["seconds"] >= 0
    # A call that cannot be read is kept with the reason, and the run goes on.
    assert predictions[1]["problem"] == "No transcript was found with the id T0404"
    assert predictions[1]["usage"] == {"model_calls": 0, "input_tokens": 0}
    # A call already done is not asked again, and is not reported again.
    assert predictions[2] == done["T0003"]
    assert seen == ["T0001", "T0404"]
    assert waits == [2.0]


def test_a_failure_that_is_not_about_one_call_stops_the_run() -> None:
    class Unreachable(FakeAssist):
        def turns(self, transcript_id: str) -> list[dict[str, str]]:
            raise ConnectionError("workspace unreachable")

    with pytest.raises(ConnectionError):
        predict([CALL], Unreachable({}))


# --- scoring ------------------------------------------------------------------------------------


def made_up(
    call_id: str,
    on_show: list[str | None],
    *,
    script: tuple[str, int] = ("billing", 2),
    resolution: str = "escalated",
    **more: Any,
) -> dict[str, Any]:
    changes = [
        {
            "turn": turn,
            "article": name,
            "title": name,
            "score": 0.55,
            "next_step": "Tell them the fee is $5 and say why.",
            "unsupported": [],
            "problem": None,
        }
        for turn, name in enumerate(on_show)
        if name is not None and (turn == 0 or on_show[turn - 1] != name)
    ]
    return {
        "transcript_id": call_id,
        "category": script[0],
        "resolution": resolution,
        "script": script[1],
        "issue_turn": 3,
        "turns": len(on_show),
        "on_show": on_show,
        "changes": changes,
        "searches": 4,
        "model_calls": len(changes),
        "identity_checked_at": 6,
        "reminders": [],
        "hand_off": None,
        "usage": {
            "model_calls": len(changes),
            "input_tokens": 900 * len(changes),
            "output_tokens": 30,
        },
        "seconds": 2.5,
        **more,
    }


FEE, DISPUTE, PAY = "late-payment-fee", "dispute-a-charge", "pay-your-bill"
PREDICTIONS = [
    # The best article at the issue turn, and it stays.
    made_up("T0001", [None, None, None, FEE, FEE, FEE]),
    # An "also" article at the issue turn.
    made_up("T0002", [None, None, None, DISPUTE, DISPUTE, DISPUTE]),
    # A wrong article first, a right one two turns later.
    made_up("T0003", [None, None, None, PAY, PAY, FEE]),
    # Nothing at the issue turn, and never a right one.
    made_up("T0004", [None, None, None, None, PAY, PAY], resolution="resolved"),
    # Another script, right at once, with a false alarm and a hint.
    made_up(
        "T0005",
        [None, None, None, "no-service", "no-service", "no-service"],
        script=("troubleshooting", 0),
        resolution="resolved",
        reminders=[{"rule": "card_read_back", "turn": 4}],
        hand_off={"category": "device", "team": "the device support team", "turn": 3},
    ),
    {"transcript_id": "T0404", "category": "billing", "resolution": "resolved", "problem": "gone"},
]


def test_the_article_figures_are_counted_from_the_issue_turn_with_intervals() -> None:
    scores = score(PREDICTIONS)

    assert scores["calls"] == 6
    assert scores["calls_followed"] == 5
    assert scores["calls_not_followed"] == ["T0404"]
    assert scores["calls_whose_script_was_found"] == 5
    found = scores["article"]
    assert found["best_at_the_issue_turn"] == {
        "count": 2,
        "of": 5,
        "rate": 0.4,
        "ci95": list(wilson_interval(2, 5)),
    }
    assert (found["right_at_the_issue_turn"]["count"], found["right_at_the_issue_turn"]["of"]) == (
        3,
        5,
    )
    assert found["nothing_on_show_at_the_issue_turn"]["count"] == 1
    assert found["right_by_the_end_of_the_call"]["count"] == 4
    assert found["never_right"] == 1
    assert found["turns_to_a_right_article"]["by_wait"] == {"0": 3, "2": 1}
    assert found["turns_to_a_right_article"]["median"] == 0
    assert found["turns_to_a_right_article"]["max"] == 2
    assert found["right_within_two_turns"]["count"] == 4
    assert [row["transcript_id"] for row in scores["wrong_at_the_issue_turn"]] == ["T0003", "T0004"]
    assert scores["wrong_at_the_issue_turn"][0]["turns_to_a_right_article"] == 2
    assert scores["wrong_at_the_issue_turn"][1]["on_show"] is None


def test_the_article_figures_are_also_given_without_the_calls_seen_in_a_trial() -> None:
    assert frozenset({"T0001", "T0005"}) <= TRIAL_CALLS
    later = [
        {**prediction, "transcript_id": f"T01{n:02d}"}
        for n, prediction in enumerate(PREDICTIONS[:5])
    ]

    scores = score([*PREDICTIONS[:5], *later])

    assert scores["article"]["right_at_the_issue_turn"]["of"] == 10
    unseen = scores["article_without_the_trial_calls"]
    assert (
        unseen["right_at_the_issue_turn"]["count"],
        unseen["right_at_the_issue_turn"]["of"],
    ) == (3, 5)
    assert unseen == article_scores(later)


def test_cost_reminders_steps_and_the_hint_are_counted() -> None:
    scores = score(PREDICTIONS)

    cost = scores["cost"]
    assert cost["model_calls_per_call"]["by_count"] == {"1": 4, "2": 1}
    assert cost["model_calls_per_call"]["mean"] == 1.2
    assert cost["model_calls_made"] == 6
    assert cost["searches_per_call"]["median"] == 4
    assert cost["input_tokens_per_call"]["max"] == 1800
    assert scores["reminders"]["calls_with_a_reminder"]["count"] == 1
    assert scores["reminders"]["by_rule"] == {"card_read_back": 1}
    assert scores["reminders"]["calls_where_the_identity_check_was_seen"]["count"] == 5
    steps = scores["next_steps"]
    assert (steps["changes_of_article"], steps["written"]) == (6, 6)
    assert steps["declined_by_the_model"] == 0
    assert steps["reading_grade"]["of"] == 6
    hint = scores["hand_off_hint_by_ending"]
    assert (hint["resolved"]["count"], hint["resolved"]["of"]) == (1, 2)
    assert (hint["escalated"]["count"], hint["escalated"]["of"]) == (0, 3)


def test_every_script_has_its_own_line_so_a_miss_can_be_placed() -> None:
    rows = score(PREDICTIONS)["by_script"]

    assert rows == [
        {
            "category": "billing",
            "script": 2,
            "best": "late-payment-fee",
            "calls": 4,
            "best_at_issue": 1,
            "right_at_issue": 2,
            "right_by_the_end": 3,
        },
        {
            "category": "troubleshooting",
            "script": 0,
            "best": "no-service",
            "calls": 1,
            "best_at_issue": 1,
            "right_at_issue": 1,
            "right_by_the_end": 1,
        },
    ]


def test_steps_that_were_declined_withheld_or_flagged_are_told_apart() -> None:
    prediction = made_up("T0001", [None, None, None, FEE, PAY, DISPUTE])
    prediction["changes"][0].update(next_step=None)
    prediction["changes"][1].update(next_step=None, problem=STEP_WITHHELD)
    prediction["changes"][2].update(unsupported=["money"])

    steps = score([prediction])["next_steps"]

    assert steps["written"] == 1
    assert steps["declined_by_the_model"] == 1
    assert steps["withheld_by_the_rule_check"] == 1
    assert steps["failed"] == 0
    assert steps["with_a_figure_in_no_source"] == 1


def test_a_run_with_nothing_followed_has_no_rates() -> None:
    scores = score([PREDICTIONS[-1]])

    assert scores["article"]["right_at_the_issue_turn"] == {
        "count": 0,
        "of": 0,
        "rate": None,
        "ci95": None,
    }
    assert scores["cost"]["model_calls_per_call"]["mean"] is None


def test_the_printed_scores_give_counts_and_intervals_and_say_what_limits_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_scores(score(PREDICTIONS))

    printed = capsys.readouterr().out
    assert "calls followed: 5 of 6" in printed
    assert "the best article: 2/5 (40%, " in printed
    assert "a right article (best or also): 3/5 (60%, " in printed
    assert "calls by turns waited: {'0': 3, '2': 1}" in printed
    assert "without the five calls looked at in a trial" in printed
    assert "calls with a reminder: 1/5" in printed
    assert "billing/2 (late-payment-fee): 4 calls, 1 / 2 / 3" in printed
    assert "copies of 22 scripts" in printed


# --- the command --------------------------------------------------------------------------------


def test_a_result_is_not_saved_from_uncommitted_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(assist_eval, "_git", lambda *args: " M src/copilot/assist.py")

    with pytest.raises(SystemExit) as stopped:
        assist_eval.main(["--save"])

    assert stopped.value.code == 1
    assert "commit first" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [["--save", "--limit", "5"], ["--resume"], ["--limit", "0"]])
def test_a_trial_cannot_be_saved_and_only_a_saved_run_can_be_carried_on(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assist_eval, "_git", lambda *args: "")

    with pytest.raises(SystemExit) as stopped:
        assist_eval.main(arguments)

    assert stopped.value.code == 2
