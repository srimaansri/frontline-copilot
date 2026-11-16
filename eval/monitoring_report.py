"""A monitoring report built from the copilot's traces and the ratings on them.

Usage:
    python -m eval.monitoring_report                       the last 7 days of real use
    python -m eval.monitoring_report --days 1 --limit 20   a quick look; never saved
    python -m eval.monitoring_report --since 2026-11-14 --until 2026-11-16
    python -m eval.monitoring_report --source evaluation
    python -m eval.monitoring_report --save

It answers two questions for whoever is on call: is the copilot healthy, and
what changed? It reads the traces of the MLflow experiment for a window of time
and prints, as Markdown: how many requests there were by day and by source,
where they went (answered, handed off, refused; the router or the rules; every
guardrail flag), how long the answer and each stage of it took, the model calls
and tokens per answer, what failed and where, what the ratings say, and a short
list of what to look at. ``--save`` writes the same page to
``eval/results/monitoring_<date>.md`` and its numbers to a ``.json`` file beside
it. It needs a clean working tree, so the commit it names is the code that read
the traces.

By default only real use is reported: the requests the web app tagged
``source=web``. ``--source`` picks another source by name (``evaluation``,
``untagged``, any other ``source`` tag) or ``all``.

This file is the only place that touches MLflow, and it only reads. It makes two
searches: one for every trace of the window without its spans, which is cheap
and gives the volume table, and one with spans for the requests of the chosen
source. Each trace becomes a ``TraceRecord`` from ``eval.monitoring``, which
works everything out. A record has no field for a question, an answer or a tool
argument, so the report cannot print one. Spans are read for three things only:
their names, times and status; the fixed fields of the answer (flags, tools,
counts); and whether a tool's result is the copilot's own "Tool error" message.

A trace whose spans cannot be downloaded is kept, with its state and its total
time, and the report says how many there were. MLflow leaves such a trace out
of a search that asks for spans, which would otherwise make it vanish.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from eval.monitoring import (
    ANSWER_SPAN,
    CONFIG_TAGS,
    ROUTER_SPAN,
    SOURCE_ALL,
    SOURCE_EVALUATION,
    SOURCE_UNTAGGED,
    SOURCE_WEB,
    TOOL_PREFIX,
    AnswerRecord,
    RatingRecord,
    SpanRecord,
    TraceRecord,
    render_markdown,
    runtime_of,
    safe_flag,
    safe_name,
    safe_span_name,
    safe_value,
    select,
    source_of,
    summarise,
)
from eval.redaction_eval import _git

RESULTS_DIR = Path("eval/results")
DEFAULT_DAYS = 7.0
DAY_MS = 24 * 60 * 60 * 1000

# The rating the web app logs for a thumbs up or down (``api.main``).
FEEDBACK_NAME = "agent_feedback"
# Where MLflow keeps what the report reads beside the copilot's own tags. A test
# checks these against the constants of the installed MLflow.
TRACE_NAME_TAG = "mlflow.traceName"
SOURCE_RUN_KEY = "mlflow.sourceRun"
SOURCE_NAME_KEY = "mlflow.source.name"
EXCEPTION_EVENT = "exception"
EXCEPTION_TYPE = "exception.type"
# The attributes the copilot sets on the root span of an answer (``copilot.agent``).
MODEL_CALLS_ATTRIBUTE = "copilot.model_calls"
INPUT_TOKENS_ATTRIBUTE = "copilot.input_tokens"
OUTPUT_TOKENS_ATTRIBUTE = "copilot.output_tokens"
# What the copilot gives the model in place of a tool's result when the tool failed.
TOOL_ERROR_PREFIX = "Tool error:"
TOOL_UNREACHABLE = "Tool error: the lookup could not be completed."

_SOURCE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,59}")


# --- one trace -> one record ---------------------------------------------------------------------


def _count(value: Any) -> int | None:
    """A count as a whole number, or None when the trace does not hold one."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _note(name: str, depth: int, outputs: Any) -> str | None:
    """What happened inside a router or tool span that ended without an exception.

    The router's span records whether its reply was used. A failed tool leaves
    the copilot's own fixed message as its result. Nothing else is read from a
    span's outputs, and nothing read here is kept as text.
    """
    if name == ROUTER_SPAN and isinstance(outputs, Mapping):
        if outputs.get("used") is True:
            return "used"
        return "unreachable" if outputs.get("route") is None else "unreadable"
    is_tool = name.startswith(TOOL_PREFIX) and depth == 1
    if is_tool and isinstance(outputs, str) and outputs.startswith(TOOL_ERROR_PREFIX):
        return "unreachable" if outputs == TOOL_UNREACHABLE else "rejected"
    return None


def span_records(spans: Sequence[Any]) -> tuple[SpanRecord, ...]:
    """The spans of one trace as records: names, times and status, and no content."""
    by_id = {span.span_id: span for span in spans}

    def depth_of(span: Any) -> int:
        depth = 0
        while span.parent_id and span.parent_id in by_id and depth < len(by_id):
            span = by_id[span.parent_id]
            depth += 1
        return depth

    records = []
    for span in spans:
        parent = by_id.get(span.parent_id) if span.parent_id else None
        depth = depth_of(span)
        status = getattr(span.status.status_code, "value", str(span.status.status_code))
        thrown = next((event for event in span.events if event.name == EXCEPTION_EVENT), None)
        ended = span.end_time_ns is not None and span.start_time_ns is not None
        records.append(
            SpanRecord(
                name=safe_span_name(span.name),
                kind=safe_name(span.span_type),
                depth=depth,
                parent=safe_span_name(parent.name) if parent is not None else None,
                started_ms=(span.start_time_ns or 0) / 1e6,
                duration_ms=(span.end_time_ns - span.start_time_ns) / 1e6 if ended else None,
                failed=status == "ERROR",
                # The type only. The message of an exception can quote what it was given.
                exception=safe_name(thrown.attributes.get(EXCEPTION_TYPE)) if thrown else None,
                note=_note(str(span.name), depth, span.outputs),
            )
        )
    return tuple(records)


def answer_record(root: Any) -> AnswerRecord | None:
    """The fixed fields of an answer, read from its root span. None if it holds no answer."""
    outputs = root.outputs
    if not isinstance(outputs, Mapping):
        return None
    usage = outputs.get("usage")
    flags = outputs.get("guardrail_flags")
    citations = outputs.get("citations")
    return AnswerRecord(
        escalated=outputs.get("escalated") is True,
        flags=tuple(safe_flag(flag) for flag in flags) if isinstance(flags, list) else (),
        handoff_drafted=outputs.get("handoff_draft") is not None,
        citations=len(citations) if isinstance(citations, list) else 0,
        model_calls=_count(root.attributes.get(MODEL_CALLS_ATTRIBUTE)),
        input_tokens=_count(root.attributes.get(INPUT_TOKENS_ATTRIBUTE)),
        output_tokens=_count(root.attributes.get(OUTPUT_TOKENS_ATTRIBUTE)),
        calls_without_counts=_count(usage.get("calls_without_counts"))
        if isinstance(usage, Mapping)
        else None,
    )


def _ratings(info: Any) -> tuple[RatingRecord, ...]:
    """The thumbs up and down on a trace that a person gave and that still stand."""
    found = []
    for assessment in info.assessments or []:
        feedback = getattr(assessment, "feedback", None)
        source = getattr(assessment, "source", None)
        if (
            assessment.name != FEEDBACK_NAME
            or feedback is None
            or getattr(assessment, "valid", True) is False
            or not isinstance(feedback.value, bool)
            or str(getattr(source, "source_type", "")) != "HUMAN"
        ):
            continue
        at_ms = assessment.last_update_time_ms or assessment.create_time_ms or 0
        found.append(RatingRecord(helpful=feedback.value, at_ms=int(at_ms)))
    return tuple(found)


def to_record(info: Any, spans: Sequence[Any] | None = None) -> TraceRecord:
    """One trace as a record. ``spans`` is None when the trace's spans could not be read."""
    tags = dict(info.tags or {})
    metadata = dict(info.trace_metadata or {})
    records = span_records(spans) if spans else None
    root = next((span for span in spans or [] if not span.parent_id), None)
    name = tags.get(TRACE_NAME_TAG) or (root.name if root is not None else None)
    return TraceRecord(
        trace_id=str(info.trace_id),
        started_ms=int(info.request_time),
        duration_ms=float(info.execution_duration) if info.execution_duration is not None else None,
        state=getattr(info.state, "value", str(info.state)),
        name=safe_span_name(name),
        source=source_of(tags, run_linked=bool(metadata.get(SOURCE_RUN_KEY))),
        runtime=runtime_of(metadata.get(SOURCE_NAME_KEY)),
        view=safe_value(tags["view"]) if tags.get("view") else None,
        config={tag: safe_value(tags[tag]) for tag in CONFIG_TAGS if tags.get(tag)},
        ratings=_ratings(info),
        spans=records,
        answer=answer_record(root) if root is not None and name == ANSWER_SPAN else None,
    )


# --- reading the experiment ----------------------------------------------------------------------


def window_filter(since_ms: int, until_ms: int, source: str | None = None) -> str:
    """The search filter for traces that started in ``[since_ms, until_ms)``.

    ``source`` adds the ``source`` tag, for a source that is told by that tag.
    It is checked to be a plain name before it is put into the filter.
    """
    clauses = [
        f"attributes.timestamp_ms >= {int(since_ms)}",
        f"attributes.timestamp_ms < {int(until_ms)}",
    ]
    if source is not None:
        if not _SOURCE_RE.fullmatch(source):
            msg = f"not a source name: {source!r}"
            raise ValueError(msg)
        clauses.append(f"tags.source = '{source}'")
    return " AND ".join(clauses)


def read_traces(
    experiment_id: str,
    since_ms: int,
    until_ms: int,
    *,
    source: str = SOURCE_WEB,
    limit: int | None = None,
) -> list[TraceRecord]:
    """Every trace of the window as a record, with spans for the requests of ``source``.

    With ``limit``, spans are read for the newest ``limit`` requests of the
    source only. ``summarise`` is given the same limit and reports on those.
    """
    # Imported here so that --help, and the tests of the arithmetic, do not load MLflow.
    import mlflow

    # ``mlflow.search_traces`` follows the page tokens itself and returns every match.
    infos = mlflow.search_traces(
        locations=[experiment_id],
        filter_string=window_filter(since_ms, until_ms),
        return_type="list",
        include_spans=False,
    )
    records = [to_record(trace.info) for trace in infos]
    chosen = select(records, source, limit)
    if not chosen:
        return records

    by_tag = source not in {SOURCE_ALL, SOURCE_EVALUATION, SOURCE_UNTAGGED}
    full = mlflow.search_traces(
        locations=[experiment_id],
        # Only as much of the window as the chosen requests span.
        filter_string=window_filter(
            chosen[-1].started_ms, chosen[0].started_ms + 1, source if by_tag else None
        ),
        return_type="list",
        include_spans=True,
    )
    wanted = {record.trace_id for record in chosen}
    with_spans = {
        str(trace.info.trace_id): to_record(trace.info, trace.data.spans)
        for trace in full
        if str(trace.info.trace_id) in wanted and trace.data.spans
    }
    # A trace the second search did not return keeps its first record, which has no spans.
    return [with_spans.get(record.trace_id, record) for record in records]


def open_experiment(wanted: str | None = None) -> tuple[str, str]:
    """Point MLflow at the workspace and find the experiment. Returns its id and its name.

    ``wanted`` is a path or an id; without it the experiment of the settings is
    used. The experiment is looked up and never created: a report only reads.

    Raises:
        SystemExit: If no experiment is named, or the one named does not exist.
    """
    # Imported here so that --help, and the tests of the arithmetic, do not load MLflow.
    import mlflow
    from dotenv import load_dotenv

    from copilot.config import load_settings

    # Puts DATABRICKS_HOST and DATABRICKS_CONFIG_PROFILE where the SDK and MLflow look.
    load_dotenv()
    wanted = wanted or load_settings().mlflow_experiment
    if not wanted:
        print("not started: no experiment is set (MLFLOW_EXPERIMENT) and none was given")
        raise SystemExit(1)
    mlflow.set_tracking_uri("databricks")
    experiment = find_experiment(wanted)
    if experiment is None:
        print("not started: the experiment does not exist, and a report does not create one")
        raise SystemExit(1)
    return str(experiment.experiment_id), str(experiment.name)


def find_experiment(name_or_id: str) -> Any:
    """The experiment with this path or id on the current tracking server, or None."""
    import mlflow

    if name_or_id.isdigit():
        try:
            return mlflow.get_experiment(name_or_id)
        except Exception:
            return None
    return mlflow.get_experiment_by_name(name_or_id)


# --- the window and the provenance ---------------------------------------------------------------


def parse_time(text: str) -> int:
    """A date (``2026-11-14``) or a date and time, read as UTC, in milliseconds."""
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp() * 1000)


def window_of(
    *, days: float | None, since: str | None, until: str | None, now_ms: int
) -> tuple[int, int]:
    """The window ``[since, until)`` in milliseconds.

    ``--since`` and ``--until`` name it outright; ``--until`` alone or
    ``--days`` count back from the end. Without any, it is the last 7 days.

    Raises:
        ValueError: If the window is empty, or ``--days`` is given with ``--since``.
    """
    if since is not None and days is not None:
        msg = "give --days or --since, not both"
        raise ValueError(msg)
    until_ms = parse_time(until) if until is not None else now_ms
    if since is not None:
        since_ms = parse_time(since)
    else:
        since_ms = until_ms - int((days if days is not None else DEFAULT_DAYS) * DAY_MS)
    if since_ms >= until_ms:
        msg = "the window is empty: --since must be before --until"
        raise ValueError(msg)
    return since_ms, until_ms


def _utc(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def provenance(
    *,
    experiment_name: str,
    experiment_id: str,
    since_ms: int,
    until_ms: int,
    now_ms: int,
    limit: int | None,
    mlflow_version: str,
) -> dict[str, Any]:
    """What a reader needs to know about how the report was made."""
    return {
        "generated_at": _utc(now_ms),
        "git_sha": _git("rev-parse", "HEAD"),
        # Saved reports themselves do not make the code "dirty".
        "git_dirty": bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results")),
        "mlflow_version": mlflow_version,
        "experiment": {
            # The last part of the path only: the rest is the owner's workspace folder,
            # which names a person.
            "name": experiment_name.rstrip("/").rsplit("/", 1)[-1],
            "id": experiment_id,
        },
        "window": {
            "since": _utc(since_ms),
            "until": _utc(until_ms),
            "days": round((until_ms - since_ms) / DAY_MS, 2),
        },
        "limit": limit,
    }


def build_report(
    records: Sequence[TraceRecord], *, source: str, about: Mapping[str, Any]
) -> dict[str, Any]:
    """The whole report as plain data: how it was made, then every number."""
    return {
        "provenance": dict(about),
        **summarise(records, source=source, limit=about.get("limit")),
    }


def save(report: Mapping[str, Any], results_dir: Path = RESULTS_DIR) -> tuple[Path, Path]:
    """Write the page and its numbers. Returns the two paths."""
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = f"monitoring_{report['provenance']['window']['until'][:10]}"
    if report["source"] != SOURCE_WEB:
        stem += f"_{report['source']}"
    page, numbers = results_dir / f"{stem}.md", results_dir / f"{stem}.json"
    page.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    numbers.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return page, numbers


# --- the command ---------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Print the report, and with ``--save`` write it to ``eval/results``."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--days", type=float, default=None, help="how far back to look (7)")
    parser.add_argument("--since", default=None, help="start of the window, UTC: 2026-11-14")
    parser.add_argument("--until", default=None, help="end of the window, UTC; now if left out")
    parser.add_argument(
        "--source",
        default=SOURCE_WEB,
        help="whose requests to report: web (real use), evaluation, untagged, any other "
        "`source` tag, or all",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="read only the newest N requests; saves nothing"
    )
    parser.add_argument("--experiment", default=None, help="experiment path or id, not the set one")
    parser.add_argument("--save", action="store_true", help="write the report to eval/results")
    args = parser.parse_args(argv)

    if args.save and args.limit is not None:
        parser.error("--limit is a quick look; it cannot be saved")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if not _SOURCE_RE.fullmatch(args.source):
        parser.error("--source must be a plain name, such as web or evaluation")
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    try:
        since_ms, until_ms = window_of(
            days=args.days, since=args.since, until=args.until, now_ms=now_ms
        )
    except ValueError as error:
        parser.error(str(error))
    dirty = bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results"))
    if args.save and dirty:
        print("not started: commit first, so the report names the code that made it")
        raise SystemExit(1)

    experiment_id, experiment_name = open_experiment(args.experiment)
    records = read_traces(experiment_id, since_ms, until_ms, source=args.source, limit=args.limit)
    report = build_report(
        records,
        source=args.source,
        about=provenance(
            experiment_name=experiment_name,
            experiment_id=experiment_id,
            since_ms=since_ms,
            until_ms=until_ms,
            now_ms=now_ms,
            limit=args.limit,
            mlflow_version=version("mlflow"),
        ),
    )
    print(render_markdown(report), end="")
    if args.save:
        page, numbers = save(report, RESULTS_DIR)
        print(f"\nsaved {page.as_posix()} and {numbers.as_posix()}")


if __name__ == "__main__":
    main()
