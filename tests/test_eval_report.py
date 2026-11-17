"""The statistics, the generated reports and the offline gate over saved evaluation runs."""

import json
from pathlib import Path
from typing import Any

import pytest

from copilot.prompts import PROMPT_VERSION
from eval import gate, report
from eval.fingerprint import behaviour_fingerprint
from eval.stats import percentile, rate_with_interval, wilson_interval


def saved_run(**changes: Any) -> dict[str, Any]:
    """A small result file in the runner's shape: two rows, one failed check."""
    run: dict[str, Any] = {
        "run_at": "2026-11-15T12:00:00Z",
        "tag": "full",
        "git_sha": "abcdef1234567890",
        "git_dirty": False,
        "prompt_version": PROMPT_VERSION,
        "llm_endpoint": "databricks-gpt-oss-120b",
        "judge_endpoint": "databricks-judge",
        "category": "all",
        "rows": 2,
        "rows_reviewed": 2,
        "rows_without_answer": [],
        "eval_set_sha256": "same",
        "behaviour": {"sha256": "abc", "files": {"src/copilot/agent.py": "1"}},
        "router": "model",
        "router_endpoint": "databricks-router",
        "chunk_config": "A",
        "query_type": "ann",
        "metrics": {
            "retrieval_groundedness": {"kind": "pass_fail", "passed": 2, "scored": 2, "rate": 1.0},
            "no_pii_leak": {"kind": "pass_fail", "passed": 2, "scored": 2, "rate": 1.0},
            "escalation_correct": {"kind": "pass_fail", "passed": 2, "scored": 2, "rate": 1.0},
            "reading_level_ok": {"kind": "pass_fail", "passed": 2, "scored": 2, "rate": 1.0},
            "correctness": {"kind": "pass_fail", "passed": 1, "scored": 2, "rate": 0.5},
        },
        "per_row": [
            {
                "id": "E001",
                "category": "kb",
                "scores": {
                    "correctness": "no",
                    "retrieval_relevance": "no",
                    "reading_level_ok": True,
                    "latency_ms": 2000.0,
                    "model_calls": 3.0,
                    "total_tokens": 2340.0,
                },
            },
            {
                "id": "E030",
                "category": "escalation",
                "scores": {"escalation_correct": True, "latency_ms": 100.0, "model_calls": 0.0},
            },
        ],
    }
    run.update(changes)
    return run


def write_run(folder: Path, name: str, run: dict[str, Any]) -> None:
    (folder / name).write_text(json.dumps(run), encoding="utf-8")


# --- statistics -------------------------------------------------------------------------------


def test_a_perfect_score_on_few_rows_is_not_reported_as_certain() -> None:
    low, high = wilson_interval(22, 22)

    assert high == 1.0
    assert 0.84 < low < 0.86


def test_the_interval_narrows_as_rows_are_added() -> None:
    few = wilson_interval(9, 10)
    many = wilson_interval(900, 1000)

    assert many[1] - many[0] < few[1] - few[0]
    assert few[0] < 0.9 < few[1]
    assert wilson_interval(0, 5)[0] == 0.0


def test_impossible_counts_are_refused() -> None:
    for passed, scored in ((1, 0), (3, 2), (-1, 2)):
        with pytest.raises(ValueError, match="not a valid count"):
            wilson_interval(passed, scored)


def test_a_rate_is_written_with_its_count_and_interval() -> None:
    assert rate_with_interval(27, 31) == "27/31 (71-95%)"
    assert rate_with_interval(22, 22) == "22/22 (85-100%)"


def test_percentile_is_the_nearest_rank() -> None:
    values = [3.0, 1.0, 2.0, 4.0]

    assert percentile(values, 0.5) == 2.0
    assert percentile(values, 0.95) == 4.0
    assert percentile([7.0], 0.95) == 7.0
    with pytest.raises(ValueError, match="at least one value"):
        percentile([], 0.5)


# --- reports ----------------------------------------------------------------------------------


def test_reports_are_built_from_the_saved_runs_only(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-11-15_full-A-ann.json", saved_run())
    write_run(tmp_path, "redaction_2026-11-12_test.json", {"metrics": {}, "per_row": []})
    (tmp_path / "inspected.json").write_text(
        json.dumps(
            {
                "_about": "notes",
                "2026-11-15_full-A-ann.json": {
                    "E001": {"cause": "judge", "found": "The answer has every expected fact."}
                },
            }
        ),
        encoding="utf-8",
    )

    changed = report.write(tmp_path)

    assert {path.name for path in changed} == {"SUMMARY.md", "ERRORS.md"}
    summary = (tmp_path / "SUMMARY.md").read_text(encoding="utf-8")
    assert "1/2 (9-91%)" in summary
    # The answering model and the router are named, so two runs can be told apart.
    assert "| full | gpt-oss-120b | router | A | ann |" in summary
    assert "redaction_" not in summary
    assert "| 2026-11-15_full-A-ann.json | All | 2 | 0.1 | 2.0 | 2.0 | 0 | 2,340 |" in summary
    assert "| Help articles | 1 | 2.0 | 2.0 | 2.0 | 3 | 2,340 |" in summary
    assert "| 2026-11-15_full-A-ann.json | Requests that need a person | 1 | 0.1 | 0.1 | 0.1 |" in (
        summary
    )
    errors = (tmp_path / "ERRORS.md").read_text(encoding="utf-8")
    assert "1 of 2 rows failed at least one check" in errors
    assert "| E001 | Help articles | correctness | answer, by the judge | **judge.**" in errors
    # A chunk that is off the point is not a failed row, and a row that passed is not listed.
    assert "retrieval_relevance" not in errors
    assert "E030" not in errors


def test_every_table_row_has_as_many_cells_as_its_header(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-11-15_full-A-ann.json", saved_run())
    report.write(tmp_path)

    for name in ("SUMMARY.md", "ERRORS.md"):
        lines = (tmp_path / name).read_text(encoding="utf-8").splitlines()
        width = 0
        for number, line in enumerate(lines):
            if not line.startswith("|"):
                continue
            following = lines[number + 1] if number + 1 < len(lines) else ""
            if following.startswith("|---"):
                # A header row: the rows under it must match it.
                width = line.count("|")
            assert line.count("|") == width, line


def test_a_report_that_is_out_of_date_is_noticed(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-11-15_full-A-ann.json", saved_run())
    report.write(tmp_path)
    assert report.out_of_date(tmp_path) == []
    assert report.write(tmp_path) == []

    write_run(tmp_path, "2026-11-16_full-A-ann.json", saved_run(run_at="2026-11-16T12:00:00Z"))

    assert {path.name for path in report.out_of_date(tmp_path)} == {"SUMMARY.md", "ERRORS.md"}


def test_the_committed_reports_match_the_committed_runs() -> None:
    assert report.out_of_date() == []


# --- the gate ---------------------------------------------------------------------------------

BEHAVIOUR = {"sha256": "abc", "files": {"src/copilot/agent.py": "1"}}
SETTINGS = {
    "llm_endpoint": "databricks-gpt-oss-120b",
    "router": "model",
    "router_endpoint": "databricks-router",
    "chunk_config": "A",
    "query_type": "ann",
}


def check(run: dict[str, Any], **changes: Any) -> list[str]:
    arguments: dict[str, Any] = {
        "eval_set_sha256": "same",
        "prompt_version": PROMPT_VERSION,
        "behaviour": BEHAVIOUR,
        "settings": SETTINGS,
        **changes,
    }
    return gate.problems(run, **arguments)


def test_a_run_that_meets_the_thresholds_passes() -> None:
    assert check(saved_run()) == []


def test_a_run_below_a_threshold_fails_and_says_which() -> None:
    run = saved_run()
    run["metrics"]["reading_level_ok"] = {
        "kind": "pass_fail",
        "passed": 1,
        "scored": 2,
        "rate": 0.5,
    }
    del run["metrics"]["no_pii_leak"]

    found = check(run)

    assert found == ["no_pii_leak was not scored", "reading_level_ok is 1/2 (0.50), below 0.80"]


def test_a_run_made_with_another_set_or_prompt_is_stale() -> None:
    found = check(saved_run(), eval_set_sha256="different", prompt_version="v99")

    assert len(found) == 2
    assert "evaluation set has changed" in found[0]
    assert "prompt" in found[1]


def test_a_run_from_a_dirty_tree_or_with_missing_answers_fails() -> None:
    run = saved_run(git_dirty=True, rows_without_answer=["E002"])

    found = check(run)

    assert len(found) == 2


def test_a_run_of_code_that_has_since_changed_is_stale_and_the_gate_says_what_changed() -> None:
    now = {
        "sha256": "xyz",
        "files": {"src/copilot/agent.py": "2", "src/copilot/router.py": "1"},
    }

    found = check(saved_run(), behaviour=now)

    assert len(found) == 1
    assert "stale" in found[0]
    assert "src/copilot/agent.py, src/copilot/router.py" in found[0]


def test_a_run_saved_before_fingerprints_cannot_pass() -> None:
    run = saved_run()
    del run["behaviour"]

    found = check(run)

    assert len(found) == 1
    assert "before runs recorded a fingerprint" in found[0]


def test_a_run_made_with_another_model_or_router_is_not_the_configured_system() -> None:
    run = saved_run(llm_endpoint="databricks-other-model", router="rules")

    found = check(run)

    assert len(found) == 2
    assert "llm_endpoint = databricks-other-model" in found[0]
    assert "router = rules" in found[1]


def test_the_gate_reads_the_newest_run_over_the_whole_set(tmp_path: Path) -> None:
    write_run(tmp_path, "a.json", saved_run(run_at="2026-11-14T00:00:00Z", tag="old"))
    write_run(tmp_path, "b.json", saved_run(run_at="2026-11-16T00:00:00Z", tag="new"))
    write_run(tmp_path, "c.json", saved_run(run_at="2026-11-17T00:00:00Z", tag="kb", category="kb"))

    # A run of another set, or of a sample of this one, is not what the gate rests on.
    write_run(
        tmp_path,
        "f.json",
        saved_run(run_at="2026-11-20T00:00:00Z", tag="extended", eval_set="eval/other.jsonl"),
    )
    write_run(tmp_path, "g.json", saved_run(run_at="2026-11-21T00:00:00Z", sample=40))
    # A comparison between models, scored by some judges or by none, is not a full run.
    write_run(
        tmp_path,
        "d.json",
        saved_run(run_at="2026-11-18T00:00:00Z", tag="models", judges=["correctness"]),
    )
    write_run(
        tmp_path,
        "e.json",
        saved_run(run_at="2026-11-19T00:00:00Z", tag="no-judges", judge_endpoint=None),
    )

    latest = gate.latest_full_run(tmp_path)

    assert latest is not None
    assert (latest[0], latest[1]["tag"]) == ("b.json", "new")
    assert gate.latest_full_run(tmp_path / "missing") is None


def test_the_committed_results_pass_the_gate() -> None:
    latest = gate.latest_full_run()

    assert latest is not None
    assert (
        gate.problems(
            latest[1],
            eval_set_sha256=gate.sha256(gate.EVAL_SET),
            prompt_version=PROMPT_VERSION,
            behaviour=behaviour_fingerprint(),
            settings=gate.configured_settings(),
        )
        == []
    )
