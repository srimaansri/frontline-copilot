"""Fail when the newest saved evaluation no longer supports the repository.

Usage:
    python -m eval.gate

It makes no model calls, so it runs on every push. It checks the newest saved
run over the whole evaluation set, with every judge, for two things:

- **It is about this repository.** Every run records a fingerprint of what
  decided the copilot's behaviour: the agent's code, its prompts, its settings,
  the evaluation set and the scorers (``eval/fingerprint.py``). The gate
  computes the same fingerprint from the repository and fails if they differ,
  naming the files that changed. It also fails if the run answered or routed
  with a model other than the configured one. A change to how the copilot
  behaves therefore has to arrive together with a fresh evaluation of it.
- **It meets the thresholds** in PLAN.md section 9.5.

What it does not see: a change in a model behind an endpoint, in the search
index, or in the data. Those are outside the repository.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from copilot.config import load_settings
from copilot.prompts import PROMPT_VERSION
from eval.fingerprint import behaviour_fingerprint, changed_files
from eval.report import RESULTS_DIR, load_results

EVAL_SET = Path("eval/eval_set.jsonl")

# (scorer, the lowest pass rate allowed). PLAN.md section 9.5.
THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("retrieval_groundedness", 0.85),
    ("no_pii_leak", 1.0),
    ("escalation_correct", 0.9),
    ("reading_level_ok", 0.8),
)


def configured_settings() -> dict[str, Any]:
    """The models and search settings a full run must have used to describe this repository.

    A run can be made with another model or setting from the command line. That is
    a comparison, and it must not stand in for an evaluation of the configured system.
    """
    settings = load_settings()
    return {
        "llm_endpoint": settings.llm_endpoint,
        "router": settings.router,
        "router_endpoint": settings.router_endpoint if settings.router == "model" else None,
        "chunk_config": settings.chunk_config,
        "query_type": settings.query_type,
    }


def sha256(path: Path) -> str:
    """The hash the runner records for the evaluation set."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_full_run(results_dir: Path = RESULTS_DIR) -> tuple[str, dict[str, Any]] | None:
    """The newest saved run over every category with every judge, or None if there is none.

    A run limited to some judges, or to none, is a comparison between settings.
    It cannot meet the thresholds and is not what the published figures rest on.
    """
    full = [
        item
        for item in load_results(results_dir)
        if item[1].get("category") == "all"
        # Only the reviewed set the thresholds were written for. A run of another
        # set, or of a sample, is reported and is not what the gate rests on.
        and item[1].get("eval_set", EVAL_SET.as_posix()) == EVAL_SET.as_posix()
        and not item[1].get("sample")
        and item[1].get("judge_endpoint")
        and item[1].get("judges", "all") == "all"
    ]
    return full[-1] if full else None


def problems(
    report: Mapping[str, Any],
    *,
    eval_set_sha256: str,
    prompt_version: str,
    behaviour: Mapping[str, Any],
    settings: Mapping[str, Any],
) -> list[str]:
    """Why this run does not pass the gate. Empty when it does.

    Args:
        report: The saved run.
        eval_set_sha256: The hash of the evaluation set in the repository.
        prompt_version: The prompt version in the repository.
        behaviour: The fingerprint computed from the repository now.
        settings: The models and search settings the repository is configured with.
    """
    found: list[str] = []
    saved = report.get("behaviour")
    if not saved:
        found.append(
            "the run was saved before runs recorded a fingerprint, so it cannot be shown "
            "to describe this code; save a new full run (python -m eval.run_eval ... --save)"
        )
    elif changed := changed_files(saved.get("files", {}), behaviour["files"]):
        found.append(
            "the copilot has changed since this run, so its numbers are stale; changed: "
            f"{', '.join(changed) or 'unknown'}. Save a new full run"
        )
    for name, configured in settings.items():
        if report.get(name) != configured:
            found.append(
                f"the run used {name} = {report.get(name)} and the repository is configured "
                f"with {configured}; save a new full run"
            )
    if report.get("git_dirty"):
        found.append("the run was made from a working tree with uncommitted changes")
    if report.get("rows_without_answer"):
        found.append("some rows have no recorded answer")
    if report.get("eval_set_sha256") != eval_set_sha256:
        found.append(
            "the evaluation set has changed since this run; save a new full run "
            "(python -m eval.run_eval ... --save)"
        )
    if report.get("prompt_version") != prompt_version:
        found.append(
            f"the run used prompt {report.get('prompt_version')} and the repository has "
            f"{prompt_version}; save a new full run"
        )
    metrics = report.get("metrics", {})
    for scorer, lowest in THRESHOLDS:
        metric = metrics.get(scorer)
        if not metric or metric.get("kind") != "pass_fail":
            found.append(f"{scorer} was not scored")
        elif metric["rate"] < lowest:
            found.append(
                f"{scorer} is {metric['passed']}/{metric['scored']} "
                f"({metric['rate']:.2f}), below {lowest:.2f}"
            )
    return found


def main() -> None:
    """Check the newest full run and exit 1 if it does not pass."""
    latest = latest_full_run()
    if latest is None:
        print("gate: no saved run over the whole evaluation set")
        raise SystemExit(1)
    file_name, report = latest
    print(f"gate: {file_name}, commit {report['git_sha'][:7]}, {report['rows']} rows")
    found = problems(
        report,
        eval_set_sha256=sha256(EVAL_SET),
        prompt_version=PROMPT_VERSION,
        behaviour=behaviour_fingerprint(),
        settings=configured_settings(),
    )
    for problem in found:
        print(f"gate: FAIL: {problem}")
    if found:
        raise SystemExit(1)
    for scorer, lowest in THRESHOLDS:
        metric = report["metrics"][scorer]
        print(f"gate: ok: {scorer} {metric['passed']}/{metric['scored']} (needs {lowest:.2f})")


if __name__ == "__main__":
    main()
