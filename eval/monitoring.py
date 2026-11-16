"""What the monitoring report works out from the copilot's traces. No MLflow, no workspace.

``eval.monitoring_report`` reads traces and turns each one into a ``TraceRecord``.
Everything here is a pure function of those records: which requests are real
use, where they went, how long each stage took, what failed, and what the
ratings say. ``summarise`` returns the numbers and ``render_markdown`` prints
them, so the saved Markdown file and the saved JSON file hold the same figures.

Two rules shape this module.

**No text from a trace.** A record has no field for a question, an answer or a
tool argument, so none can reach the report. What a record does hold is counts,
durations, ids and names, and a name is only kept when it cannot be free text:

- a tool name must be one of the copilot's tools. The model writes the name of
  the tool it calls, so a tool it made up would otherwise put the model's words
  in a span name and in a ``tool_error`` flag;
- a flag must be one the code defines;
- any other name (a span the code opened, a tag value, the type of an
  exception) must look like an identifier. A value with a space in it is shown
  as ``(not a plain name)``.

**No rate without its count.** Every rate carries the count it rests on and a
95% Wilson interval. Below ``MIN_FOR_RATE`` rows the report prints the count and
the interval and no percentage, and a percentile is printed only when it is not
simply the largest value seen.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from eval.stats import percentile, rate_with_interval, wilson_interval

# --- names --------------------------------------------------------------------------------------

# The copilot's tools and guardrail flags. A test keeps both lists equal to the code's.
KNOWN_TOOLS: tuple[str, ...] = (
    "search_kb",
    "get_plan_details",
    "summarize_call",
    "escalate_to_human",
)
KNOWN_FLAGS: tuple[str, ...] = (
    "pii_in_question",
    "history_turn_dropped",
    "account_action_requested",
    "injection_suspected",
    "router_unavailable",
    "tool_error",
    "tool_limit_reached",
    "no_context",
    "empty_answer",
    "invalid_citation_removed",
    "no_citation",
    "answer_simplified",
    "rewrite_changed_facts",
    "pii_removed_from_answer",
    "unsupported_claim",
)
FLAG_ROUTER_FALLBACK = "router_unavailable"
FLAG_INJECTION = "injection_suspected"
FLAG_TOOL_ERROR = "tool_error"

# The spans the copilot opens for one answer (``copilot.agent``).
ANSWER_SPAN = "run_copilot"
ROUTER_SPAN = "route_request"
MODEL_SPAN = "generate_answer"
REWRITE_SPAN = "simplify_answer"
MODEL_CALL_SPANS: tuple[str, ...] = (ROUTER_SPAN, MODEL_SPAN, REWRITE_SPAN)
TOOL_PREFIX = "tool_"

# The trace tags that say how the copilot was set up when it answered.
CONFIG_TAGS: tuple[str, ...] = (
    "prompt_version",
    "llm_endpoint",
    "router",
    "router_endpoint",
    "router_prompt_version",
    "chunk_config",
    "query_type",
)

SOURCE_WEB = "web"
SOURCE_EVALUATION = "evaluation"
SOURCE_UNTAGGED = "untagged"
SOURCE_ALL = "all"

RUNTIME_APP = "databricks_app"
RUNTIME_LOCAL = "local"
RUNTIME_UNKNOWN = "unknown"
# Where Databricks Apps keeps an app's code. Seen on every trace the deployed app wrote.
_APP_SOURCE_PREFIX = "/app/python/"

NOT_A_NAME = "(not a plain name)"
UNLISTED_TOOL = "(unlisted tool)"
UNLISTED_FLAG = "(unlisted flag)"
NOT_RECORDED = "(not recorded)"

_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,59}")
_VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,59}")

# --- how much data a figure needs ----------------------------------------------------------------

# Below this many rows a rate is given as a count and an interval, with no percentage.
MIN_FOR_RATE = 20
# With fewer values than this, the nearest-rank percentile is just the largest value.
MIN_FOR_P90 = 10
MIN_FOR_P99 = 100
# The most ids one list in the report holds. The count beside it is always the full count.
MAX_IDS = 50


def safe_name(text: object) -> str:
    """``text`` if it looks like an identifier, such as a span name or an exception type."""
    return text if isinstance(text, str) and _NAME_RE.fullmatch(text) else NOT_A_NAME


def safe_value(text: object) -> str:
    """``text`` if it looks like a tag value the code sets, such as an endpoint name."""
    return text if isinstance(text, str) and _VALUE_RE.fullmatch(text) else NOT_A_NAME


def safe_span_name(name: object) -> str:
    """A span name that is safe to print.

    The copilot names a tool's span after the tool the model asked for, so only
    the name of a real tool is kept.
    """
    if isinstance(name, str) and name.startswith(TOOL_PREFIX):
        tool = name.removeprefix(TOOL_PREFIX)
        return name if tool in KNOWN_TOOLS else f"{TOOL_PREFIX}{UNLISTED_TOOL}"
    return safe_name(name)


def safe_flag(flag: object) -> str:
    """A guardrail flag that is safe to print: one the code defines, with a plain detail."""
    if not isinstance(flag, str):
        return UNLISTED_FLAG
    base, _, detail = flag.partition(":")
    if base not in KNOWN_FLAGS:
        return UNLISTED_FLAG
    if not detail:
        return base
    if base == FLAG_TOOL_ERROR:
        return f"{base}:{detail if detail in KNOWN_TOOLS else UNLISTED_TOOL}"
    return f"{base}:{detail if _NAME_RE.fullmatch(detail) else NOT_A_NAME}"


def source_of(tags: Mapping[str, str], *, run_linked: bool) -> str:
    """Which kind of use wrote a trace.

    The web app tags every request ``source=web``. An evaluation run tags each
    row ``eval_id`` and runs inside an MLflow run, which MLflow records on the
    trace. Anything else is ``untagged``: a script, a notebook, a test against
    the workspace. Those cannot be told apart from each other.
    """
    named = tags.get("source")
    if named:
        return safe_value(named)
    if tags.get("eval_id") or run_linked:
        return SOURCE_EVALUATION
    return SOURCE_UNTAGGED


def runtime_of(source_name: str | None) -> str:
    """Whether a trace was written by the deployed app or by a process on someone's machine.

    This reads the path of the program that wrote the trace, which MLflow
    records. It is a guess from a path, not a tag the copilot sets.
    """
    if not source_name:
        return RUNTIME_UNKNOWN
    return RUNTIME_APP if source_name.startswith(_APP_SOURCE_PREFIX) else RUNTIME_LOCAL


# --- the records ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SpanRecord:
    """One span, without what went in or came out of it."""

    name: str
    kind: str
    # 0 for the root span, 1 for a span opened directly under it, and so on.
    depth: int
    # The name of the span this one is inside. None for the root.
    parent: str | None
    started_ms: float
    # None when the span never ended.
    duration_ms: float | None
    failed: bool = False
    # The type of the exception that ended the span, such as ``TimeoutError``.
    exception: str | None = None
    # What happened inside a span that ended normally. For a tool: ``rejected`` (the
    # tool refused its arguments) or ``unreachable``. For the router: ``used``,
    # ``unreachable`` or ``unreadable``.
    note: str | None = None


@dataclass(frozen=True)
class AnswerRecord:
    """What the root span says about one answer. The answer itself is not here."""

    escalated: bool = False
    flags: tuple[str, ...] = ()
    handoff_drafted: bool = False
    citations: int = 0
    # None on a trace written before the copilot recorded its model work.
    model_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Model calls whose reply carried no token count.
    calls_without_counts: int | None = None


@dataclass(frozen=True)
class RatingRecord:
    """One thumbs up or down."""

    helpful: bool
    at_ms: int


@dataclass(frozen=True)
class TraceRecord:
    """One request, as far as the report needs it."""

    trace_id: str
    started_ms: int
    # None when the trace has no end time.
    duration_ms: float | None
    # OK, ERROR, IN_PROGRESS or STATE_UNSPECIFIED.
    state: str
    # The name of the root span: ``run_copilot`` for an answer.
    name: str
    source: str
    runtime: str = RUNTIME_UNKNOWN
    view: str | None = None
    config: Mapping[str, str] | None = None
    ratings: tuple[RatingRecord, ...] = ()
    # None when the trace's spans could not be read.
    spans: tuple[SpanRecord, ...] | None = None
    # None when this is not an answer, or its root span could not be read.
    answer: AnswerRecord | None = None

    @property
    def is_answer(self) -> bool:
        """Whether this request was a question to the copilot."""
        return self.name == ANSWER_SPAN

    @property
    def day(self) -> str:
        """The UTC day the request started on."""
        return datetime.fromtimestamp(self.started_ms / 1000, UTC).strftime("%Y-%m-%d")


# --- the levels ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Level:
    """One line of "what to look at": a figure, the level it is held to, and why."""

    key: str
    # A share from 0 to 1 for ``rate``, seconds for ``seconds``, a number of requests for ``count``.
    level: float
    kind: str
    what: str
    why: str


# Every level the report holds the copilot to. They are a first proposal: nobody has
# tuned them against real incidents, and the report says so wherever it uses them.
LEVELS: tuple[Level, ...] = (
    Level(
        "span_data_missing",
        0,
        "count",
        "requests whose spans could not be read",
        "Such a request shows its state and its total time and nothing else: no route, no "
        "flags, no stage times. One is enough to mean that whatever wrote it could not "
        "store its spans.",
    ),
    Level(
        "error_rate",
        0.02,
        "rate",
        "requests whose trace ended in the error state",
        "A tool or a router that fails is caught and the answer goes on, so the error "
        "state means the agent got no answer at all.",
    ),
    Level(
        "unfinished",
        0,
        "count",
        "requests whose trace never finished",
        "A trace still in progress long after it started means the process died mid-answer.",
    ),
    Level(
        "router_fallback_rate",
        0.05,
        "rate",
        "answers routed by the rules because the router could not be reached or read, "
        "of the answers where the router was asked",
        "On the held-out routing set the rules alone missed most hand-off requests, so a "
        "fallback is a request routed by the weaker of the two.",
    ),
    Level(
        "tool_error_rate",
        0.05,
        "rate",
        "failed calls of one tool, of that tool's calls",
        "The model is told the lookup failed and says so, which is an answer with nothing "
        "in it. One call in twenty is already a tool that needs looking at.",
    ),
    Level(
        "answer_p90_seconds",
        8.0,
        "seconds",
        "the time nine answers in ten finish within",
        "The agent waits for the answer with a customer on the line. Eight seconds is a "
        "round number above what a normal answer with one search takes.",
    ),
    Level(
        "unhelpful_rate",
        0.20,
        "rate",
        "rated answers that were marked not helpful",
        "Few answers are rated and unhappy people rate more often, so this starts high. "
        "The ids matter more than the rate.",
    ),
    Level(
        "empty_answer",
        0,
        "count",
        "answers where the model returned nothing",
        "The agent is told to pass the question to a person. One is worth opening.",
    ),
    Level(
        "tool_limit_rate",
        0.05,
        "rate",
        "answers that used every allowed round of tool calls",
        "The model kept asking for tools until it was stopped, which is slow and usually "
        "means it could not find what it wanted.",
    ),
    Level(
        "pii_in_answer_rate",
        0.05,
        "rate",
        "answers from which the output check removed something that looked like personal data",
        "The question is redacted before the model sees it, so the model should have "
        "nothing personal to write. A steady share means the redactor is missing "
        "something, or the check is misfiring.",
    ),
    Level(
        "unsupported_claim_rate",
        0.10,
        "rate",
        "answers with a figure that is in none of the text the copilot was given",
        "The claim check flags and does not block, so these answers reached the agent.",
    ),
    Level(
        "token_counts_missing_rate",
        0.10,
        "rate",
        "answers with no token count, or with one that is incomplete",
        "Tokens are the cost of the copilot. Above this share the totals in this report "
        "understate it too much to use.",
    ),
)
LEVEL_BY_KEY: dict[str, Level] = {level.key: level for level in LEVELS}

STATUS_LOOK = "look"
STATUS_FEW = "few"
STATUS_OK = "ok"
STATUS_NO_DATA = "no_data"


# --- small arithmetic ----------------------------------------------------------------------------


def rate(count: int, of: int) -> dict[str, Any]:
    """A share with the counts it rests on and its 95% Wilson interval.

    ``few`` is true when there are too few rows to print a percentage.
    """
    if of <= 0:
        return {"count": count, "of": 0, "rate": None, "ci95": None, "few": True}
    low, high = wilson_interval(count, of)
    return {
        "count": count,
        "of": of,
        "rate": round(count / of, 4),
        "ci95": [round(low, 4), round(high, 4)],
        "few": of < MIN_FOR_RATE,
    }


def spread(values: Iterable[float]) -> dict[str, Any]:
    """Median, tail and largest of some values.

    ``p90`` and ``p99`` are None when there are so few values that the
    percentile would be the largest one, which ``max`` already gives.
    """
    numbers = [float(value) for value in values]
    count = len(numbers)
    if not count:
        return {"n": 0, "mean": None, "p50": None, "p90": None, "p99": None, "max": None}
    return {
        "n": count,
        "mean": round(statistics.fmean(numbers), 2),
        "p50": round(percentile(numbers, 0.5), 2),
        "p90": round(percentile(numbers, 0.9), 2) if count >= MIN_FOR_P90 else None,
        "p99": round(percentile(numbers, 0.99), 2) if count >= MIN_FOR_P99 else None,
        "max": round(max(numbers), 2),
    }


def outcome_of(answer: AnswerRecord) -> str:
    """Where an answer went: ``handed_off``, ``refused`` or ``answered``.

    The same rule ``eval.routing_eval`` scores the whole copilot by: a hand-off
    when the answer says a person is needed, a refusal when an attempt to
    override the instructions was flagged, and an answer otherwise.
    """
    if answer.escalated:
        return "handed_off"
    if FLAG_INJECTION in answer.flags:
        return "refused"
    return "answered"


def _ids(records: Iterable[TraceRecord]) -> list[str]:
    """The ids of some requests, newest first, at most ``MAX_IDS`` of them."""
    newest_first = sorted(records, key=lambda record: record.started_ms, reverse=True)
    return [record.trace_id for record in newest_first[:MAX_IDS]]


def _has_span(record: TraceRecord, name: str) -> bool:
    return any(span.name == name for span in record.spans or ())


def _flagged(record: TraceRecord, base: str) -> bool:
    """Whether an answer carries the flag ``base``, with or without a detail after it."""
    flags = record.answer.flags if record.answer else ()
    return any(flag == base or flag.startswith(f"{base}:") for flag in flags)


# --- the parts of the report ---------------------------------------------------------------------


def select(
    records: Sequence[TraceRecord], source: str, limit: int | None = None
) -> list[TraceRecord]:
    """The requests of one source, or every request for ``all``, newest first.

    ``limit`` keeps the newest that many, for a quick look.
    """
    chosen = [record for record in records if source in {SOURCE_ALL, record.source}]
    chosen.sort(key=lambda record: (record.started_ms, record.trace_id), reverse=True)
    return chosen if limit is None else chosen[:limit]


def volume(records: Sequence[TraceRecord]) -> dict[str, Any]:
    """Every trace in the window, by UTC day and by source."""
    by_source = Counter(record.source for record in records)
    by_day: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        by_day[record.day][record.source] += 1
    # Real use first, then the largest.
    sources = sorted(by_source, key=lambda name: (name != SOURCE_WEB, -by_source[name], name))
    return {
        "traces": len(records),
        "sources": sources,
        "by_source": {name: by_source[name] for name in sources},
        "by_day": [
            {"day": day, "total": sum(by_day[day].values()), "by_source": dict(by_day[day])}
            for day in sorted(by_day)
        ],
    }


def requests(chosen: Sequence[TraceRecord]) -> dict[str, Any]:
    """The chosen requests by what was asked for, by where they ran, and by setup."""
    kinds = Counter((record.name, record.view or "") for record in chosen)
    answers = [record for record in chosen if record.is_answer]
    without_spans = [record for record in chosen if record.spans is None]
    setup = []
    for tag in CONFIG_TAGS:
        seen: dict[str, list[str]] = defaultdict(list)
        for record in answers:
            seen[(record.config or {}).get(tag) or NOT_RECORDED].append(record.day)
        values = [
            {"value": value, "answers": len(days), "first_day": min(days), "last_day": max(days)}
            for value, days in sorted(seen.items(), key=lambda item: (min(item[1]), item[0]))
        ]
        setup.append({"tag": tag, "values": values})
    return {
        "traces": len(chosen),
        "answers": len(answers),
        "answers_with_spans": sum(1 for record in answers if record.answer is not None),
        "without_spans": len(without_spans),
        "without_spans_by_runtime": dict(Counter(record.runtime for record in without_spans)),
        "without_span_ids": _ids(without_spans),
        "by_kind": [
            {"name": name, "view": view or None, "count": count}
            for (name, view), count in sorted(kinds.items(), key=lambda item: (-item[1], item[0]))
        ],
        "by_runtime": dict(Counter(record.runtime for record in chosen)),
        "setup": setup,
    }


def routing(answers: Sequence[TraceRecord]) -> dict[str, Any]:
    """Where answers went, how the router did, and every guardrail flag.

    ``answers`` are the answers whose root span could be read.
    """
    total = len(answers)
    outcomes = Counter(outcome_of(record.answer) for record in answers if record.answer)
    handed_off = [record for record in answers if record.answer and record.answer.escalated]
    by_model = sum(1 for record in handed_off if _has_span(record, MODEL_SPAN))
    asked = [record for record in answers if _has_span(record, ROUTER_SPAN)]
    fell_back = [record for record in asked if _flagged(record, FLAG_ROUTER_FALLBACK)]
    router_notes = Counter(
        span.note or NOT_RECORDED
        for record in asked
        for span in record.spans or ()
        if span.name == ROUTER_SPAN
    )
    settings = Counter((record.config or {}).get("router") or NOT_RECORDED for record in answers)
    with_flag: Counter[str] = Counter()
    for record in answers:
        with_flag.update(set(record.answer.flags if record.answer else ()))
    return {
        "answers": total,
        "outcomes": {
            name: rate(outcomes[name], total) for name in ("answered", "handed_off", "refused")
        },
        "handed_off_by": {
            "input_check": len(handed_off) - by_model,
            "answering_model": by_model,
        },
        "handoff_drafted": sum(
            1 for record in answers if record.answer and record.answer.handoff_drafted
        ),
        "router": {
            "setting": dict(settings),
            "asked": len(asked),
            # With the model router on, a request the rules hand off never reaches it.
            "not_asked": total - len(asked),
            "fallback": rate(len(fell_back), len(asked)),
            "fallback_ids": _ids(fell_back),
            "span_notes": dict(router_notes),
        },
        "flags": [
            {"flag": flag, **rate(count, total)}
            for flag, count in sorted(with_flag.items(), key=lambda item: (-item[1], item[0]))
        ],
        "unflagged": rate(
            sum(1 for record in answers if record.answer and not record.answer.flags), total
        ),
    }


def tools(answers: Sequence[TraceRecord]) -> list[dict[str, Any]]:
    """Each tool: how often it was called, in how many answers, and how often it failed."""
    calls: Counter[str] = Counter()
    used_in: Counter[str] = Counter()
    failed: dict[str, Counter[str]] = defaultdict(Counter)
    for record in answers:
        names = set()
        for span in record.spans or ():
            if span.depth != 1 or not span.name.startswith(TOOL_PREFIX):
                continue
            tool = span.name.removeprefix(TOOL_PREFIX)
            names.add(tool)
            calls[tool] += 1
            if span.failed:
                failed[tool][span.exception or "span_error"] += 1
            elif span.note in {"rejected", "unreachable"}:
                failed[tool][span.note] += 1
        used_in.update(names)
    return [
        {
            "tool": tool,
            "calls": calls[tool],
            "answers": used_in[tool],
            "errors": rate(sum(failed[tool].values()), calls[tool]),
            "errors_by_kind": dict(failed[tool]),
        }
        for tool in sorted(calls, key=lambda name: (-calls[name], name))
    ]


def _stage_rows(answers: Sequence[TraceRecord]) -> list[dict[str, Any]]:
    """Per-call times of every span under the root, and the time no span accounts for."""
    durations: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    seen_in: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    order: dict[tuple[str, str, str], float] = {}
    remainders: list[float] = []

    def add(key: tuple[str, str, str], record: TraceRecord, span: SpanRecord) -> None:
        if span.duration_ms is None:
            return
        durations[key].append(span.duration_ms)
        seen_in[key].add(record.trace_id)
        # Stages are listed by how early in an answer each one has started.
        offset = span.started_ms - record.started_ms
        order[key] = min(order.get(key, offset), offset)

    for record in answers:
        spans = sorted(record.spans or (), key=lambda span: span.started_ms)
        root = next((span for span in spans if span.depth == 0), None)
        model_turns = 0
        for span in spans:
            if span.depth == 0:
                continue
            inside = span.parent if span.depth > 1 and span.parent else ""
            add((span.name, span.kind, inside), record, span)
            if span.name == MODEL_SPAN and span.depth == 1:
                model_turns += 1
                turn = "first call" if model_turns == 1 else "later calls"
                add((f"{MODEL_SPAN}, {turn}", span.kind, ""), record, span)
        if root is not None and root.duration_ms is not None:
            direct = sum(span.duration_ms or 0.0 for span in spans if span.depth == 1)
            remainders.append(max(0.0, root.duration_ms - direct))

    top_level = {name: order[key] for key in order for name, _, inside in [key] if not inside}

    def placed(key: tuple[str, str, str]) -> tuple[float, bool, tuple[str, str, str]]:
        """A stage inside another, or a part of one, is listed straight after it."""
        name, _, inside = key
        anchor = inside or name.split(",")[0]
        return (top_level.get(anchor, order[key]), bool(inside), key)

    rows = [
        {
            "stage": name,
            "kind": kind,
            "inside": inside or None,
            "answers": len(seen_in[key]),
            **spread(durations[key]),
        }
        for key in sorted(durations, key=placed)
        for name, kind, inside in [key]
    ]
    if remainders:
        rows.append(
            {
                "stage": "(time in no span)",
                "kind": "",
                "inside": None,
                "answers": len(remainders),
                **spread(remainders),
            }
        )
    return rows


def latency(chosen: Sequence[TraceRecord]) -> dict[str, Any]:
    """Milliseconds: the whole answer, each stage of it, and the other kinds of request."""
    answers = [record for record in chosen if record.is_answer]
    timed = [record for record in answers if record.duration_ms is not None]
    by_outcome: dict[str, list[float]] = defaultdict(list)
    for record in timed:
        if record.answer is not None and record.duration_ms is not None:
            by_outcome[outcome_of(record.answer)].append(record.duration_ms)
    others: dict[str, list[float]] = defaultdict(list)
    for record in chosen:
        if not record.is_answer and record.duration_ms is not None:
            others[record.name].append(record.duration_ms)
    return {
        "unit": "ms",
        "answer": spread(record.duration_ms for record in timed if record.duration_ms is not None),
        "answer_by_outcome": {
            name: spread(by_outcome[name])
            for name in ("answered", "handed_off", "refused")
            if by_outcome[name]
        },
        "stages": _stage_rows([record for record in answers if record.spans]),
        "other_requests": [
            {"name": name, **spread(values)} for name, values in sorted(others.items())
        ],
    }


def model_work(answers: Sequence[TraceRecord]) -> dict[str, Any]:
    """Model calls and tokens per answer, and how many answers have no usable count.

    A token count is missing in two ways. An older trace has no count at all. A
    newer one has a count, but a model call whose reply carried none adds
    nothing to it, so the total is a lower bound.
    """
    total = len(answers)
    counted = [
        record for record in answers if record.answer and record.answer.model_calls is not None
    ]
    partial: list[TraceRecord] = []
    complete: list[TraceRecord] = []
    for record in counted:
        answer = record.answer
        if answer is None or answer.model_calls is None:
            continue
        if answer.calls_without_counts is None:
            # Not said, so judged from the totals: calls were made and no token was counted.
            lacks = answer.model_calls > 0 and not (answer.input_tokens or answer.output_tokens)
        else:
            lacks = answer.calls_without_counts > 0
        (partial if lacks else complete).append(record)
    called = [record for record in complete if record.answer and record.answer.model_calls]
    tokens_in = [float(record.answer.input_tokens or 0) for record in called if record.answer]
    tokens_out = [float(record.answer.output_tokens or 0) for record in called if record.answer]
    return {
        "answers": total,
        "counted": len(counted),
        "not_recorded": total - len(counted),
        "incomplete": len(partial),
        "token_counts_missing": rate(total - len(counted) + len(partial), total),
        "no_model_call": len(complete) - len(called),
        "model_calls": spread(
            float(record.answer.model_calls or 0) for record in counted if record.answer
        ),
        "input_tokens": spread(tokens_in),
        "output_tokens": spread(tokens_out),
        "total_tokens": spread(a + b for a, b in zip(tokens_in, tokens_out, strict=True)),
        "sum_input_tokens": int(sum(tokens_in)),
        "sum_output_tokens": int(sum(tokens_out)),
        # Counted from the spans, so it is there for a trace with no recorded count too.
        "model_call_spans": spread(
            float(sum(1 for span in record.spans or () if span.name in MODEL_CALL_SPANS))
            for record in answers
        ),
    }


def _error_origin(record: TraceRecord) -> tuple[str, str]:
    """The span a failed request broke in, and the type of the exception.

    An exception passes up through every span around it, so the origin is the
    deepest failed span, and the earliest of those.
    """
    if record.spans is None:
        return ("(span data missing)", NOT_RECORDED)
    failed = [span for span in record.spans if span.failed]
    if not failed:
        return ("(no failed span)", NOT_RECORDED)
    origin = min(failed, key=lambda span: (-span.depth, span.started_ms))
    return (origin.name, origin.exception or NOT_RECORDED)


def failures(chosen: Sequence[TraceRecord]) -> dict[str, Any]:
    """Requests that ended in error or never ended, and where they broke."""
    errored = [record for record in chosen if record.state == "ERROR"]
    unfinished = [record for record in chosen if record.state == "IN_PROGRESS"]
    origins = Counter(_error_origin(record) for record in errored)
    return {
        "traces": len(chosen),
        "errors": rate(len(errored), len(chosen)),
        "error_ids": _ids(errored),
        "errors_by_origin": [
            {"span": span, "exception": exception, "count": count}
            for (span, exception), count in sorted(
                origins.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "unfinished": len(unfinished),
        "unfinished_ids": _ids(unfinished),
        "tools": tools([record for record in chosen if record.is_answer and record.spans]),
    }


def feedback(chosen: Sequence[TraceRecord]) -> dict[str, Any]:
    """How many answers were rated and what the ratings say.

    An answer rated more than once counts once, by its latest rating. A rating
    belongs to its trace, so one given this week to an answer from before the
    window is not counted here.
    """
    answers = [record for record in chosen if record.is_answer]
    rated = [record for record in answers if record.ratings]
    latest = {
        record.trace_id: max(record.ratings, key=lambda rating: rating.at_ms).helpful
        for record in rated
    }
    unhelpful = [record for record in rated if not latest[record.trace_id]]
    return {
        "answers": len(answers),
        "rated": rate(len(rated), len(answers)),
        "helpful": rate(len(rated) - len(unhelpful), len(rated)),
        "unhelpful": len(unhelpful),
        "unhelpful_ids": _ids(unhelpful),
        "rated_more_than_once": sum(1 for record in rated if len(record.ratings) > 1),
        "ratings_on_other_requests": sum(
            1 for record in chosen if not record.is_answer and record.ratings
        ),
    }


def by_day(chosen: Sequence[TraceRecord]) -> list[dict[str, Any]]:
    """The chosen requests day by day, so a change inside the window shows."""
    days: dict[str, list[TraceRecord]] = defaultdict(list)
    for record in chosen:
        days[record.day].append(record)
    rows = []
    for day in sorted(days):
        records = days[day]
        answers = [record for record in records if record.is_answer]
        read = [record for record in answers if record.answer is not None]
        outcomes = Counter(outcome_of(record.answer) for record in read if record.answer)
        times = [record.duration_ms for record in answers if record.duration_ms is not None]
        latest = [
            max(record.ratings, key=lambda rating: rating.at_ms).helpful
            for record in answers
            if record.ratings
        ]
        rows.append(
            {
                "day": day,
                "requests": len(records),
                "answers": len(answers),
                "answers_read": len(read),
                "handed_off": outcomes["handed_off"],
                "refused": outcomes["refused"],
                "router_fallback": sum(
                    1 for record in read if _flagged(record, FLAG_ROUTER_FALLBACK)
                ),
                "errors": sum(1 for record in records if record.state == "ERROR"),
                "answer_p50_ms": round(percentile(times, 0.5), 2) if times else None,
                "rated": len(latest),
                "unhelpful": sum(1 for helpful in latest if not helpful),
            }
        )
    return rows


# --- what to look at -----------------------------------------------------------------------------


def _percent(share: float) -> str:
    return f"{share * 100:.0f}%"


def _rate_check(key: str, measured: Mapping[str, Any], ids: Sequence[str] = ()) -> dict[str, Any]:
    """Hold one share to its level.

    Above the level with at least ``MIN_FOR_RATE`` rows it is something to look
    at. Above it with fewer rows it is reported as seen, with no claim about
    the rate.
    """
    level = LEVEL_BY_KEY[key]
    count, of = int(measured["count"]), int(measured["of"])
    if of == 0:
        status = STATUS_NO_DATA
    elif count / of <= level.level:
        status = STATUS_OK
    else:
        status = STATUS_FEW if of < MIN_FOR_RATE else STATUS_LOOK
    return {
        "key": key,
        "status": status,
        "kind": level.kind,
        "level": level.level,
        "count": count,
        "of": of,
        "ids": list(ids),
    }


def _count_check(key: str, count: int, of: int, ids: Sequence[str] = ()) -> dict[str, Any]:
    level = LEVEL_BY_KEY[key]
    status = STATUS_OK
    if of == 0:
        status = STATUS_NO_DATA
    elif count > level.level:
        status = STATUS_LOOK
    return {
        "key": key,
        "status": status,
        "kind": level.kind,
        "level": level.level,
        "count": count,
        "of": of,
        "ids": list(ids),
    }


def checks(summary: Mapping[str, Any], chosen: Sequence[TraceRecord]) -> list[dict[str, Any]]:
    """Every level in ``LEVELS``, held against the figures of this window."""
    answers = [record for record in chosen if record.is_answer]
    read = [record for record in answers if record.answer is not None]
    asked = summary["requests"]
    routed = summary["routing"]
    failed = summary["failures"]
    rated = summary["feedback"]

    def flag_share(base: str) -> tuple[dict[str, Any], list[str]]:
        hit = [record for record in read if _flagged(record, base)]
        return rate(len(hit), len(read)), _ids(hit)

    found = [
        _count_check(
            "span_data_missing", asked["without_spans"], asked["traces"], asked["without_span_ids"]
        ),
        _rate_check("error_rate", failed["errors"], failed["error_ids"]),
        _count_check("unfinished", failed["unfinished"], asked["traces"], failed["unfinished_ids"]),
        _rate_check(
            "router_fallback_rate", routed["router"]["fallback"], routed["router"]["fallback_ids"]
        ),
    ]
    for tool in failed["tools"]:
        found.append({**_rate_check("tool_error_rate", tool["errors"]), "subject": tool["tool"]})
    if not failed["tools"]:
        found.append(_rate_check("tool_error_rate", rate(0, 0)))

    level = LEVEL_BY_KEY["answer_p90_seconds"]
    times = [record.duration_ms / 1000 for record in answers if record.duration_ms is not None]
    slow = [
        record
        for record in answers
        if record.duration_ms is not None and record.duration_ms / 1000 > level.level
    ]
    if not times:
        status = STATUS_NO_DATA
    elif len(times) < MIN_FOR_P90:
        # Too few answers for a ninetieth percentile, so any slow one is reported as seen.
        status = STATUS_FEW if slow else STATUS_OK
    else:
        status = STATUS_LOOK if percentile(times, 0.9) > level.level else STATUS_OK
    found.append(
        {
            "key": level.key,
            "status": status,
            "kind": level.kind,
            "level": level.level,
            "count": len(slow),
            "of": len(times),
            "p90_seconds": round(percentile(times, 0.9), 2) if len(times) >= MIN_FOR_P90 else None,
            "ids": _ids(slow),
        }
    )

    found.append(_rate_check("unhelpful_rate", _inverse(rated["helpful"]), rated["unhelpful_ids"]))
    empty = [record for record in read if _flagged(record, "empty_answer")]
    found.append(_count_check("empty_answer", len(empty), len(read), _ids(empty)))
    for key, base in (
        ("tool_limit_rate", "tool_limit_reached"),
        ("pii_in_answer_rate", "pii_removed_from_answer"),
        ("unsupported_claim_rate", "unsupported_claim"),
    ):
        measured, ids = flag_share(base)
        found.append(_rate_check(key, measured, ids))
    found.append(
        _rate_check("token_counts_missing_rate", summary["model_work"]["token_counts_missing"])
    )
    return found


def _inverse(measured: Mapping[str, Any]) -> dict[str, Any]:
    """The share that did not pass, from the share that did."""
    return rate(int(measured["of"]) - int(measured["count"]), int(measured["of"]))


def setup_changes(setup: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The settings that had more than one value among the answers of the window."""
    return [dict(item) for item in setup if len(item["values"]) > 1]


def summarise(
    records: Sequence[TraceRecord], *, source: str = SOURCE_WEB, limit: int | None = None
) -> dict[str, Any]:
    """Every number in the report, as plain data.

    ``records`` are all the traces of the window. Volume counts every one of
    them. Everything else is about the requests of ``source`` alone, and with
    ``limit`` about the newest that many of them.
    """
    chosen = select(records, source, limit)
    read = [record for record in chosen if record.is_answer and record.answer is not None]
    summary: dict[str, Any] = {
        "source": source,
        "volume": volume(records),
        "requests": requests(chosen),
        "routing": routing(read),
        "latency": latency(chosen),
        "model_work": model_work(read),
        "failures": failures(chosen),
        "feedback": feedback(chosen),
        "by_day": by_day(chosen),
    }
    summary["checks"] = checks(summary, chosen)
    summary["setup_changes"] = setup_changes(summary["requests"]["setup"])
    summary["levels"] = [
        {"key": level.key, "level": level.level, "kind": level.kind, "what": level.what}
        for level in LEVELS
    ]
    summary["minimums"] = {
        "rate": MIN_FOR_RATE,
        "p90": MIN_FOR_P90,
        "p99": MIN_FOR_P99,
    }
    return summary


# --- the page ------------------------------------------------------------------------------------


def _rate_text(measured: Mapping[str, Any]) -> str:
    """``12%, 3/25 (5-30%)``, or the count and its interval alone when rows are few.

    The part in brackets is the 95% Wilson interval, as ``eval.stats`` prints it.
    """
    count, of = int(measured["count"]), int(measured["of"])
    if not of:
        return "none to count"
    counted = rate_with_interval(count, of)
    if measured["few"]:
        return f"{counted}, too few for a rate"
    return f"{_percent(measured['rate'])}, {counted}"


def _seconds(milliseconds: float | None) -> str:
    return "n/a" if milliseconds is None else f"{milliseconds / 1000:.2f}"


def _number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def _days(value: Mapping[str, Any]) -> str:
    """The days a setting was seen on: one day, or the first and the last."""
    first, last = value["first_day"], value["last_day"]
    return str(first) if first == last else f"{first} to {last}"


def _id_list(ids: Sequence[str], count: int) -> str:
    shown = ", ".join(f"`{trace_id}`" for trace_id in ids)
    more = f" and {count - len(ids)} more" if count > len(ids) else ""
    return shown + more


def _table(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return [*lines, ""]


def _spread_cells(values: Mapping[str, Any], convert: Any = _seconds) -> list[str]:
    return [
        str(values["n"]),
        convert(values["p50"]),
        convert(values["p90"]),
        convert(values["p99"]),
        convert(values["max"]),
    ]


def _check_line(check: Mapping[str, Any]) -> str:
    """One finding in words: what was seen, against which level, and which requests to open."""
    level = LEVEL_BY_KEY[check["key"]]
    subject = f" (`{check['subject']}`)" if check.get("subject") else ""
    count, of = check["count"], check["of"]
    if level.kind == "seconds":
        if check.get("p90_seconds") is not None:
            seen = f"nine answers in ten finished within {check['p90_seconds']:.2f} s"
        else:
            seen = f"{count} of {of} answers took longer than {level.level:g} s"
        held = f"level: {level.level:g} s"
    elif level.kind == "count":
        seen = f"{count} of {of}"
        held = f"level: more than {level.level:g}"
    else:
        seen = f"{count} of {of}"
        if check["status"] == STATUS_LOOK:
            seen += f" ({_percent(count / of)})"
        held = f"level: above {_percent(level.level)}"
    few = (
        f" Too few rows to call it a rate (fewer than {MIN_FOR_RATE})."
        if check["status"] == STATUS_FEW
        else ""
    )
    ids = f" Open: {_id_list(check['ids'], count)}." if check.get("ids") else ""
    return f"- **{level.what}{subject}**: {seen}; {held}.{few} {level.why}{ids}"


def _what_to_look_at(summary: Mapping[str, Any]) -> list[str]:
    found = summary["checks"]
    look = [check for check in found if check["status"] == STATUS_LOOK]
    few = [check for check in found if check["status"] == STATUS_FEW]
    # A level that is checked once for each tool is listed once, under its worst result.
    raised = {check["key"] for check in [*look, *few]}
    fine = sorted({check["key"] for check in found if check["status"] == STATUS_OK} - raised)
    blank = sorted(
        {check["key"] for check in found if check["status"] == STATUS_NO_DATA} - raised - set(fine)
    )
    asked = summary["requests"]
    lines = [
        "## What to look at",
        "",
        "Each line holds one figure to a fixed level. The levels are a first proposal, "
        "written down in `eval/monitoring.py` (`LEVELS`). Nobody has tuned them against real "
        "incidents, so read a line as a prompt to open the traces, not as an alarm.",
        "",
    ]
    if asked["answers_with_spans"] < MIN_FOR_RATE:
        lines += [
            f"**Only {asked['answers_with_spans']} answers could be read in full** "
            f"({asked['answers']} answers in the window). That is fewer than the "
            f"{MIN_FOR_RATE} a rate needs, so shares are given as counts with their 95% "
            "interval, and nothing here says with any confidence that the copilot is "
            "healthy or that it is not.",
            "",
        ]
    if look:
        lines += ["Over its level:", "", *[_check_line(check) for check in look], ""]
    if few:
        lines += [
            "Seen, on too few rows to judge:",
            "",
            *[_check_line(check) for check in few],
            "",
        ]
    if not look and not few:
        lines += ["Nothing is over its level.", ""]
    if summary["setup_changes"]:
        lines += [
            "Changed inside the window, so figures from before and after are not one population:",
            "",
        ]
        for item in summary["setup_changes"]:
            values = "; ".join(
                f"`{value['value']}` on {value['answers']} answers ({_days(value)})"
                for value in item["values"]
            )
            lines.append(f"- `{item['tag']}`: {values}.")
        lines.append("")
    if fine:
        lines += ["Inside its level: " + ", ".join(f"`{key}`" for key in fine) + ".", ""]
    if blank:
        lines += ["Nothing to measure it on: " + ", ".join(f"`{key}`" for key in blank) + ".", ""]
    return lines


def _volume_section(summary: Mapping[str, Any]) -> list[str]:
    counted = summary["volume"]
    sources = counted["sources"]
    lines = [
        "## Volume",
        "",
        f"Every trace in the window, whatever wrote it: {counted['traces']}. Days are UTC.",
        "",
    ]
    if counted["traces"]:
        lines += _table(
            ["day", *[f"`{name}`" for name in sources], "all"],
            [
                [row["day"], *[row["by_source"].get(name, 0) for name in sources], row["total"]]
                for row in counted["by_day"]
            ]
            + [["all", *[counted["by_source"][name] for name in sources], counted["traces"]]],
        )
    lines += [
        "How the sources are told apart:",
        "",
        "- `web` is real use: the API tags every request `source=web`. Any other name in "
        "this table is a `source` tag some other caller set.",
        "- `evaluation` has an `eval_id` tag, which `eval.run_eval` sets on each row, or is "
        "linked to an MLflow run, which MLflow records when a trace is written inside one.",
        "- `untagged` is everything else: a script, a notebook, a check run by hand. These "
        "cannot be told apart from each other.",
        "- Recording runs (`eval.record_demo`), `eval.routing_eval --router agent` and "
        "`eval.claim_check_eval --collect` turn tracing off, so they leave no trace and are "
        "not in this table. If a recording run were traced it would go through the API and "
        "be tagged `web`, with nothing to tell it from real use.",
        "- A developer's own server and the deployed app both tag `web`. The report splits "
        "them by the path of the program that wrote the trace, which is a guess.",
        "",
    ]
    return lines


def _requests_section(summary: Mapping[str, Any]) -> list[str]:
    asked = summary["requests"]
    source = summary["source"]
    lines = [f"## Requests from `{source}`", ""]
    if not asked["traces"]:
        return [*lines, "None in this window. The sections below have nothing to report.", ""]
    lines += [
        f"{asked['traces']} requests, of which {asked['answers']} were questions to the "
        f"copilot (`{ANSWER_SPAN}`). Spans could be read for "
        f"{asked['traces'] - asked['without_spans']} of the {asked['traces']} requests; "
        f"the route, the flags, the stage times and the model work below rest on the "
        f"{asked['answers_with_spans']} answers among them.",
        "",
    ]
    lines += _table(
        ["request", "view", "count"],
        [[f"`{row['name']}`", row["view"] or "", row["count"]] for row in asked["by_kind"]],
    )
    lines += _table(
        ["written by", "requests", "of them without spans"],
        [
            [name, count, asked["without_spans_by_runtime"].get(name, 0)]
            for name, count in sorted(asked["by_runtime"].items())
        ],
    )
    lines += ["How the copilot was set up, by the tags on the answers:", ""]
    lines += _table(
        ["tag", "value", "answers", "first day", "last day"],
        [
            [
                f"`{item['tag']}`",
                f"`{value['value']}`",
                value["answers"],
                value["first_day"],
                value["last_day"],
            ]
            for item in asked["setup"]
            for value in item["values"]
        ],
    )
    lines += ["Day by day:", ""]
    lines += _table(
        [
            "day",
            "requests",
            "answers",
            "handed off",
            "refused",
            "router fallback",
            "errors",
            "median answer (s)",
            "rated",
            "not helpful",
        ],
        [
            [
                row["day"],
                row["requests"],
                row["answers"],
                row["handed_off"],
                row["refused"],
                row["router_fallback"],
                row["errors"],
                _seconds(row["answer_p50_ms"]),
                row["rated"],
                row["unhelpful"],
            ]
            for row in summary["by_day"]
        ],
    )
    return lines


def _routing_section(summary: Mapping[str, Any]) -> list[str]:
    routed = summary["routing"]
    router = routed["router"]
    lines = ["## Where requests went", ""]
    if not routed["answers"]:
        return [*lines, "No answer whose spans could be read.", ""]
    lines += [f"Of the {routed['answers']} answers whose spans could be read:", ""]
    lines += _table(
        ["outcome", "answers"],
        [
            ["answered", _rate_text(routed["outcomes"]["answered"])],
            ["handed off to a person", _rate_text(routed["outcomes"]["handed_off"])],
            [
                "refused (an attempt to override the instructions)",
                _rate_text(routed["outcomes"]["refused"]),
            ],
        ],
    )
    settings = ", ".join(
        f"`{name}` on {count}" for name, count in sorted(router["setting"].items())
    )
    notes = ", ".join(f"{name} {count}" for name, count in sorted(router["span_notes"].items()))
    lines += [
        f"- Hand-offs decided before the model that answers was called (the rules or the "
        f"router): {routed['handed_off_by']['input_check']}. Decided by that model through "
        f"its tool: {routed['handed_off_by']['answering_model']}. Answers that carry a "
        f"drafted hand-off: {routed['handoff_drafted']}.",
        f"- Router setting, from the `router` tag: {settings}.",
        f"- The router was asked on {router['asked']} answers and not on "
        f"{router['not_asked']} (the rules handed those off first, or the router is off).",
        f"- Rules fallback (`{FLAG_ROUTER_FALLBACK}`), of the answers where the router was "
        f"asked: {_rate_text(router['fallback'])}."
        + (f" What the router's span recorded: {notes}." if notes else ""),
    ]
    if router["fallback_ids"]:
        lines.append(
            f"- Fallback traces: {_id_list(router['fallback_ids'], router['fallback']['count'])}."
        )
    lines += ["", "Guardrail flags, by how many answers carry each:", ""]
    lines += _table(
        ["flag", "answers"],
        [[f"`{row['flag']}`", _rate_text(row)] for row in routed["flags"]]
        + [["(no flag at all)", _rate_text(routed["unflagged"])]],
    )
    return lines


def _latency_section(summary: Mapping[str, Any]) -> list[str]:
    timed = summary["latency"]
    lines = [
        "## Latency",
        "",
        f"Seconds. p90 is shown from {MIN_FOR_P90} values and p99 from {MIN_FOR_P99}; with "
        "fewer, the percentile would be the largest value, which is in the last column. "
        "The whole answer is the trace's own duration, so it is there for a request whose "
        "spans could not be read. It starts after the question is redacted, because "
        "redaction runs before the trace opens.",
        "",
    ]
    rows = [["whole answer", *_spread_cells(timed["answer"])]]
    rows += [
        [f"whole answer, {name.replace('_', ' ')}", *_spread_cells(values)]
        for name, values in timed["answer_by_outcome"].items()
    ]
    rows += [
        [f"`{row['name']}` (not an answer)", *_spread_cells(row)] for row in timed["other_requests"]
    ]
    lines += _table(["request", "n", "p50", "p90", "p99", "max"], rows)
    if timed["stages"]:
        lines += [
            "Each stage, per call. A stage inside another is counted in both, so the rows do "
            "not add up to the whole answer.",
            "",
        ]
        lines += _table(
            ["stage", "kind", "inside", "in answers", "calls", "p50", "p90", "p99", "max"],
            [
                [
                    f"`{row['stage']}`" if not row["stage"].startswith("(") else row["stage"],
                    row["kind"],
                    f"`{row['inside']}`" if row["inside"] else "",
                    row["answers"],
                    *_spread_cells(row),
                ]
                for row in timed["stages"]
            ],
        )
    return lines


def _model_section(summary: Mapping[str, Any]) -> list[str]:
    work = summary["model_work"]
    lines = ["## Model work", ""]
    if not work["answers"]:
        return [*lines, "No answer whose spans could be read.", ""]
    lines += [
        f"- Answers with a recorded count of model calls and tokens: {work['counted']} of "
        f"{work['answers']}. Not recorded at all (written before the copilot counted): "
        f"{work['not_recorded']}. Recorded but incomplete (a model call whose reply carried "
        f"no token count): {work['incomplete']}.",
        f"- Token counts missing or incomplete: {_rate_text(work['token_counts_missing'])}.",
        f"- Counted answers that needed no model call (handed off by the rules): "
        f"{work['no_model_call']}. They are left out of the token rows.",
        f"- Tokens in the window, on the answers with a complete count: "
        f"{work['sum_input_tokens']:,} in, {work['sum_output_tokens']:,} out.",
        "",
    ]
    lines += _table(
        ["per answer", "n", "p50", "p90", "p99", "max"],
        [
            ["model calls (recorded)", *_spread_cells(work["model_calls"], _number)],
            [
                "model-call spans (counted from the trace)",
                *_spread_cells(work["model_call_spans"], _number),
            ],
            ["input tokens", *_spread_cells(work["input_tokens"], _number)],
            ["output tokens", *_spread_cells(work["output_tokens"], _number)],
            ["tokens, in and out", *_spread_cells(work["total_tokens"], _number)],
        ],
    )
    return lines


def _failures_section(summary: Mapping[str, Any]) -> list[str]:
    failed = summary["failures"]
    lines = ["## Failures", ""]
    if not failed["traces"]:
        return [*lines, "No requests.", ""]
    lines += [f"- Requests that ended in the error state: {_rate_text(failed['errors'])}."]
    if failed["error_ids"]:
        lines.append(f"- Open: {_id_list(failed['error_ids'], failed['errors']['count'])}.")
    lines.append(f"- Requests that never finished: {failed['unfinished']}.")
    if failed["unfinished_ids"]:
        lines.append(f"- Open: {_id_list(failed['unfinished_ids'], failed['unfinished'])}.")
    lines.append("")
    if failed["errors_by_origin"]:
        lines += ["Where the failed requests broke:", ""]
        lines += _table(
            ["span", "exception", "requests"],
            [
                [
                    f"`{row['span']}`" if not row["span"].startswith("(") else row["span"],
                    f"`{row['exception']}`"
                    if not row["exception"].startswith("(")
                    else row["exception"],
                    row["count"],
                ]
                for row in failed["errors_by_origin"]
            ],
        )
    if failed["tools"]:
        lines += [
            "Tool calls. A failed call does not fail the request: the model is told and the "
            "answer goes on. `rejected` is a call the tool refused, such as an unknown id; "
            "`unreachable` is a lookup that could not be completed.",
            "",
        ]
        lines += _table(
            ["tool", "in answers", "calls", "failed", "how"],
            [
                [
                    f"`{row['tool']}`" if not row["tool"].startswith("(") else row["tool"],
                    row["answers"],
                    row["calls"],
                    _rate_text(row["errors"]),
                    ", ".join(
                        f"{kind} {count}" for kind, count in sorted(row["errors_by_kind"].items())
                    ),
                ]
                for row in failed["tools"]
            ],
        )
    else:
        lines += ["No tool call on a trace whose spans could be read.", ""]
    return lines


def _feedback_section(summary: Mapping[str, Any]) -> list[str]:
    rated = summary["feedback"]
    lines = ["## Feedback", ""]
    if not rated["answers"]:
        return [*lines, "No answers, so nothing to rate.", ""]
    lines += [
        f"- Answers rated: {_rate_text(rated['rated'])}.",
        f"- Marked helpful, of the rated ones: {_rate_text(rated['helpful'])}.",
        f"- Rated more than once (the latest rating counts): {rated['rated_more_than_once']}.",
        f"- Ratings on requests that are not answers: {rated['ratings_on_other_requests']}.",
    ]
    if rated["unhelpful_ids"]:
        lines.append(
            f"- Marked not helpful: {_id_list(rated['unhelpful_ids'], rated['unhelpful'])}."
        )
    else:
        lines.append("- Marked not helpful: none.")
    lines += [
        "",
        "A rating is read from its trace, so one given inside the window to an answer from "
        "before it is not counted.",
        "",
    ]
    return lines


def _levels_section() -> list[str]:
    lines = [
        "## The levels",
        "",
        'Proposed, not tuned. A share over its level is listed under "What to look at" '
        f"when it rests on at least {MIN_FOR_RATE} rows; on fewer it is listed as seen.",
        "",
    ]
    rows = []
    for level in LEVELS:
        if level.kind == "rate":
            held = f"above {_percent(level.level)}"
        elif level.kind == "seconds":
            held = f"above {level.level:g} s"
        else:
            held = f"more than {level.level:g}"
        rows.append([f"`{level.key}`", level.what, held])
    return [*lines, *_table(["key", "what is measured", "level"], rows)]


def render_markdown(report: Mapping[str, Any]) -> str:
    """The report as a page. It prints only what ``summarise`` returned and the provenance."""
    about = report["provenance"]
    window = about["window"]
    tree = "uncommitted changes" if about["git_dirty"] else "clean tree"
    lines = [
        "# Copilot monitoring report",
        "",
        f"Window: {window['since']} to {window['until']} (UTC, {window['days']:g} days). "
        f"Requests shown: `{report['source']}`. Experiment `{about['experiment']['name']}` "
        f"(id {about['experiment']['id']}). Written {about['generated_at']} by "
        f"`python -m eval.monitoring_report` at commit `{about['git_sha'][:7]}` ({tree}), "
        f"MLflow {about['mlflow_version']}.",
        "",
        "This page holds counts, names, durations, flags and trace ids. It holds no "
        "question, no answer and no tool argument: open a trace by its id to read those.",
        "",
    ]
    if about.get("limit"):
        lines += [
            f"**A quick look, not the report.** Only the newest {about['limit']} "
            f"`{report['source']}` requests of the window were read (`--limit`).",
            "",
        ]
    lines += _what_to_look_at(report)
    lines += _volume_section(report)
    lines += _requests_section(report)
    if report["requests"]["traces"]:
        lines += _routing_section(report)
        lines += _latency_section(report)
        lines += _model_section(report)
        lines += _failures_section(report)
        lines += _feedback_section(report)
    lines += _levels_section()
    return "\n".join(lines).rstrip("\n") + "\n"
