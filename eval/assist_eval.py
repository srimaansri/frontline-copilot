"""Measure call assist by replaying the redacted calls turn by turn.

Usage:
    python -m eval.assist_eval --limit 5       a trial: five calls, nothing saved
    python -m eval.assist_eval --save          every call, and a result file
    python -m eval.assist_eval --save --resume carry on a run that stopped part way

Each call is followed from its first turn to its last, exactly as the Calls
view's replay follows it (``CallAssist.state`` for every turn), and four things
are reported:

1. How often the article on show is a right one at the turn where the customer
   first states the issue.
2. How many turns it takes for a right article to come up.
3. What a call costs: searches, model calls and tokens.
4. What the reminders say about these calls, in which no rule is broken: any
   reminder here is a false alarm.

What "a right article" means, and who decided it. Every call is a filled-in
copy of one of 22 scripts (``data_gen/transcript_templates.py``): a category
and one way a conversation about it can go. ``RIGHT_ARTICLES`` below names, for
each script, the one help article written for what the customer first says
("best") and the other articles that cover it ("also"). The table was written
by hand by the author of call assist, from the 22 scripts and the titles and
text of the 87 articles, before any call was replayed against the index.
Nobody else has reviewed it. Two figures are given so that the table's
judgement can be seen: "the best article" and "a right article" (best or also).
A call's script is found by matching its turns against each script's first
line; the turn that matches is "the turn where the customer first states the
issue".

How far the numbers reach.

* The calls are 200 copies of 22 scripts, so they are far fewer than 200
  independent tests: if the search misreads one script's first line, it
  misreads every call made from it. The intervals treat the calls as
  independent and are therefore too narrow. The result lists every script
  with its own counts.
* A script's first line is a clean, complete statement of the issue. Real
  customers ramble, and a transcript of real speech has recognition errors.
  These figures are an upper bound on what a live call would give.
* Only the first article is scored. A call moves on (a new phone, then
  voicemail), and nothing here says whether a later change of article was
  right. The count of changes is reported, which is the cost, not the quality.
* The next step is written by a model and is not scored. What is counted: how
  many were written, how many the model declined, how many were withheld by the
  rule check, how many hold a figure that is in neither the article nor the
  call, and their reading grade.
* The hint to hand off is wording rules written with these same scripts in
  view. Its counts by ending are a description, not an accuracy: an ending of
  "escalated" does not mean the customer asked for a change.
* The two thresholds of call assist were set from 14 lines written by hand
  (see ``copilot.assist``). What makes up a search query was changed once, after
  a trial on T0001 to T0005 showed the agent's greeting bringing up an article
  in every call. Those five calls, and the opening and closing lines that all
  200 calls share, were in view for that change: the figures below are not a
  held-out test of it. ``TRIAL_CALLS`` names the five, and the figures are also
  given without them. If the thresholds, the query or the prompt are changed
  again after looking at these calls, the result must say so, and the earlier
  result file is kept.

A reply the workspace refuses for its rate limit is tried again, with a longer
wait each time. With ``--save`` every prediction is written to a progress file
as it is made, so a run that stops can be resumed. ``--save`` refuses to start
from a working tree with uncommitted changes, so the result names the code that
made it.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from copilot.assist import (
    ADOPT_SCORE,
    ASSIST_PROMPT_VERSION,
    SEARCH_TOP_K,
    STEP_FAILED,
    STEP_WITHHELD,
    SWITCH_MARGIN,
    WINDOW_TURNS,
    AssistState,
    search_turns,
)
from copilot.readability import reading_grade
from copilot.schemas import KBHit
from copilot.tools import ToolError
from data_gen.transcript_templates import ISSUES
from eval.redaction_eval import _git
from eval.stats import wilson_interval
from eval.wrapup_eval import _append, read_progress, with_retries

RESULTS_DIR = Path("eval/results")
# T0001 to T0200 are the calls of seed 42, in which no rule is broken.
LAST_SCRIPTED_CALL = 200
# The calls that were looked at in a trial before the search query took its present form.
TRIAL_CALLS: frozenset[str] = frozenset({"T0001", "T0002", "T0003", "T0004", "T0005"})

# (category, the script's place in ISSUES[category]) -> (best, also).
# "best" is the one article written for what the customer first says. "also" are
# other articles that cover it. Written by hand; see the top of this file.
RIGHT_ARTICLES: dict[tuple[str, int], tuple[str, tuple[str, ...]]] = {
    # "My bill is higher than usual this month and I don't understand why."
    ("billing", 0): ("bill-higher-than-expected", ("read-your-bill",)),
    # "I'd like to pay my bill over the phone."
    ("billing", 1): ("pay-your-bill", ()),
    # "There's a late fee on my bill and I always pay on time."
    ("billing", 2): ("late-payment-fee", ("dispute-a-charge",)),
    # "My phone has said no service since yesterday."
    ("troubleshooting", 0): ("no-service", ("sim-not-detected",)),
    # "People tell me their calls go straight to my voicemail."
    ("troubleshooting", 1): ("calls-go-to-voicemail", ()),
    # "My internet on the phone is very slow all of a sudden."
    ("troubleshooting", 2): ("slow-data", ("check-data-usage",)),
    # "I just got a new phone and I need help setting it up."
    ("device_setup", 0): ("activate-a-new-phone", ("bring-your-own-phone",)),
    # "I need to move my contacts and photos from my old phone to my new {device}."
    ("device_setup", 1): ("move-contacts-and-photos", ("back-up-your-phone",)),
    # "I want to switch to a cheaper plan."
    ("plan_change", 0): ("change-your-plan", ("compare-plans", "choose-the-right-plan")),
    # "My grandkids use up all my data. Can I get unlimited?"
    ("plan_change", 1): (
        "unlimited-data-explained",
        ("compare-plans", "choose-the-right-plan", "change-your-plan", "data-top-up"),
    ),
    # "I'd like to add a line for my husband."
    ("add_line", 0): ("add-a-line", ("two-line-unlimited",)),
    # "Can I put my daughter on my plan?"
    ("add_line", 1): ("add-a-line", ("two-line-unlimited",)),
    # "I'm going to {country} next month. Will my phone work there?"
    ("international", 0): ("before-you-travel", ("international-day-pass", "canada-and-mexico")),
    # "How much does it cost to call my son in {country}?"
    ("international", 1): ("international-calling-pack", ("canada-and-mexico",)),
    # "My phone was stolen this morning. I need it turned off right away."
    ("lost_stolen", 0): ("lost-or-stolen-phone", ("device-protection",)),
    # "I lost my phone at the grocery store yesterday."
    ("lost_stolen", 1): ("lost-or-stolen-phone", ("device-protection",)),
    # "I want to cancel my service and move my number to another company."
    ("cancel_port", 0): ("transfer-number-away", ("cancel-service",)),
    # "My husband passed away and I need to cancel his line."
    ("cancel_port", 1): ("deceased-account-holder", ("cancel-service",)),
    # "I wear hearing aids and I can't hear well on my new phone."
    ("accessibility", 0): (
        "hearing-aid-compatibility",
        ("pair-hearing-aids", "accessibility-services"),
    ),
    # "The words on my screen are too small to read."
    ("accessibility", 1): ("make-text-larger", ("accessibility-services",)),
    # "I got a text saying my account is locked and to click a link. Is that from you?"
    ("scam", 0): ("spot-a-scam-text", ()),
    # "Someone called claiming to be from Northline and asked for my Social Security number."
    ("scam", 1): ("scam-calls", ("your-account-privacy",)),
}  # fmt: skip

_SLOT_RE = re.compile(r"\{[a-z_0-9]+\}")


# --- which script a call was made from ----------------------------------------------------------


def _line_re(template: str) -> re.Pattern[str]:
    """A script line as a pattern: its fixed words, with anything where a slot is."""
    fixed = [re.escape(part) for part in _SLOT_RE.split(template)]
    return re.compile(".+?".join(fixed), re.IGNORECASE | re.DOTALL)


_FIRST_LINES: dict[tuple[str, int], re.Pattern[str]] = {
    (category, number): _line_re(issue.intro[0][1])
    for category, issues in ISSUES.items()
    for number, issue in enumerate(issues)
}


def script_of(category: str, turns: Sequence[Mapping[str, str]]) -> tuple[int, int] | None:
    """Which script of ``category`` a call was made from, and the turn its first line is at.

    Returns:
        The script's place in ``ISSUES[category]`` and the index of the turn, or
        None when no customer turn is the first line of any script of the category.
    """
    for index, turn in enumerate(turns):
        if turn.get("speaker") != "customer":
            continue
        for (name, number), pattern in _FIRST_LINES.items():
            if name == category and pattern.fullmatch(turn.get("text", "").strip()):
                return number, index
    return None


def is_scripted_call(call: Mapping[str, str]) -> bool:
    """Whether a call is one of the 200 in which no rule is broken (T0001 to T0200).

    Later ids are the calls written to break a rule (``data_gen/synth_breaches.py``).
    They belong to the compliance measurement, and a reminder on one is not a false alarm.
    """
    number = call["transcript_id"][1:]
    return call["category"] in ISSUES and number.isdigit() and int(number) <= LAST_SCRIPTED_CALL


def slug(url: str | None) -> str | None:
    """The last part of an article's address, which is how the table names an article."""
    return None if url is None else url.rstrip("/").rsplit("/", 1)[-1]


# --- following one call -------------------------------------------------------------------------


class Follows(Protocol):
    """The parts of ``CallAssist`` the measurement uses."""

    def turns(self, transcript_id: str) -> list[dict[str, str]]:
        """The redacted turns of one call."""
        ...

    def state(self, transcript_id: str, turn: int) -> AssistState:
        """What the panel shows at one turn."""
        ...

    def results(self, transcript_id: str, turn: int) -> Sequence[KBHit]:
        """The articles the search at one turn returned, best first."""
        ...


def follow_call(call: Mapping[str, str], assist: Follows) -> dict[str, Any]:
    """Replay one call through call assist and keep what it showed at every turn.

    What is kept was written from redacted text and has passed the output
    check, so it holds nothing the redacted table does not: article titles and
    addresses, fixed words from the rules, and each next step.
    """
    call_id, category = call["transcript_id"], call["category"]
    turns = assist.turns(call_id)
    found = script_of(category, turns)
    states = [assist.state(call_id, turn) for turn in range(len(turns))]
    last = states[-1] if states else None
    on_show = [slug(state.article.url) if state.article else None for state in states]
    changes: list[dict[str, Any]] = []
    for state in states:
        if state.article is None or state.article.since_turn != state.turn:
            continue
        step = state.next_step
        changes.append(
            {
                "turn": state.turn,
                "article": slug(state.article.url),
                "title": state.article.title,
                "score": state.article.score,
                "next_step": step.text if step else None,
                "unsupported": list(step.unsupported) if step else [],
                "problem": state.step_problem,
            }
        )
    prediction: dict[str, Any] = {
        "transcript_id": call_id,
        "category": category,
        "resolution": call.get("resolution"),
        "script": None if found is None else found[0],
        "issue_turn": None if found is None else found[1],
        "turns": len(turns),
        # The article on show at each turn, by the last part of its address.
        "on_show": on_show,
        "changes": changes,
        "searches": last.cost.searches if last else 0,
        # What each search returned, best first, as [article, score]. With these the
        # two thresholds can be studied afterwards without searching again.
        "searched": [
            {
                "turn": turn,
                "results": [[slug(hit.url), hit.score] for hit in assist.results(call_id, turn)],
            }
            for turn in search_turns(turns, len(turns) - 1)
        ],
        "model_calls": last.cost.model_calls if last else 0,
        "identity_checked_at": last.identity_checked_at if last else None,
        "reminders": [
            {"rule": reminder.rule, "turn": reminder.turn}
            for reminder in (last.reminders if last else [])
        ],
        "hand_off": last.hand_off.model_dump() if last and last.hand_off else None,
    }
    return prediction


def predict(
    calls: Iterable[Mapping[str, str]],
    assist: Follows,
    *,
    usage: Callable[[], Mapping[str, int]] | None = None,
    done: Mapping[str, Mapping[str, Any]] | None = None,
    on_prediction: Callable[[Mapping[str, Any]], None] | None = None,
    pause: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Follow each call and return what call assist showed.

    Args:
        calls: Each call's ``transcript_id``, ``category`` and ``resolution``.
        assist: Call assist, or anything that follows a call as it does.
        usage: Returns the running totals of model calls and tokens. The
            difference across one call is kept with its prediction.
        done: Predictions from an earlier part of the same run, by call id.
        on_prediction: Called with each new prediction as soon as it is made.
        pause: Seconds to wait between calls, to stay under a shared rate limit.
        sleep: Stands in for ``time.sleep`` in tests.

    A call that cannot be read is kept, with the reason and nothing scored. A
    failure that is not about one call, such as the workspace being
    unreachable, stops the run.
    """
    predictions: list[dict[str, Any]] = []
    asked = 0
    for call in calls:
        call_id = call["transcript_id"]
        if done and call_id in done:
            predictions.append(dict(done[call_id]))
            continue
        if asked and pause > 0:
            sleep(pause)
        asked += 1
        started = time.perf_counter()
        before = dict(usage()) if usage else {}
        try:
            prediction = follow_call(call, assist)
        except ToolError as error:
            # A tool's message is safe to keep: it names an id or a count, never text.
            prediction = {
                "transcript_id": call_id,
                "category": call["category"],
                "resolution": call.get("resolution"),
                "problem": str(error),
            }
        if usage:
            after = usage()
            prediction["usage"] = {key: after[key] - before.get(key, 0) for key in after}
        prediction["seconds"] = round(time.perf_counter() - started, 2)
        predictions.append(prediction)
        if on_prediction is not None:
            on_prediction(prediction)
    return predictions


# --- scoring ------------------------------------------------------------------------------------


def _rate(count: int, of: int) -> dict[str, Any]:
    if of == 0:
        return {"count": 0, "of": 0, "rate": None, "ci95": None}
    return {"count": count, "of": of, "rate": count / of, "ci95": list(wilson_interval(count, of))}


def _spread(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"of": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "of": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def right_for(prediction: Mapping[str, Any]) -> tuple[str, frozenset[str]]:
    """The best article for a prediction's script, and every right one (best and also)."""
    best, also = RIGHT_ARTICLES[(prediction["category"], prediction["script"])]
    return best, frozenset({best, *also})


def first_turn_with(prediction: Mapping[str, Any], wanted: frozenset[str]) -> int | None:
    """How many turns after the issue turn an article in ``wanted`` is first on show.

    0 means it was on show at the issue turn itself. None means it never came up.
    """
    start = prediction["issue_turn"]
    for turn in range(start, len(prediction["on_show"])):
        if prediction["on_show"][turn] in wanted:
            return int(turn - start)
    return None


def article_scores(placed: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How often, and how soon, a right article was on show, for calls whose script is known."""
    best_at_issue = right_at_issue = nothing_at_issue = 0
    waits: list[int] = []
    for p in placed:
        best, right = right_for(p)
        shown = p["on_show"][p["issue_turn"]]
        wait = first_turn_with(p, right)
        best_at_issue += shown == best
        right_at_issue += shown in right
        nothing_at_issue += shown is None
        if wait is not None:
            waits.append(wait)
    return {
        "best_at_the_issue_turn": _rate(best_at_issue, len(placed)),
        "right_at_the_issue_turn": _rate(right_at_issue, len(placed)),
        "nothing_on_show_at_the_issue_turn": _rate(nothing_at_issue, len(placed)),
        "right_by_the_end_of_the_call": _rate(len(waits), len(placed)),
        "never_right": len(placed) - len(waits),
        # Turns after the issue turn until a right article was on show, for the
        # calls in which one came up. 0 is the issue turn itself.
        "turns_to_a_right_article": {
            **_spread(waits),
            "by_wait": {str(wait): count for wait, count in sorted(Counter(waits).items())},
        },
        "right_within_two_turns": _rate(sum(wait <= 2 for wait in waits), len(placed)),
    }


def score(predictions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every figure the measurement reports, from the saved predictions alone."""
    followed = [p for p in predictions if "problem" not in p]
    placed = [p for p in followed if p["script"] is not None]
    by_script: dict[tuple[str, int], dict[str, int]] = {}
    for p in placed:
        best, right = right_for(p)
        shown = p["on_show"][p["issue_turn"]]
        wait = first_turn_with(p, right)
        row = by_script.setdefault(
            (p["category"], p["script"]),
            {"calls": 0, "best_at_issue": 0, "right_at_issue": 0, "right_by_the_end": 0},
        )
        row["calls"] += 1
        row["best_at_issue"] += shown == best
        row["right_at_issue"] += shown in right
        row["right_by_the_end"] += wait is not None
    steps = [change for p in followed for change in p["changes"]]
    written = [change["next_step"] for change in steps if change["next_step"]]
    flagged = Counter(reminder["rule"] for p in followed for reminder in p["reminders"])
    endings = sorted({str(p["resolution"]) for p in followed})
    usage = [p["usage"] for p in followed if "usage" in p]
    return {
        "calls": len(predictions),
        "calls_followed": len(followed),
        "calls_not_followed": [p["transcript_id"] for p in predictions if "problem" in p],
        "calls_whose_script_was_found": len(placed),
        "article": article_scores(placed),
        # The same figures without the five calls that were looked at in a trial. Their
        # scripts, and the opening lines of every call, are still in the other calls.
        "article_without_the_trial_calls": article_scores(
            [p for p in placed if p["transcript_id"] not in TRIAL_CALLS]
        ),
        "cost": {
            "model_calls_per_call": {
                **_spread([p["model_calls"] for p in followed]),
                "by_count": {
                    str(count): calls
                    for count, calls in sorted(Counter(p["model_calls"] for p in followed).items())
                },
            },
            "searches_per_call": _spread([p["searches"] for p in followed]),
            "turns_per_call": _spread([p["turns"] for p in followed]),
            # What the model client counted during the run.
            "model_calls_made": sum(item.get("model_calls", 0) for item in usage),
            "input_tokens_per_call": _spread([item.get("input_tokens", 0) for item in usage]),
            "output_tokens_per_call": _spread([item.get("output_tokens", 0) for item in usage]),
            "calls_without_token_counts": sum(
                item.get("calls_without_counts", 0) for item in usage
            ),
            "seconds_per_call": _spread([p["seconds"] for p in followed if "seconds" in p]),
        },
        "reminders": {
            # No rule is broken in these calls, so every reminder is a false alarm.
            "calls_with_a_reminder": _rate(
                sum(bool(p["reminders"]) for p in followed), len(followed)
            ),
            "by_rule": dict(sorted(flagged.items())),
            "calls_where_the_identity_check_was_seen": _rate(
                sum(p["identity_checked_at"] is not None for p in followed), len(followed)
            ),
        },
        "next_steps": {
            "changes_of_article": len(steps),
            "written": len(written),
            "declined_by_the_model": sum(
                not change["next_step"] and not change["problem"] for change in steps
            ),
            "withheld_by_the_rule_check": sum(
                change["problem"] == STEP_WITHHELD for change in steps
            ),
            "failed": sum(change["problem"] == STEP_FAILED for change in steps),
            "with_a_figure_in_no_source": sum(bool(change["unsupported"]) for change in steps),
            "reading_grade": _spread([round(reading_grade(text), 1) for text in written]),
        },
        # A description, not an accuracy: see the top of this file.
        "hand_off_hint_by_ending": {
            ending: _rate(
                sum(p["hand_off"] is not None for p in followed if p["resolution"] == ending),
                sum(p["resolution"] == ending for p in followed),
            )
            for ending in endings
        },
        "by_script": [
            {
                "category": category,
                "script": number,
                "best": RIGHT_ARTICLES[(category, number)][0],
                **row,
            }
            for (category, number), row in sorted(by_script.items())
        ],
        "wrong_at_the_issue_turn": [
            {
                "transcript_id": p["transcript_id"],
                "category": p["category"],
                "script": p["script"],
                "on_show": p["on_show"][p["issue_turn"]],
                "turns_to_a_right_article": first_turn_with(p, right_for(p)[1]),
            }
            for p in placed
            if p["on_show"][p["issue_turn"]] not in right_for(p)[1]
        ],
    }


# --- printing -----------------------------------------------------------------------------------


def _line(label: str, rate: Mapping[str, Any]) -> str:
    if rate["rate"] is None:
        return f"{label}: none"
    low, high = rate["ci95"]
    return f"{label}: {rate['count']}/{rate['of']} ({rate['rate']:.0%}, {low:.0%}-{high:.0%})"


def _spread_line(label: str, spread: Mapping[str, Any]) -> str:
    if not spread["of"]:
        return f"{label}: none"
    return (
        f"{label}: mean {spread['mean']}, median {spread['median']}, "
        f"{spread['min']} to {spread['max']}"
    )


def print_scores(scores: Mapping[str, Any]) -> None:
    """Print the scores for a person to read. Counts and labels only, never transcript text."""
    print(f"\ncalls followed: {scores['calls_followed']} of {scores['calls']}")
    if scores["calls_not_followed"]:
        print(f"could not be read: {', '.join(scores['calls_not_followed'])}")
    print(f"calls whose script was found: {scores['calls_whose_script_was_found']}")

    article = scores["article"]
    print("\nthe article on show at the turn the customer first states the issue")
    print("  " + _line("the best article", article["best_at_the_issue_turn"]))
    print("  " + _line("a right article (best or also)", article["right_at_the_issue_turn"]))
    print("  " + _line("nothing on show", article["nothing_on_show_at_the_issue_turn"]))
    print("\nhow long a right article takes")
    print("  " + _line("on show by the end of the call", article["right_by_the_end_of_the_call"]))
    print("  " + _line("on show within two turns", article["right_within_two_turns"]))
    waits = article["turns_to_a_right_article"]
    print("  " + _spread_line("turns after the issue turn, where one came up", waits))
    print(f"  calls by turns waited: {waits['by_wait']}")
    unseen = scores["article_without_the_trial_calls"]
    print("\nthe same, without the five calls looked at in a trial (T0001 to T0005)")
    print("  " + _line("the best article", unseen["best_at_the_issue_turn"]))
    print("  " + _line("a right article (best or also)", unseen["right_at_the_issue_turn"]))
    print("  " + _line("on show by the end of the call", unseen["right_by_the_end_of_the_call"]))

    cost = scores["cost"]
    print("\nwhat a call costs")
    print("  " + _spread_line("model calls", cost["model_calls_per_call"]))
    print(f"  calls by model calls: {cost['model_calls_per_call']['by_count']}")
    print("  " + _spread_line("searches", cost["searches_per_call"]))
    print("  " + _spread_line("turns", cost["turns_per_call"]))
    print("  " + _spread_line("input tokens", cost["input_tokens_per_call"]))
    print("  " + _spread_line("output tokens", cost["output_tokens_per_call"]))
    print("  " + _spread_line("seconds to follow a whole call", cost["seconds_per_call"]))

    reminders = scores["reminders"]
    print("\nreminders on calls in which no rule is broken")
    print("  " + _line("calls with a reminder", reminders["calls_with_a_reminder"]))
    if reminders["by_rule"]:
        print(f"  by rule: {reminders['by_rule']}")
    print("  " + _line("identity check seen", reminders["calls_where_the_identity_check_was_seen"]))

    steps = scores["next_steps"]
    print("\nnext steps (counted, not scored)")
    print(
        f"  changes of article {steps['changes_of_article']}: written {steps['written']}, "
        f"declined by the model {steps['declined_by_the_model']}, "
        f"withheld by the rule check {steps['withheld_by_the_rule_check']}, "
        f"failed {steps['failed']}"
    )
    print(f"  with a figure in no source: {steps['with_a_figure_in_no_source']}")
    print("  " + _spread_line("reading grade", steps["reading_grade"]))

    print("\nhint to hand off, by how the generator says the call ended (a description)")
    for ending, rate in scores["hand_off_hint_by_ending"].items():
        print("  " + _line(ending, rate))

    print("\nby script (best at the issue turn / right at the issue turn / right by the end)")
    for row in scores["by_script"]:
        print(
            f"  {row['category']}/{row['script']} ({row['best']}): {row['calls']} calls, "
            f"{row['best_at_issue']} / {row['right_at_issue']} / {row['right_by_the_end']}"
        )
    print(
        "\nThe intervals treat the calls as independent. They are copies of 22 scripts, "
        "so the true ranges are wider."
    )


# --- the command --------------------------------------------------------------------------------


class _Retried:
    """A model or a retriever whose calls are tried again after a rate limit."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def invoke(self, messages: Any) -> Any:
        return with_retries(lambda: self._inner.invoke(messages))[0]

    def bind_tools(self, tools: Any) -> Any:
        return self._inner.bind_tools(tools)

    def search(self, question: str, *, top_k: int | None = None, section: str | None = None) -> Any:
        return with_retries(lambda: self._inner.search(question, top_k=top_k, section=section))[0]


class _Parts:
    """The copilot's tools as call assist borrows them, each call retried after a rate limit."""

    def __init__(self, tools: Any) -> None:
        self.settings = tools.settings
        self.redactor = tools.redactor
        self.retriever = _Retried(tools.retriever)
        self.llm = _Retried(tools.llm)
        self._sql = tools.sql

    def sql(self, statement: str, parameters: Any) -> Any:
        return with_retries(lambda: self._sql(statement, parameters))[0]


def main(argv: list[str] | None = None) -> None:
    """Follow the redacted calls with call assist and report what it showed."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--limit", type=int, default=None, help="follow this many, save nothing")
    parser.add_argument("--save", action="store_true", help="write a result file")
    parser.add_argument("--resume", action="store_true", help="carry on an unfinished --save run")
    parser.add_argument(
        "--pause", type=float, default=2.0, help="seconds between calls (default 2)"
    )
    parser.add_argument(
        "--show-steps",
        action="store_true",
        help="print each change of article and its next step; they are written from "
        "redacted synthetic calls",
    )
    parser.add_argument(
        "--states-out",
        type=Path,
        default=None,
        help="also write every turn's full state to this file, for looking at the interface",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.save and args.limit is not None:
        parser.error("--limit is a trial; it cannot be saved")
    if args.resume and not args.save:
        parser.error("--resume carries on a --save run")
    dirty = bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results"))
    if args.save and dirty:
        print("not started: commit first, so the result names the code that made it")
        raise SystemExit(1)

    # Imported here so that --help and the tests do not load the model stack.
    import mlflow
    from dotenv import load_dotenv

    from copilot.assist import CallAssist
    from copilot.config import load_settings
    from copilot.tools import Tools
    from copilot.transcripts import list_transcripts

    load_dotenv()
    settings = load_settings()
    # These are measurements, not an agent's work: they are not traced.
    mlflow.tracing.disable()
    parts = _Parts(Tools(settings))
    assist = CallAssist(parts)
    name = settings.llm_endpoint.removeprefix("databricks-")
    run = {
        "git_sha": _git("rev-parse", "HEAD"),
        "assist_prompt_version": ASSIST_PROMPT_VERSION,
        "llm_endpoint": settings.llm_endpoint,
        "query_type": settings.query_type,
        "chunk_config": settings.chunk_config,
        "window_turns": WINDOW_TURNS,
        "search_top_k": SEARCH_TOP_K,
        "adopt_score": ADOPT_SCORE,
        "switch_margin": SWITCH_MARGIN,
    }

    calls = [call for call in list_transcripts(parts.sql, settings) if is_scripted_call(call)]
    chosen = calls[: args.limit] if args.limit else calls
    progress = RESULTS_DIR / f"assist_{name}.progress.jsonl"
    done: dict[str, dict[str, Any]] = {}
    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        if progress.exists() and not args.resume:
            print(
                f"not started: {progress.as_posix()} holds an unfinished run. "
                "Add --resume to carry on, or delete it to start again."
            )
            raise SystemExit(1)
        done = read_progress(progress, run)
        if not progress.exists():
            _append(progress, run)
        if done:
            print(f"carrying on: {len(done)} of {len(chosen)} calls are already done")

    def report(prediction: Mapping[str, Any]) -> None:
        if args.save:
            _append(progress, prediction)
        call_id = prediction["transcript_id"]
        if "problem" in prediction:
            print(f"  {call_id} not followed: {prediction['problem']}", flush=True)
            return
        if prediction["script"] is None:
            placed = "script not found"
        else:
            best, right = right_for(prediction)
            shown = prediction["on_show"][prediction["issue_turn"]]
            wait = first_turn_with(prediction, right)
            verdict = "best" if shown == best else "right" if shown in right else "WRONG"
            placed = (
                f"{prediction['category']}/{prediction['script']} issue at turn "
                f"{prediction['issue_turn']}: {shown} ({verdict}); "
                f"right after {wait if wait is not None else 'never'}"
            )
        print(
            f"  {call_id} {prediction['seconds']:.1f}s  {placed}; "
            f"model calls {prediction['model_calls']}, searches {prediction['searches']}, "
            f"reminders {len(prediction['reminders'])}",
            flush=True,
        )
        if args.show_steps:
            for change in prediction["changes"]:
                step = change["next_step"] or change["problem"] or "(the model declined)"
                print(f"      turn {change['turn']} {change['article']} {change['score']}: {step}")

    predictions = predict(
        chosen,
        assist,
        usage=lambda: assist.usage.model_dump(),
        done=done,
        on_prediction=report,
        pause=args.pause,
    )
    if args.states_out is not None:
        # Asked again from memory: nothing is searched or written twice.
        states = {
            p["transcript_id"]: [
                assist.state(p["transcript_id"], turn).model_dump() for turn in range(p["turns"])
            ]
            for p in predictions
            if "problem" not in p
        }
        args.states_out.write_text(json.dumps(states, indent=1) + "\n", encoding="utf-8")
        print(f"wrote the states of {len(states)} calls to {args.states_out.as_posix()}")
    scores = score(predictions)
    print_scores(scores)
    if not args.save:
        print("\nnothing saved" + (" (--limit)" if args.limit else ""))
        return
    result = {
        "scored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **run,
        "llm_temperature": settings.llm_temperature,
        "truth": "RIGHT_ARTICLES in eval/assist_eval.py: one best article and the others that "
        "cover it, for each of the 22 scripts, written by hand by the author of call assist",
        "calls_are_independent": False,
        **scores,
        "predictions": predictions,
    }
    path = RESULTS_DIR / f"assist_{result['scored_at'][:10]}_{name}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    progress.unlink()
    print(f"saved {path.as_posix()}")


if __name__ == "__main__":
    main()
