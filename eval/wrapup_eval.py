"""Measure the after-call wrap-up against the transcript generator's own labels.

Usage:
    python -m eval.wrapup_eval --limit 5       a trial: five calls, nothing saved
    python -m eval.wrapup_eval --save          every call, and a result file
    python -m eval.wrapup_eval --save --resume carry on a run that stopped part way

The copilot drafts a wrap-up for each redacted call from the conversation alone
(``Tools.wrap_up_call``). Its prompt is never given the call's recorded
category or outcome, so two of the things it writes can be checked at no
labelling cost: the disposition against the generator's ``resolution``, and
the category against the generator's ``category``. Notes, promises and the
follow-up are saved with each prediction and are not scored: nothing here says
whether they are right.

How far the numbers reach. The calls are synthetic. Each one is a filled-in copy
of one of about two dozen scripts (``data_gen/transcript_templates.py``), so 200
calls are far fewer than 200 independent tests: if the model misreads one
script, it misreads every call made from it. The intervals printed here treat
the calls as independent and are therefore too narrow. The result lists each
pair of category and ending with its own counts, so that a reader can see
whether the mistakes sit in one script. The endings are also the generator's
own judgement: a call it labels "unresolved" may read as "resolved" to a
careful person, and a disagreement is counted as a mistake either way.

Each call costs one small SQL lookup and one model call. A reply the workspace
refuses for its rate limit is tried again, with a longer wait each time. With
``--save`` every prediction is written to a progress file as it is made, so a
run that stops can be resumed and nothing already paid for is lost. ``--save``
refuses to start from a working tree with uncommitted changes, so the result
names the code that made it.

A saved result of prompt version ``w1`` is a first-contact result: that prompt
was written before any call was scored. If the prompt is changed after looking
at the mistakes, bump ``WRAP_UP_PROMPT_VERSION``; the calls are then in-sample
for the new version, the result says so, and the earlier result file is kept.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar, get_args

from copilot.prompts import WRAP_UP_PROMPT_VERSION
from copilot.schemas import CallCategory, Disposition
from copilot.tools import ToolError
from eval.redaction_eval import _git
from eval.stats import wilson_interval

RESULTS_DIR = Path("eval/results")
DISPOSITIONS: tuple[str, ...] = get_args(Disposition)
CATEGORIES: tuple[str, ...] = get_args(CallCategory)
# The column of a confusion matrix for a call with no usable draft.
NO_ANSWER = "no_answer"
# The one prompt version that was written before any call was scored.
FIRST_CONTACT_VERSION = "w1"
# The last of the 200 ordinary calls (``synth_transcripts --seed 42``). The calls with
# a seeded rule breach, T0201 on, are in the same table and are not measured here.
LAST_MEASURED_CALL = "T0200"

T = TypeVar("T")


def measured_calls(calls: Iterable[Mapping[str, str]]) -> list[Mapping[str, str]]:
    """The calls this measurement is about: the 200 ordinary ones.

    The saved results were made when the table held only those. The breach
    calls were added to it later for the compliance review, and scoring them
    too would change what the published figures mean without saying so.
    """
    return [call for call in calls if call["transcript_id"] <= LAST_MEASURED_CALL]


# --- scoring ----------------------------------------------------------------------------------


def _rate(count: int, of: int) -> dict[str, Any]:
    if of == 0:
        return {"count": 0, "of": 0, "rate": None, "ci95": None}
    return {"count": count, "of": of, "rate": count / of, "ci95": list(wilson_interval(count, of))}


def score_label(pairs: Sequence[tuple[str, str | None]], labels: Sequence[str]) -> dict[str, Any]:
    """Accuracy, each class's recall and precision, and the confusion matrix.

    Args:
        pairs: For each call, the true label and the predicted one. None is a call
            with no usable draft; it is counted as wrong and has its own column.
        labels: Every label a call can have, in the order to report them.
    """
    said = [(truth, guess if guess is not None else NO_ANSWER) for truth, guess in pairs]
    matrix = Counter(said)
    columns = [*labels, NO_ANSWER]
    by_class: dict[str, Any] = {}
    for label in labels:
        truly = sum(truth == label for truth, _ in said)
        guessed = sum(guess == label for _, guess in said)
        right = matrix[(label, label)]
        by_class[label] = {"recall": _rate(right, truly), "precision": _rate(right, guessed)}
    return {
        "accuracy": _rate(sum(truth == guess for truth, guess in said), len(said)),
        "by_class": by_class,
        # Rows are the true label, columns the predicted one.
        "confusion": {
            truth: {guess: matrix[(truth, guess)] for guess in columns} for truth in labels
        },
    }


def score(predictions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Score every prediction on both labels, together and for each kind of call."""
    dispositions = [(p["truth"]["disposition"], _said(p, "disposition")) for p in predictions]
    categories = [(p["truth"]["category"], _said(p, "category")) for p in predictions]
    both = sum(
        truth_d == said_d and truth_c == said_c
        for (truth_d, said_d), (truth_c, said_c) in zip(dispositions, categories, strict=True)
    )
    kinds = sorted({(p["truth"]["category"], p["truth"]["disposition"]) for p in predictions})
    by_kind = []
    for category, disposition in kinds:
        rows = [
            p
            for p in predictions
            if (p["truth"]["category"], p["truth"]["disposition"]) == (category, disposition)
        ]
        by_kind.append(
            {
                "category": category,
                "disposition": disposition,
                "calls": len(rows),
                "disposition_right": sum(_said(p, "disposition") == disposition for p in rows),
                "category_right": sum(_said(p, "category") == category for p in rows),
            }
        )
    return {
        "calls": len(predictions),
        "no_answer": sum(p["predicted"] is None for p in predictions),
        "disposition": score_label(dispositions, DISPOSITIONS),
        "category": score_label(categories, CATEGORIES),
        "both_right": _rate(both, len(predictions)),
        # One line for each pair of category and ending the generator can produce.
        "by_kind_of_call": by_kind,
        "wrong": [
            {
                "transcript_id": p["transcript_id"],
                "truth": p["truth"],
                "said": {
                    "disposition": _said(p, "disposition"),
                    "category": _said(p, "category"),
                },
            }
            for p in predictions
            if _said(p, "disposition") != p["truth"]["disposition"]
            or _said(p, "category") != p["truth"]["category"]
        ],
    }


def _said(prediction: Mapping[str, Any], label: str) -> str | None:
    predicted = prediction["predicted"]
    return None if predicted is None else str(predicted[label])


# --- printing ---------------------------------------------------------------------------------


def _line(label: str, rate: Mapping[str, Any]) -> str:
    if rate["rate"] is None:
        return f"{label}: none"
    low, high = rate["ci95"]
    return f"{label}: {rate['count']}/{rate['of']} ({rate['rate']:.0%}, {low:.0%}-{high:.0%})"


def _matrix_lines(confusion: Mapping[str, Mapping[str, int]]) -> list[str]:
    truths = list(confusion)
    columns = list(next(iter(confusion.values()))) if confusion else []
    # A column nobody was ever placed in is left out, so ten categories stay readable.
    columns = [name for name in columns if any(confusion[truth][name] for truth in truths)]
    width = max((len(name) for name in [*truths, *columns]), default=0) + 2
    lines = [" " * width + "".join(name.rjust(width) for name in columns)]
    lines += [
        truth.ljust(width) + "".join(str(confusion[truth][name]).rjust(width) for name in columns)
        for truth in truths
        if any(confusion[truth].values())
    ]
    return lines


def print_scores(scores: Mapping[str, Any]) -> None:
    """Print the scores for a person to read. Counts and labels only, never transcript text."""
    print(f"\ncalls scored: {scores['calls']}")
    if scores["no_answer"]:
        print(f"calls with no usable draft (counted as wrong): {scores['no_answer']}")
    for name in ("disposition", "category"):
        result = scores[name]
        print("\n" + _line(f"{name} right", result["accuracy"]))
        for label, both in result["by_class"].items():
            if both["recall"]["of"] == 0 and both["precision"]["of"] == 0:
                # No call had this label and none was given it: there is nothing to say.
                continue
            print(
                f"  {label}: "
                + _line("recall", both["recall"])
                + "; "
                + _line("precision", both["precision"])
            )
        print("  rows are the generator's label, columns what the copilot said:")
        for line in _matrix_lines(result["confusion"]):
            print("    " + line)
    print("\n" + _line("both right on the same call", scores["both_right"]))
    print("\nby kind of call (the generator's category and ending):")
    for kind in scores["by_kind_of_call"]:
        print(
            f"  {kind['category']} / {kind['disposition']}: {kind['calls']} calls, "
            f"disposition right {kind['disposition_right']}, "
            f"category right {kind['category_right']}"
        )
    print(
        "\nThe intervals treat the calls as independent. They are copies of about two dozen "
        "scripts, so the true ranges are wider."
    )


# --- asking the copilot -----------------------------------------------------------------------


def is_rate_limit(error: BaseException) -> bool:
    """Whether a failure is the workspace saying "too many requests" (HTTP 429)."""
    response = getattr(error, "response", None)
    if 429 in (getattr(error, "status_code", None), getattr(response, "status_code", None)):
        return True
    text = f"{type(error).__name__} {error}".lower().replace(" ", "").replace("_", "")
    return any(
        sign in text
        for sign in ("429", "ratelimit", "toomanyrequests", "requestlimitexceeded", "quotaexceeded")
    )


def with_retries(
    call: Callable[[], T],
    *,
    attempts: int = 8,
    first_wait: float = 5.0,
    longest_wait: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """Run ``call``, trying again after a rate limit. Returns its result and the tries it took.

    Only a rate limit is retried: the wait doubles each time, up to
    ``longest_wait``. Any other failure, and the last rate limit, is raised.
    """
    wait = first_wait
    for attempt in range(1, attempts + 1):
        try:
            return call(), attempt
        except Exception as error:
            if attempt == attempts or not is_rate_limit(error):
                raise
            sleep(wait)
            wait = min(wait * 2, longest_wait)
    msg = "attempts must be at least 1"
    raise ValueError(msg)


def predict(
    calls: Iterable[Mapping[str, str]],
    draft: Callable[[str], Any],
    *,
    done: Mapping[str, Mapping[str, Any]] | None = None,
    on_prediction: Callable[[Mapping[str, Any]], None] | None = None,
    pause: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Draft a wrap-up for each call and pair it with the generator's labels.

    Args:
        calls: Each call's ``transcript_id``, ``category`` and ``resolution``.
        draft: Drafts the wrap-up of one call from its id, as ``Tools.wrap_up_call`` does.
        done: Predictions from an earlier part of the same run, by call id. Those
            calls are not asked again.
        on_prediction: Called with each new prediction as soon as it is made.
        pause: Seconds to wait between calls, to stay under a shared rate limit.
        sleep: Stands in for ``time.sleep`` in tests.

    A call the model gives no usable draft for is kept, with ``predicted`` None
    and the reason. A failure that is not about one call's reply, such as the
    workspace being unreachable, stops the run.
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
        prediction: dict[str, Any] = {
            "transcript_id": call_id,
            "truth": {"disposition": call["resolution"], "category": call["category"]},
            "predicted": None,
            "problem": None,
            "tries": 1,
        }
        try:
            wrap_up, tries = with_retries(lambda call_id=call_id: draft(call_id), sleep=sleep)
            # The whole draft is kept. It was written from redacted text and has passed
            # the output check, so it holds nothing the redacted table does not.
            prediction["predicted"] = wrap_up.model_dump(
                exclude={"transcript_id", "related_articles"}
            )
            prediction["tries"] = tries
        except ToolError as error:
            # The model's reply could not be used. A tool's message is safe to keep.
            prediction["problem"] = str(error)
        prediction["seconds"] = round(time.perf_counter() - started, 2)
        predictions.append(prediction)
        if on_prediction is not None:
            on_prediction(prediction)
    return predictions


# --- a run that can be carried on -------------------------------------------------------------


def read_progress(path: Path, run: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The predictions an unfinished run left behind, if it was this same run.

    The first line of a progress file says what made it: the commit, the prompt
    version and the model. Predictions are carried over only when all three are
    the same now, because otherwise they describe a different system.

    Raises:
        SystemExit: If the file was left by a different run.
    """
    if not path.exists():
        return {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {}
    if json.loads(lines[0]) != dict(run):
        print(
            f"not started: {path.as_posix()} was left by a different commit, prompt or model. "
            "Delete it to start again."
        )
        raise SystemExit(1)
    done: dict[str, dict[str, Any]] = {}
    for line in lines[1:]:
        try:
            prediction = json.loads(line)
        except json.JSONDecodeError:
            # A run that was cut off can leave half a line at the end. That call is asked again.
            continue
        done[prediction["transcript_id"]] = prediction
    return done


def _append(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value) + "\n")


# --- the command ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Score the wrap-up on the redacted calls."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--limit", type=int, default=None, help="score this many, save nothing")
    parser.add_argument("--save", action="store_true", help="write a result file")
    parser.add_argument("--resume", action="store_true", help="carry on an unfinished --save run")
    parser.add_argument(
        "--pause", type=float, default=2.0, help="seconds between calls (default 2)"
    )
    parser.add_argument(
        "--show-drafts",
        action="store_true",
        help="print each draft in full; they are written from redacted synthetic calls",
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

    from copilot.config import load_settings
    from copilot.tools import Tools
    from copilot.transcripts import list_transcripts

    load_dotenv()
    settings = load_settings()
    # These drafts are measurements, not an agent's work: they are not traced.
    mlflow.tracing.disable()
    tools = Tools(settings)
    name = settings.llm_endpoint.removeprefix("databricks-")
    run = {
        "git_sha": _git("rev-parse", "HEAD"),
        "wrap_up_prompt_version": WRAP_UP_PROMPT_VERSION,
        "llm_endpoint": settings.llm_endpoint,
    }

    listed, _ = with_retries(lambda: list_transcripts(tools.sql, settings))
    calls = measured_calls(listed)
    chosen = calls[: args.limit] if args.limit else calls
    progress = RESULTS_DIR / f"wrapup_{name}.progress.jsonl"
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
        said = prediction["predicted"]
        problem = f"no draft: {prediction['problem']}"
        outcome = f"{said['disposition']}, {said['category']}" if said else problem
        truth = prediction["truth"]
        print(
            f"  {prediction['transcript_id']} {prediction['seconds']:.1f}s  "
            f"labels: {truth['disposition']}, {truth['category']}  said: {outcome}",
            flush=True,
        )
        if args.show_drafts and said:
            print(json.dumps(said, indent=2), flush=True)

    predictions = predict(
        chosen,
        lambda call_id: tools.wrap_up_call(call_id, with_articles=False),
        done=done,
        on_prediction=report,
        pause=args.pause,
    )
    scores = score(predictions)
    print_scores(scores)
    if not args.save:
        print("\nnothing saved" + (" (--limit)" if args.limit else ""))
        return
    result = {
        "scored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **run,
        "llm_temperature": settings.llm_temperature,
        "truth": "the transcript generator's own labels: resolution and category",
        "first_contact": WRAP_UP_PROMPT_VERSION == FIRST_CONTACT_VERSION,
        "calls_are_independent": False,
        **scores,
        "predictions": predictions,
    }
    path = RESULTS_DIR / f"wrapup_{result['scored_at'][:10]}_{name}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    progress.unlink()
    print(f"saved {path.as_posix()}")


if __name__ == "__main__":
    main()
