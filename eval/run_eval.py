"""Evaluate the copilot on the evaluation set and record the result.

Usage:
    python -m eval.run_eval --config A --query-type ann --tag baseline --category kb --limit 5
    python -m eval.run_eval --config A --query-type ann --tag baseline --category kb --save

Always try ``--limit 5`` first. A full pass makes several hundred model calls, and
on Free Edition a pass that dies on the daily quota costs a day.

``--save`` writes ``eval/results/<date>_<tag>.json`` and rebuilds
``eval/results/SUMMARY.md`` and ``ERRORS.md`` from every saved run. It refuses to run
from a dirty working tree, so every saved number has a real git SHA.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from eval.redaction_eval import _git, _sha256
from eval.report import as_pass
from eval.report import write as write_reports
from eval.stats import percentile, wilson_interval

EVAL_SET = Path("eval/eval_set.jsonl")
RESULTS_DIR = Path("eval/results")
EVAL_ID_TAG = "eval_id"

# Defaults for a workspace with a low requests-per-second limit on its model
# endpoints (Databricks Free Edition). MLflow's own defaults run ten rows and ten
# judges at once, which the judge endpoint answers with HTTP 429. Each can be
# overridden by setting the variable before running.
EVAL_ENVIRONMENT: dict[str, str] = {
    # One row at a time. Also keeps the latency measurement free of contention.
    "MLFLOW_GENAI_EVAL_MAX_WORKERS": "1",
    "MLFLOW_GENAI_EVAL_MAX_SCORER_WORKERS": "2",
    "MLFLOW_GENAI_EVAL_SCORER_RATE_LIMIT": "2",
    "MLFLOW_GENAI_EVAL_MAX_RETRIES": "8",
    # MLflow otherwise downloads a model price catalogue from GitHub to estimate
    # trace cost. Not needed here.
    "MLFLOW_MODEL_CATALOG_URI": "",
}


def load_eval_set(
    path: Path = EVAL_SET, *, category: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """Read the evaluation rows, optionally one category and the first ``limit`` of them."""
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if category:
        rows = [row for row in rows if row["category"] == category]
    return rows[:limit] if limit else rows


def to_records(
    rows: Sequence[Mapping[str, Any]], safe_questions: Mapping[str, str] | None = None
) -> list[dict[str, Any]]:
    """Convert rows to the ``inputs`` / ``expectations`` shape MLflow evaluates.

    MLflow stores the inputs with the run. ``safe_questions`` maps a row id to
    its redacted question, so a question that contains personal data on purpose
    is never stored as written.
    """
    safe = safe_questions or {}
    return [
        {
            "inputs": {
                **row["inputs"],
                "question": safe.get(row.get("id", ""), row["inputs"]["question"]),
            },
            "expectations": {k: v for k, v in row["expectations"].items() if v is not None},
        }
        for row in rows
    ]


def aggregate(per_row: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summarise each scorer over the rows that have a value for it.

    A pass/fail scorer gets ``passed``, ``scored``, ``rate`` and ``ci95``, the
    95% Wilson interval of the rate. A numeric one gets ``scored``, ``mean``,
    ``median``, ``p90`` and ``p95``. Rows where a scorer produced nothing or
    errored are simply not counted, and ``scored`` says how many were.
    """
    values: dict[str, list[Any]] = defaultdict(list)
    for scores in per_row:
        for name, value in scores.items():
            if value is not None:
                values[name].append(value)
    summary: dict[str, dict[str, Any]] = {}
    for name, items in sorted(values.items()):
        verdicts = [as_pass(item) for item in items]
        if all(verdict is not None for verdict in verdicts):
            passed = sum(1 for verdict in verdicts if verdict)
            summary[name] = {
                "kind": "pass_fail",
                "passed": passed,
                "scored": len(items),
                "rate": passed / len(items),
                "ci95": list(wilson_interval(passed, len(items))),
            }
            continue
        numbers = sorted(float(item) for item in items if isinstance(item, int | float))
        if numbers:
            summary[name] = {
                "kind": "numeric",
                "scored": len(numbers),
                "mean": statistics.fmean(numbers),
                "median": statistics.median(numbers),
                "p90": numbers[min(len(numbers) - 1, int(0.9 * len(numbers)))],
                "p95": percentile(numbers, 0.95),
            }
    return summary


def rows_by_eval_id(traces: Sequence[Any]) -> dict[str, dict[str, Any]]:
    """Scores per evaluation row, keyed by the ``eval_id`` tag on each trace.

    Rows are matched by tag and not by question text, because the question on a
    trace is the redacted one. If a row has several traces, the one with the
    most scores is used.
    """
    best: dict[str, dict[str, Any]] = {}
    for trace in traces:
        eval_id = (trace.info.tags or {}).get(EVAL_ID_TAG)
        if not eval_id:
            continue
        scores = scores_from_trace(trace)
        if eval_id not in best or len(scores) > len(best[eval_id]):
            best[eval_id] = scores
    return best


def rows_without_answer(
    rows: Sequence[Mapping[str, Any]], scored: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """Ids of rows that have no trace, or whose trace holds no answer.

    Such a row has no real scores. The run reports these and stops, so a pass
    that lost an answer is never saved as if it were complete.
    """
    return [
        row["id"] for row in rows if scored.get(row["id"], {}).get("answer_recorded") is not True
    ]


def scores_from_trace(trace: Any) -> dict[str, Any]:
    """Collect every scorer value attached to a trace, by scorer name."""
    scores: dict[str, Any] = {}
    for assessment in trace.info.assessments or []:
        feedback = getattr(assessment, "feedback", None)
        if feedback is None:
            continue
        scores[assessment.name] = None if getattr(feedback, "error", None) else feedback.value
    return scores


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, choices=["A", "B"], help="chunk configuration")
    parser.add_argument("--query-type", required=True, choices=["ann", "hybrid"])
    parser.add_argument("--tag", required=True, help="short name for this run")
    parser.add_argument("--category", default=None, help="only rows of this category")
    parser.add_argument("--limit", type=int, default=None, help="only the first N rows")
    parser.add_argument("--no-judges", action="store_true", help="deterministic scorers only")
    parser.add_argument("--no-ragas", action="store_true", help="skip RAGAS ContextPrecision")
    parser.add_argument("--save", action="store_true", help="write the result to eval/results")
    args = parser.parse_args(argv)

    git_dirty = bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results"))
    if args.save and git_dirty:
        print("not started: commit your changes first so the result has a clean git SHA")
        raise SystemExit(1)

    for name, value in EVAL_ENVIRONMENT.items():
        os.environ.setdefault(name, value)

    import mlflow
    from dotenv import load_dotenv

    from copilot.agent import Copilot
    from copilot.config import load_settings
    from copilot.prompts import PROMPT_VERSION
    from copilot.redaction import get_redactor
    from eval.scorers import DETERMINISTIC_SCORERS, llm_judges, register_raw_questions

    # Puts DATABRICKS_HOST and DATABRICKS_CONFIG_PROFILE where the SDK and MLflow look.
    load_dotenv()
    settings = load_settings().model_copy(
        update={
            "chunk_config": args.config,
            "query_type": args.query_type,
            # A run must not leave tickets for people who do not exist.
            "record_escalations": False,
        }
    )
    rows = load_eval_set(category=args.category, limit=args.limit)
    if not rows:
        print("no evaluation rows match")
        raise SystemExit(1)
    scorers = list(DETERMINISTIC_SCORERS)
    if not args.no_judges:
        scorers += llm_judges(settings.judge_endpoint, include_ragas=not args.no_ragas)

    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment(settings.mlflow_experiment)
    copilot = Copilot(settings)

    # MLflow stores the dataset, so it is given redacted questions. The copilot is
    # still called with the question as written, which is what it has to handle.
    redactor = get_redactor(product_names=tuple(settings.product_names))
    raw_by_id = {row["id"]: row["inputs"]["question"] for row in rows}
    safe_by_id = {row_id: redactor.redact(text).text for row_id, text in raw_by_id.items()}
    id_by_safe_question = {text: row_id for row_id, text in safe_by_id.items()}
    if len(id_by_safe_question) != len(rows):
        print("not started: two rows have the same question after redaction")
        raise SystemExit(1)
    register_raw_questions(raw_by_id)

    def predict(question: str) -> str:
        eval_id = id_by_safe_question[question]
        return copilot.run(raw_by_id[eval_id], trace_tags={EVAL_ID_TAG: eval_id}).answer

    run_name = f"{args.tag}-{args.config}-{args.query_type}"
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(
            {
                "tag": args.tag,
                "chunk_config": args.config,
                "query_type": args.query_type,
                "prompt_version": PROMPT_VERSION,
                "llm_endpoint": settings.llm_endpoint,
                "judge_endpoint": settings.judge_endpoint,
                "git_sha": _git("rev-parse", "HEAD"),
                "category": args.category or "all",
            }
        )
        mlflow.genai.evaluate(
            data=to_records(rows, safe_by_id), predict_fn=predict, scorers=scorers
        )
        traces = mlflow.search_traces(run_id=run.info.run_id, return_type="list")

    scored = rows_by_eval_id(traces)
    per_row = [
        {"id": row["id"], "category": row["category"], "scores": scored[row["id"]]}
        for row in rows
        if row["id"] in scored
    ]
    metrics = aggregate([item["scores"] for item in per_row])
    metrics_by_category = {
        category: aggregate([item["scores"] for item in per_row if item["category"] == category])
        for category in sorted({item["category"] for item in per_row})
    }
    unanswered = rows_without_answer(rows, scored)

    report: dict[str, Any] = {
        "run_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tag": args.tag,
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": git_dirty,
        "chunk_config": args.config,
        "chunking": settings.active_chunking.model_dump(),
        "query_type": args.query_type,
        "top_k": settings.top_k,
        "prompt_version": PROMPT_VERSION,
        "llm_endpoint": settings.llm_endpoint,
        "router": settings.router,
        "router_endpoint": settings.router_endpoint if settings.router == "model" else None,
        "judge_endpoint": None if args.no_judges else settings.judge_endpoint,
        "embedding_endpoint": settings.embedding_endpoint,
        "category": args.category or "all",
        "escalations_recorded": settings.record_escalations,
        "rows": len(rows),
        "rows_scored": len(per_row),
        "rows_without_answer": unanswered,
        "rows_reviewed": sum(1 for row in rows if row.get("reviewed")),
        "eval_set_sha256": _sha256(EVAL_SET),
        "mlflow_run_id": run.info.run_id,
        "versions": {name: version(name) for name in ("mlflow", "ragas", "databricks-sdk")},
        "metrics": metrics,
        "metrics_by_category": metrics_by_category,
        "per_row": per_row,
    }

    print(f"\n{run_name}: {len(per_row)} of {len(rows)} rows scored")
    for name, metric in metrics.items():
        if metric["kind"] == "pass_fail":
            print(f"  {name:<34} {metric['passed']}/{metric['scored']}  ({metric['rate']:.3f})")
        else:
            print(
                f"  {name:<34} mean {metric['mean']:.2f}  median {metric['median']:.2f}  "
                f"p90 {metric['p90']:.2f}  (n={metric['scored']})"
            )

    if unanswered:
        print(
            f"\nstopped: {len(unanswered)} of {len(rows)} rows have no recorded answer "
            f"({', '.join(unanswered)}). Nothing was saved. Look at these rows' traces in "
            f"MLflow run {run.info.run_id}, then run again."
        )
        raise SystemExit(1)

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        file_name = f"{report['run_at'][:10]}_{run_name}.json"
        (RESULTS_DIR / file_name).write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"\nsaved {RESULTS_DIR / file_name}")
        # SUMMARY.md and ERRORS.md are rebuilt from every saved run, this one included.
        for path in write_reports():
            print(f"wrote {path.as_posix()}")


if __name__ == "__main__":
    main()
