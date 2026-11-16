"""The judge scored against a person's labels, on small made-up sheets. No model calls."""

from pathlib import Path
from typing import Any

import pytest

import eval.judge_agreement as agreement_module
from eval.judge_agreement import (
    agreement,
    cohens_kappa,
    confusion,
    kappa_interval,
    labelled_rows,
    main,
    parse_label,
    report_lines,
    score,
)
from eval.judge_sheet import SHEET_COLUMNS, VERDICT_COLUMNS, write_csv
from eval.stats import wilson_interval


def pairs(both_yes: int, judge_only: int, human_only: int, both_no: int) -> list[tuple[bool, bool]]:
    """(judge, person) verdicts with the given four counts."""
    return (
        [(True, True)] * both_yes
        + [(True, False)] * judge_only
        + [(False, True)] * human_only
        + [(False, False)] * both_no
    )


def sheet_row(
    key: str, judge_verdict: str, human: str, *, set_name: str = "evaluation", note: str = ""
) -> dict[str, str]:
    row_id, judge = key.split(":")
    return {
        "key": key,
        "set": set_name,
        "id": row_id,
        "category": "kb",
        "judge": judge,
        "question": "How much is the late fee?",
        "answer": "It is $5 [1].",
        "reference": "1. The Late Payment Fee is $5",
        "human": human,
        "note": note,
        "judge_verdict": judge_verdict,
        "judge_rationale": f"the judge's reason for {key}",
    }


# --- reading labels ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["yes", "Yes", " Y ", "TRUE", "1", "pass", "yes.", "correct"])
def test_a_yes_is_read_however_it_was_typed(text: str) -> None:
    assert parse_label(text) is True


@pytest.mark.parametrize("text", ["no", "No", "n", "false", "0", "FAIL", "wrong"])
def test_a_no_is_read_however_it_was_typed(text: str) -> None:
    assert parse_label(text) is False


def test_an_empty_cell_is_not_labelled_and_anything_else_is_refused() -> None:
    assert parse_label("") is None
    assert parse_label("   ") is None
    with pytest.raises(ValueError, match="not a yes or a no: 'maybe'"):
        parse_label("maybe")


def test_unlabelled_rows_are_counted_and_left_out() -> None:
    rows = [
        sheet_row("E001:correctness", "yes", "yes"),
        sheet_row("E002:correctness", "no", ""),
        sheet_row("E003:correctness", "yes", "no"),
    ]

    usable, unlabelled, problems = labelled_rows(rows)

    assert [(row["key"], row["judge_yes"], row["human_yes"]) for row in usable] == [
        ("E001:correctness", True, True),
        ("E003:correctness", True, False),
    ]
    assert unlabelled == 1
    assert problems == []


def test_a_label_that_cannot_be_read_is_reported_and_never_scored() -> None:
    rows = [
        sheet_row("E001:correctness", "yes", "yse"),
        sheet_row("E002:correctness", "", "yes"),
        sheet_row("E003:correctness", "perhaps", "yes"),
        sheet_row("E004:correctness", "yes", "yes"),
        sheet_row("E004:correctness", "yes", "no"),
    ]

    usable, unlabelled, problems = labelled_rows(rows)

    assert [row["key"] for row in usable] == ["E004:correctness"]
    assert unlabelled == 0
    assert problems == [
        "E001:correctness: human is not a yes or a no: 'yse'",
        "E002:correctness: no judge verdict (a blind sheet needs --verdicts)",
        "E003:correctness: judge_verdict is not a yes or a no: 'perhaps'",
        "E004:correctness: a row needs a key that no other row has",
    ]


# --- the statistics ---------------------------------------------------------------------------


def test_the_confusion_counts_keep_the_judge_and_the_person_apart() -> None:
    assert confusion(pairs(5, 1, 2, 3)) == {
        "judge_yes_human_yes": 5,
        "judge_yes_human_no": 1,
        "judge_no_human_yes": 2,
        "judge_no_human_no": 3,
    }


def test_kappa_matches_a_worked_example() -> None:
    """20, 5, 10, 15 of 50: observed 0.70, by chance 0.50, so kappa is 0.40."""
    assert cohens_kappa(pairs(20, 5, 10, 15)) == pytest.approx(0.4)


def test_kappa_is_one_for_full_agreement_and_zero_for_chance() -> None:
    assert cohens_kappa(pairs(6, 0, 0, 4)) == pytest.approx(1.0)
    # The judge says yes to everything: it agrees 8 times in 10 and knows nothing.
    assert cohens_kappa(pairs(8, 2, 0, 0)) == pytest.approx(0.0)
    # Worse than chance is below zero.
    assert cohens_kappa(pairs(0, 5, 5, 0)) == pytest.approx(-1.0)


def test_kappa_is_not_defined_when_both_gave_one_answer_to_every_row() -> None:
    assert cohens_kappa(pairs(10, 0, 0, 0)) is None
    assert cohens_kappa(pairs(0, 0, 0, 7)) is None
    assert cohens_kappa([]) is None
    assert kappa_interval(pairs(10, 0, 0, 0)) is None


def test_the_kappa_interval_is_the_same_every_time_and_holds_the_estimate() -> None:
    labelled = pairs(20, 5, 10, 15)

    first = kappa_interval(labelled, resamples=400)
    second = kappa_interval(labelled, resamples=400)

    assert first is not None
    assert first == second
    low, high = first
    assert -1.0 <= low < 0.4 < high <= 1.0
    assert kappa_interval(labelled, resamples=400, seed=1) != first


def test_redraws_in_which_kappa_is_not_defined_are_left_out_of_its_interval() -> None:
    """One wrong answer in 40: about a third of the redraws hold none of it."""
    labelled = pairs(39, 0, 0, 1)

    assert cohens_kappa(labelled) == pytest.approx(1.0)
    assert kappa_interval(labelled, resamples=300) == (1.0, 1.0)
    # The judge passed the one wrong answer: kappa is 0 wherever it is defined.
    assert kappa_interval(pairs(39, 1, 0, 0), resamples=300) == (0.0, 0.0)


def test_agreement_reports_every_rate_with_its_wilson_interval() -> None:
    stats = agreement(pairs(25, 1, 2, 3))

    assert stats["labelled"] == 31
    assert stats["agree"] == {
        "count": 28,
        "of": 31,
        "rate": 28 / 31,
        "ci95": list(wilson_interval(28, 31)),
    }
    # Four answers the person marked wrong; the judge failed three of them.
    assert stats["wrong_answers_failed_by_judge"]["count"] == 3
    assert stats["wrong_answers_failed_by_judge"]["of"] == 4
    assert stats["wrong_answers_failed_by_judge"]["ci95"] == list(wilson_interval(3, 4))
    # Twenty-seven the person marked right; the judge passed twenty-five.
    assert stats["right_answers_passed_by_judge"]["count"] == 25
    assert stats["right_answers_passed_by_judge"]["of"] == 27
    assert stats["kappa"] == pytest.approx(cohens_kappa(pairs(25, 1, 2, 3)))
    assert stats["kappa_ci95"] is not None


def test_a_rate_with_nothing_to_count_is_empty_and_not_zero() -> None:
    stats = agreement(pairs(5, 0, 0, 0))

    assert stats["wrong_answers_failed_by_judge"] == {
        "count": 0,
        "of": 0,
        "rate": None,
        "ci95": None,
    }
    assert stats["kappa"] is None
    assert stats["kappa_ci95"] is None


# --- the report -------------------------------------------------------------------------------


def labelled(*rows: dict[str, str]) -> list[dict[str, Any]]:
    usable, _, problems = labelled_rows(rows)
    assert problems == []
    return usable


def test_each_judge_is_scored_apart_and_disagreements_are_listed() -> None:
    rows = labelled(
        sheet_row("E001:correctness", "yes", "yes"),
        sheet_row("E002:correctness", "no", "yes", note="every fact is there"),
        sheet_row("E003:correctness", "no", "no"),
        sheet_row("E001:retrieval_groundedness", "yes", "yes"),
        sheet_row("E002:retrieval_groundedness", "yes", "no", note="the $7 is not in the text"),
    )

    result = score(rows)

    assert list(result["by_judge"]) == ["correctness", "retrieval_groundedness"]
    assert result["by_judge"]["correctness"]["agree"]["count"] == 2
    assert result["by_judge"]["correctness"]["labelled"] == 3
    assert result["by_judge"]["retrieval_groundedness"]["confusion"]["judge_yes_human_no"] == 1
    assert result["all_judges"]["labelled"] == 5
    assert result["disagreements"] == [
        {
            "key": "E002:correctness",
            "set": "evaluation",
            "judge": "correctness",
            "judge_verdict": "no",
            "human": "yes",
            "note": "every fact is there",
            "judge_rationale": "the judge's reason for E002:correctness",
        },
        {
            "key": "E002:retrieval_groundedness",
            "set": "evaluation",
            "judge": "retrieval_groundedness",
            "judge_verdict": "yes",
            "human": "no",
            "note": "the $7 is not in the text",
            "judge_rationale": "the judge's reason for E002:retrieval_groundedness",
        },
    ]
    assert "by_set_and_judge" not in result


def test_controls_and_real_answers_are_also_reported_apart() -> None:
    rows = labelled(
        sheet_row("E001:correctness", "yes", "yes"),
        sheet_row("E002:correctness", "yes", "yes"),
        sheet_row("C01:correctness", "no", "no", set_name="control"),
        sheet_row("C02:correctness", "yes", "no", set_name="control"),
    )

    result = score(rows)

    assert list(result["by_set_and_judge"]) == ["control", "evaluation"]
    control = result["by_set_and_judge"]["control"]["correctness"]
    assert control["wrong_answers_failed_by_judge"]["count"] == 1
    assert control["wrong_answers_failed_by_judge"]["of"] == 2
    # On the real answers alone both said yes every time, so kappa says nothing.
    assert result["by_set_and_judge"]["evaluation"]["correctness"]["kappa"] is None
    assert result["by_judge"]["correctness"]["kappa"] == pytest.approx(0.5)


def test_the_printed_report_names_the_counts_the_intervals_and_the_disagreements() -> None:
    rows = labelled(
        sheet_row("E001:correctness", "yes", "yes"),
        sheet_row("E002:correctness", "no", "yes", note="every fact is there"),
        sheet_row("E003:correctness", "no", "no"),
        sheet_row("E004:correctness", "yes", "yes"),
    )

    text = "\n".join(report_lines(score(rows), unlabelled=2))

    assert "correctness: 4 labelled" in text
    assert "same verdict                     3/4 (30-96%)" in text
    assert "Cohen's kappa                    0.50" in text
    assert "wrong answers the judge failed   1/1 (20-100%)" in text
    assert "right answers the judge passed   2/3 (20-94%)" in text
    assert "1 rows where the judge and the person disagree:" in text
    assert "E002:correctness (evaluation): judge no, person yes" in text
    assert "person's note: every fact is there" in text
    assert "judge's reason: the judge's reason for E002:correctness" in text
    assert "2 rows are not labelled yet and were left out." in text
    # One judge only, so there is no second block for all judges together.
    assert "all judges together" not in text


def test_kappa_that_is_not_defined_is_said_in_words() -> None:
    rows = labelled(
        sheet_row("E001:correctness", "yes", "yes"), sheet_row("E002:correctness", "yes", "yes")
    )

    text = "\n".join(report_lines(score(rows), unlabelled=0))

    assert "Cohen's kappa                    not defined" in text
    assert "wrong answers the judge failed   none labelled" in text


# --- the command ------------------------------------------------------------------------------


def write_sheet(path: Path, *rows: dict[str, str]) -> Path:
    write_csv(rows, path, SHEET_COLUMNS)
    return path


def test_the_command_scores_a_labelled_sheet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = write_sheet(
        tmp_path / "sheet.csv",
        sheet_row("E001:correctness", "yes", "yes"),
        sheet_row("E002:correctness", "no", "no"),
        sheet_row("E003:correctness", "yes", ""),
    )

    main([str(sheet)])

    printed = capsys.readouterr().out
    assert "correctness: 2 labelled" in printed
    assert "same verdict                     2/2 (34-100%)" in printed
    assert "1 rows are not labelled yet" in printed


def test_the_command_stops_on_a_label_it_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = write_sheet(
        tmp_path / "sheet.csv",
        sheet_row("E001:correctness", "yes", "yes"),
        sheet_row("E002:correctness", "no", "nope"),
    )

    with pytest.raises(SystemExit):
        main([str(sheet)])

    printed = capsys.readouterr().out
    assert "cannot be read: E002:correctness: human is not a yes or a no: 'nope'" in printed
    assert "Nothing was scored" in printed
    assert "labelled\n" not in printed


def test_the_command_stops_when_nothing_is_labelled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = write_sheet(tmp_path / "sheet.csv", sheet_row("E001:correctness", "yes", ""))

    with pytest.raises(SystemExit):
        main([str(sheet)])

    assert "no row is labelled yet (1 rows)" in capsys.readouterr().out


def test_a_blind_sheet_is_scored_with_the_verdicts_that_were_kept_apart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blind = sheet_row("E001:correctness", "", "no")
    blind["judge_rationale"] = ""
    sheet = write_sheet(tmp_path / "sheet.csv", blind)
    verdicts = tmp_path / "sheet_verdicts.csv"
    write_csv(
        [{"key": "E001:correctness", "judge_verdict": "yes", "judge_rationale": "all there"}],
        verdicts,
        VERDICT_COLUMNS,
    )

    main([str(sheet), "--verdicts", str(verdicts)])

    printed = capsys.readouterr().out
    assert "E001:correctness (evaluation): judge yes, person no" in printed
    assert "judge's reason: all there" in printed


def test_saving_records_the_sheets_by_hash_and_every_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hashlib
    import json

    sheet = write_sheet(
        tmp_path / "sheet.csv",
        sheet_row("E001:correctness", "yes", "yes"),
        sheet_row("C01:correctness", "no", "no", set_name="control"),
    )
    monkeypatch.setattr(agreement_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(
        agreement_module, "_git", lambda *args: "" if args[0] == "status" else "abc1234"
    )

    main([str(sheet), "--save", "--tag", "first"])

    (saved_path,) = (tmp_path / "results").glob("judge_agreement_*_first.json")
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved["git_sha"] == "abc1234"
    assert saved["sheets"] == [
        {
            "file": sheet.as_posix(),
            "sha256": hashlib.sha256(sheet.read_bytes()).hexdigest(),
            "rows": 2,
        }
    ]
    assert saved["rows_labelled"] == 2
    assert [label["key"] for label in saved["labels"]] == ["E001:correctness", "C01:correctness"]
    assert saved["by_judge"]["correctness"]["kappa"] == pytest.approx(1.0)
    # The evaluation reports read only files that hold "per_row" and "metrics".
    assert "per_row" not in saved
    assert "metrics" not in saved
    assert "saved" in capsys.readouterr().out


def test_a_result_is_not_saved_from_a_tree_with_uncommitted_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = write_sheet(tmp_path / "sheet.csv", sheet_row("E001:correctness", "yes", "yes"))
    monkeypatch.setattr(agreement_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(agreement_module, "_git", lambda *args: " M eval/judge_agreement.py")

    with pytest.raises(SystemExit):
        main([str(sheet), "--save"])

    assert "not saved: commit your changes first" in capsys.readouterr().out
    assert not (tmp_path / "results").exists()
