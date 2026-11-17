"""The wrap-up measurement's own arithmetic and its handling of a run. No network, no model."""

import json
from pathlib import Path
from typing import Any, get_args

import pytest

import eval.wrapup_eval as wrapup_eval
from copilot.schemas import CallWrapUp
from copilot.tools import ToolError
from data_gen.transcript_templates import CATEGORY_WEIGHTS, ISSUES, Resolution
from eval.stats import wilson_interval
from eval.wrapup_eval import (
    CATEGORIES,
    DISPOSITIONS,
    NO_ANSWER,
    is_rate_limit,
    measured_calls,
    predict,
    print_scores,
    read_progress,
    score,
    score_label,
    with_retries,
)

CALLS = [
    {"transcript_id": "T0001", "category": "billing", "resolution": "escalated"},
    {"transcript_id": "T0002", "category": "troubleshooting", "resolution": "resolved"},
    {"transcript_id": "T0003", "category": "troubleshooting", "resolution": "unresolved"},
    {"transcript_id": "T0004", "category": "scam", "resolution": "resolved"},
]


def wrap_up(call_id: str, disposition: str, category: str) -> CallWrapUp:
    return CallWrapUp.model_validate(
        {
            "transcript_id": call_id,
            "disposition": disposition,
            "category": category,
            "notes": ["The customer asked about <PERSON_1>'s line."],
            "sentiment": "neutral",
        }
    )


def prediction(
    call_id: str, truth: tuple[str, str], said: tuple[str, str] | None
) -> dict[str, Any]:
    return {
        "transcript_id": call_id,
        "truth": {"disposition": truth[0], "category": truth[1]},
        "predicted": None if said is None else {"disposition": said[0], "category": said[1]},
    }


class RateLimitedError(Exception):
    """Stands in for the model client's error for HTTP 429."""

    status_code = 429


# --- the labels ---------------------------------------------------------------------------------


def test_only_the_200_ordinary_calls_are_measured() -> None:
    listed = [
        *CALLS,
        {"transcript_id": "T0200", "category": "billing", "resolution": "resolved"},
        # The calls with a seeded rule breach share the table and are left out.
        {"transcript_id": "T0201", "category": "billing", "resolution": "resolved"},
        {"transcript_id": "T0582", "category": "scam", "resolution": "escalated"},
    ]

    assert [call["transcript_id"] for call in measured_calls(listed)] == [
        "T0001",
        "T0002",
        "T0003",
        "T0004",
        "T0200",
    ]


def test_the_measurement_scores_the_labels_the_generator_writes() -> None:
    assert set(DISPOSITIONS) == set(get_args(Resolution))
    assert set(CATEGORIES) == set(CATEGORY_WEIGHTS)
    # Every script's ending is one of the three, so no call has a label that cannot be predicted.
    assert {issue.resolution for issues in ISSUES.values() for issue in issues} <= set(DISPOSITIONS)


# --- scoring ------------------------------------------------------------------------------------


def test_one_label_is_scored_with_an_interval_for_each_class_and_a_matrix() -> None:
    pairs = [
        ("resolved", "resolved"),
        ("resolved", "resolved"),
        ("resolved", "unresolved"),
        ("escalated", "escalated"),
        ("unresolved", "resolved"),
        ("unresolved", None),
    ]

    result = score_label(pairs, DISPOSITIONS)

    assert result["accuracy"]["count"] == 3
    assert result["accuracy"]["of"] == 6
    assert result["accuracy"]["rate"] == 0.5
    assert result["accuracy"]["ci95"] == list(wilson_interval(3, 6))
    assert result["by_class"]["resolved"]["recall"]["count"] == 2
    assert result["by_class"]["resolved"]["recall"]["of"] == 3
    assert result["by_class"]["resolved"]["recall"]["ci95"] == list(wilson_interval(2, 3))
    # Three calls were called resolved, and two of them were.
    assert result["by_class"]["resolved"]["precision"]["count"] == 2
    assert result["by_class"]["resolved"]["precision"]["of"] == 3
    assert result["by_class"]["unresolved"]["recall"]["count"] == 0
    assert result["by_class"]["unresolved"]["recall"]["of"] == 2
    assert result["confusion"] == {
        "resolved": {"resolved": 2, "escalated": 0, "unresolved": 1, NO_ANSWER: 0},
        "escalated": {"resolved": 0, "escalated": 1, "unresolved": 0, NO_ANSWER: 0},
        "unresolved": {"resolved": 1, "escalated": 0, "unresolved": 0, NO_ANSWER: 1},
    }
    # Every call is in the matrix exactly once.
    assert sum(sum(row.values()) for row in result["confusion"].values()) == len(pairs)


def test_a_class_with_no_calls_has_no_rate_and_no_interval() -> None:
    result = score_label([("resolved", "resolved")], DISPOSITIONS)

    assert result["by_class"]["escalated"]["recall"] == {
        "count": 0,
        "of": 0,
        "rate": None,
        "ci95": None,
    }
    assert result["accuracy"]["ci95"] == list(wilson_interval(1, 1))


def test_both_labels_are_scored_and_a_call_with_no_draft_is_wrong_on_both() -> None:
    predictions = [
        prediction("T0001", ("escalated", "billing"), ("escalated", "billing")),
        prediction("T0002", ("resolved", "troubleshooting"), ("resolved", "device_setup")),
        prediction("T0003", ("unresolved", "troubleshooting"), ("resolved", "troubleshooting")),
        prediction("T0004", ("resolved", "scam"), None),
        prediction("T0005", ("resolved", "troubleshooting"), ("resolved", "troubleshooting")),
    ]

    result = score(predictions)

    assert result["calls"] == 5
    assert result["no_answer"] == 1
    assert (
        result["disposition"]["accuracy"]["count"],
        result["disposition"]["accuracy"]["of"],
    ) == (
        3,
        5,
    )
    assert (result["category"]["accuracy"]["count"], result["category"]["accuracy"]["of"]) == (3, 5)
    assert (result["both_right"]["count"], result["both_right"]["of"]) == (2, 5)
    assert result["category"]["confusion"]["scam"][NO_ANSWER] == 1
    assert result["category"]["confusion"]["troubleshooting"]["device_setup"] == 1
    assert [item["transcript_id"] for item in result["wrong"]] == ["T0002", "T0003", "T0004"]
    assert result["wrong"][2]["said"] == {"disposition": None, "category": None}
    # One line for each pair of category and ending, so a script that is always
    # misread shows up as a line with nothing right.
    assert result["by_kind_of_call"] == [
        {
            "category": "billing",
            "disposition": "escalated",
            "calls": 1,
            "disposition_right": 1,
            "category_right": 1,
        },
        {
            "category": "scam",
            "disposition": "resolved",
            "calls": 1,
            "disposition_right": 0,
            "category_right": 0,
        },
        {
            "category": "troubleshooting",
            "disposition": "resolved",
            "calls": 2,
            "disposition_right": 2,
            "category_right": 1,
        },
        {
            "category": "troubleshooting",
            "disposition": "unresolved",
            "calls": 1,
            "disposition_right": 0,
            "category_right": 1,
        },
    ]
    # The result must not look like an agent evaluation run to the report builder.
    assert "per_row" not in result
    assert "metrics" not in result


def test_the_printed_scores_give_counts_intervals_and_the_matrix(
    capsys: pytest.CaptureFixture[str],
) -> None:
    predictions = [
        prediction("T0001", ("escalated", "billing"), ("escalated", "billing")),
        prediction("T0003", ("unresolved", "troubleshooting"), ("resolved", "troubleshooting")),
        prediction("T0004", ("resolved", "scam"), None),
    ]

    print_scores(score(predictions))

    printed = capsys.readouterr().out
    assert "calls scored: 3" in printed
    assert "calls with no usable draft (counted as wrong): 1" in printed
    assert "disposition right: 1/3 (33%, 6%-79%)" in printed
    assert "category right: 2/3 (67%, 21%-94%)" in printed
    assert "both right on the same call: 1/3" in printed
    assert "troubleshooting / unresolved: 1 calls, disposition right 0, category right 1" in printed
    assert "the true ranges are wider" in printed
    # A column nobody was placed in is left out of the printed matrix.
    assert "device_setup" not in printed
    assert NO_ANSWER in printed


# --- rate limits --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        RateLimitedError("slow down"),
        RuntimeError("Error code: 429 - REQUEST_LIMIT_EXCEEDED"),
        RuntimeError("Rate limit reached for the endpoint"),
        type("TooManyRequests", (Exception,), {})("try later"),
        type("RateLimitError", (Exception,), {})(""),
    ],
)
def test_a_rate_limit_is_recognised_however_it_is_reported(error: Exception) -> None:
    assert is_rate_limit(error)


@pytest.mark.parametrize(
    "error", [ToolError("The model did not return a JSON object"), TimeoutError("timed out")]
)
def test_other_failures_are_not_taken_for_a_rate_limit(error: Exception) -> None:
    assert not is_rate_limit(error)


def test_a_rate_limited_call_is_tried_again_with_a_longer_wait_each_time() -> None:
    failures = [RateLimitedError(), RateLimitedError(), RateLimitedError()]
    naps: list[float] = []

    def call() -> str:
        if failures:
            raise failures.pop()
        return "done"

    result = with_retries(call, first_wait=5.0, longest_wait=15.0, sleep=naps.append)

    assert result == ("done", 4)
    assert naps == [5.0, 10.0, 15.0]


def test_retrying_gives_up_after_the_last_try_and_never_retries_another_failure() -> None:
    naps: list[float] = []
    calls: list[int] = []

    def always_limited() -> None:
        calls.append(1)
        raise RateLimitedError

    with pytest.raises(RateLimitedError):
        with_retries(always_limited, attempts=3, sleep=naps.append)
    assert len(calls) == 3
    assert len(naps) == 2

    def broken() -> None:
        calls.append(1)
        raise ToolError("The model did not return a JSON object")

    calls.clear()
    with pytest.raises(ToolError):
        with_retries(broken, sleep=naps.append)
    assert len(calls) == 1


# --- a run --------------------------------------------------------------------------------------


def test_each_call_is_drafted_from_its_id_and_paired_with_the_generators_labels() -> None:
    asked: list[str] = []
    seen: list[str] = []
    naps: list[float] = []

    def draft(call_id: str) -> CallWrapUp:
        asked.append(call_id)
        if call_id == "T0003":
            raise ToolError("The model's wrap-up did not have the expected fields")
        return wrap_up(call_id, "resolved", "troubleshooting")

    predictions = predict(
        CALLS,
        draft,
        on_prediction=lambda item: seen.append(item["transcript_id"]),
        pause=2.0,
        sleep=naps.append,
    )

    # The draft is asked for by id alone: the labels never go near it.
    assert asked == ["T0001", "T0002", "T0003", "T0004"]
    assert seen == asked
    assert naps == [2.0, 2.0, 2.0]
    assert predictions[0]["truth"] == {"disposition": "escalated", "category": "billing"}
    assert predictions[0]["predicted"]["disposition"] == "resolved"
    assert predictions[0]["predicted"]["notes"] == ["The customer asked about <PERSON_1>'s line."]
    assert "transcript_id" not in predictions[0]["predicted"]
    assert predictions[0]["tries"] == 1
    # A reply that could not be used is kept as a call with no draft, and the run goes on.
    assert predictions[2]["predicted"] is None
    assert predictions[2]["problem"] == "The model's wrap-up did not have the expected fields"
    assert predictions[3]["predicted"] is not None
    assert score(predictions)["no_answer"] == 1
    json.dumps(predictions)


def test_a_rate_limit_in_the_middle_of_a_run_is_waited_out() -> None:
    failures = {"T0002": [RateLimitedError()]}
    naps: list[float] = []

    def draft(call_id: str) -> CallWrapUp:
        if failures.get(call_id):
            raise failures[call_id].pop()
        return wrap_up(call_id, "resolved", "billing")

    predictions = predict(CALLS[:2], draft, sleep=naps.append)

    assert [item["tries"] for item in predictions] == [1, 2]
    assert naps == [5.0]


def test_a_failure_that_is_not_about_one_reply_stops_the_run_and_keeps_what_was_done() -> None:
    kept: list[str] = []

    def draft(call_id: str) -> CallWrapUp:
        if call_id == "T0002":
            raise ConnectionError("the workspace could not be reached")
        return wrap_up(call_id, "resolved", "billing")

    with pytest.raises(ConnectionError):
        predict(CALLS, draft, on_prediction=lambda item: kept.append(item["transcript_id"]))
    assert kept == ["T0001"]


def test_a_run_that_stopped_is_carried_on_without_asking_again(tmp_path: Path) -> None:
    run = {"git_sha": "abc", "wrap_up_prompt_version": "w1", "llm_endpoint": "databricks-x"}
    first = prediction("T0001", ("escalated", "billing"), ("escalated", "billing"))
    progress = tmp_path / "wrapup_x.progress.jsonl"
    # The last line was cut off when the run stopped.
    progress.write_text(
        json.dumps(run) + "\n" + json.dumps(first) + "\n" + '{"transcript_id": "T00',
        encoding="utf-8",
    )
    asked: list[str] = []

    def draft(call_id: str) -> CallWrapUp:
        asked.append(call_id)
        return wrap_up(call_id, "resolved", "troubleshooting")

    done = read_progress(progress, run)
    predictions = predict(CALLS[:3], draft, done=done)

    assert list(done) == ["T0001"]
    assert asked == ["T0002", "T0003"]
    assert predictions[0] == first
    assert [item["transcript_id"] for item in predictions] == ["T0001", "T0002", "T0003"]


def test_progress_from_another_commit_prompt_or_model_is_not_carried_over(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = {"git_sha": "abc", "wrap_up_prompt_version": "w1", "llm_endpoint": "databricks-x"}
    progress = tmp_path / "wrapup_x.progress.jsonl"
    progress.write_text(json.dumps(run) + "\n", encoding="utf-8")

    assert read_progress(tmp_path / "missing.jsonl", run) == {}
    assert read_progress(progress, run) == {}
    for changed in ("git_sha", "wrap_up_prompt_version", "llm_endpoint"):
        with pytest.raises(SystemExit):
            read_progress(progress, {**run, changed: "something else"})
    assert "different commit, prompt or model" in capsys.readouterr().out


# --- the command --------------------------------------------------------------------------------


def test_saving_is_refused_from_a_working_tree_with_uncommitted_changes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(wrapup_eval, "_git", lambda *args: " M src/copilot/prompts.py")

    with pytest.raises(SystemExit) as stopped:
        wrapup_eval.main(["--save"])

    assert stopped.value.code == 1
    assert "commit first" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [["--save", "--limit", "5"], ["--resume"], ["--limit", "0"]])
def test_a_trial_cannot_be_saved_and_only_a_saved_run_can_be_carried_on(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wrapup_eval, "_git", lambda *args: "")

    with pytest.raises(SystemExit) as stopped:
        wrapup_eval.main(arguments)

    assert stopped.value.code == 2
