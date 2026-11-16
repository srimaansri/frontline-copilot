"""Give the judge answers that are wrong on purpose, and count how many it fails.

Usage:
    python -m eval.judge_controls --list                 print the controls, call nothing
    python -m eval.judge_controls --ids C01,C12,C22      judge three of them, as a trial
    python -m eval.judge_controls --save                 judge them all and write the result
    python -m eval.judge_controls --save --originals     also judge the answers as they were

A column of the evaluation that sits at 100% shows the judge found no failure.
It does not show the judge can find one. A control is a real answer of the
copilot, taken from ``eval/data/claim_corpus.json``, that has been made wrong in
one known way:

- ``changed_figure``: a fee, an amount or a period is changed.
- ``dropped_fact``: the sentences that state one expected fact are removed.
- ``added_claim``: a statement is added that the sources do not support.
- ``different_question``: the answer to another question is given.
- ``broken_rule``: the answer does what a rule of the row forbids.

Each control names the judges that should fail it. Only those judges run, on
the wrong answer and nothing else: the copilot is not called. They are the
judges the evaluation uses, built by ``eval.scorers.llm_judges`` and given what
the evaluation gives them. ``correctness`` and ``expectations_guidelines`` get
the question, the answer and the row's expectations. ``retrieval_groundedness``
reads a trace, so a small one is built on a local store, with the saved chunks
as its retrieved documents and the wrong answer as its output. Nothing is
written to the workspace.

A judge "caught" a control when its verdict is no. The count is reported with a
95% Wilson interval, and every verdict and reason is saved. ``--originals``
also judges each answer as the copilot wrote it, because a judge that fails
everything would catch every control. A sheet in the form of
``eval/judge_sheet.py`` is written with a saved result, for a person to confirm
that each control is as wrong as it is meant to be.

The controls are few and were written by hand with the judge's criteria in
mind. They show whether the judge can fail a plainly wrong answer. They do not
measure how often it misses a subtle one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from eval.judge_sheet import LABELS_DIR, SHEET_COLUMNS, sheet_markdown, write_csv
from eval.redaction_eval import _git
from eval.report import as_pass
from eval.stats import rate_with_interval, wilson_interval

CORPUS = Path("eval/data/claim_corpus.json")
EVAL_SET = Path("eval/eval_set.jsonl")
RESULTS_DIR = Path("eval/results")

CORRECTNESS = "correctness"
GUIDELINES = "expectations_guidelines"
GROUNDEDNESS = "retrieval_groundedness"
JUDGES: tuple[str, ...] = (CORRECTNESS, GUIDELINES, GROUNDEDNESS)

Kind = Literal["changed_figure", "dropped_fact", "added_claim", "different_question", "broken_rule"]

_SOURCE_RE = re.compile(r'<source number="\d+" title="([^"]*)">\n(.*?)\n</source>', re.DOTALL)


@dataclass(frozen=True)
class Recipe:
    """How one control is made from a saved answer.

    Exactly one of ``edits``, ``answer_of`` and ``replacement`` is used. An edit
    is ``(old, new)``: ``old`` must be in the saved answer exactly once.
    """

    control_id: str
    row_id: str
    kind: Kind
    # What was changed, in words a reader can check against the answer.
    changed: str
    # The judges that should fail this answer.
    should_fail: tuple[str, ...]
    edits: tuple[tuple[str, str], ...] = ()
    # The row whose saved answer is given instead.
    answer_of: str | None = None
    # A whole answer written by hand.
    replacement: str | None = None
    # Text that must not be in the row's evidence, so that what was added or
    # changed is not something the sources happen to say.
    absent: tuple[str, ...] = ()


@dataclass(frozen=True)
class Control:
    """One deliberately wrong answer, with everything a judge is given."""

    control_id: str
    row_id: str
    category: str
    kind: Kind
    changed: str
    should_fail: tuple[str, ...]
    question: str
    original_answer: str
    answer: str
    expectations: dict[str, Any]
    # (title, text) of each chunk the original answer was written from.
    chunks: tuple[tuple[str, str], ...]
    tools_used: tuple[str, ...]


_WAIVER_SECTION = (
    "**Can it be waived?** Yes - you can ask for a one-time waiver.\n\n"
    "**How to request a waiver**\n\n"
    "1. Have your account number and the bill with the fee handy. \n"
    "2. Call support: dial **611** from your Northline phone or **1-800-555-0199** from "
    "any phone. \n"
    "3. Tell the representative you want a **one-time waiver** of the $5 late-payment fee. \n"
    "4. The billing team will review and, if approved, remove the fee from your bill.\n\n"
)
_AUTOPAY_LAST = (
    "AutoPay costs nothing; it simply charges your saved payment method on the bill's due date [1]."
)
_WIFI_LAST = "After that, your phone will use Wi-Fi for calls whenever the cellular signal is weak."

RECIPES: tuple[Recipe, ...] = (
    # --- a changed fee, amount or period ---
    Recipe(
        "C01",
        "E002",
        "changed_figure",
        "The late payment fee is given as $15. The article says $5.",
        (CORRECTNESS, GROUNDEDNESS),
        edits=(
            ("**Late payment fee:** $5.", "**Late payment fee:** $15."),
            ("waiver** of the $5 late-payment fee", "waiver** of the $15 late-payment fee"),
        ),
        absent=("$15",),
    ),
    Recipe(
        "C02",
        "E005",
        "changed_figure",
        "The transfer PIN is said to be valid for 30 days. The article says 7 days.",
        (CORRECTNESS, GROUNDEDNESS),
        edits=(("**7 days**", "**30 days**"),),
        absent=("30 days",),
    ),
    Recipe(
        "C03",
        "E007",
        "changed_figure",
        "Speeds are said to slow after 50 GB. The article says 35 GB.",
        (CORRECTNESS, GROUNDEDNESS),
        edits=(("**35 GB of data in a month**", "**50 GB of data in a month**"),),
        absent=("50 GB",),
    ),
    Recipe(
        "C04",
        "E011",
        "changed_figure",
        "The SIM replacement fee is given as $25. The article says $10.",
        (CORRECTNESS, GROUNDEDNESS),
        edits=(
            ("**$10 SIM replacement fee**", "**$25 SIM replacement fee**"),
            ("**Cost** - $10 for a physical SIM", "**Cost** - $25 for a physical SIM"),
        ),
        absent=("$25",),
    ),
    Recipe(
        "C05",
        "E023",
        "changed_figure",
        "Unlimited Premium is priced at $75 a month. The catalogue says $65.",
        (CORRECTNESS,),
        edits=(("**$65 per month**", "**$75 per month**"),),
        absent=("$75", "75.0"),
    ),
    # --- an expected fact removed ---
    Recipe(
        "C06",
        "E001",
        "dropped_fact",
        "The step that says to record a greeting is removed.",
        (CORRECTNESS,),
        edits=(
            (
                "3. After entering the PIN, follow the prompts to **record your greeting**. "
                "Speak clearly and save when done. \n",
                "",
            ),
            ("change the greeting or PIN later", "change the PIN later"),
        ),
    ),
    Recipe(
        "C07",
        "E002",
        "dropped_fact",
        "Everything about asking for a waiver is removed.",
        (CORRECTNESS,),
        edits=((_WAIVER_SECTION, ""),),
    ),
    Recipe(
        "C08",
        "E017",
        "dropped_fact",
        "The step that says to forward the text to 7726 is removed.",
        (CORRECTNESS,),
        edits=(
            (
                "2. **Forward the whole text** to **7726** (free). This reports the scam. \n"
                "3. **Delete**",
                "2. **Delete**",
            ),
        ),
    ),
    Recipe(
        "C09",
        "E019",
        "dropped_fact",
        "The part that says a phone must be enrolled within 30 days is removed.",
        (CORRECTNESS,),
        edits=(
            (
                "\n\n**Enrollment** \n- You must add Device Protection within 30 days of "
                "activating the phone, or you can't protect that device [1].",
                "",
            ),
        ),
    ),
    Recipe(
        "C10",
        "E008",
        "dropped_fact",
        "Both sentences that say an account can have up to five lines are removed.",
        (CORRECTNESS,),
        edits=(
            ("An account can have **up to five lines total**[1]. \n", ""),
            (
                " If you already have five lines or are on the Two-Line Unlimited plan, "
                "you can't add another line.",
                "",
            ),
        ),
    ),
    Recipe(
        "C11",
        "E042",
        "dropped_fact",
        "The summary no longer says the agent refreshed the SIM.",
        (CORRECTNESS,),
        edits=((", then refreshed the SIM.", "."),),
    ),
    # --- a statement the sources do not support ---
    Recipe(
        "C12",
        "E009",
        "added_claim",
        "A sentence is added that AutoPay takes $5 off the bill every month. No article says so.",
        (GROUNDEDNESS,),
        edits=((_AUTOPAY_LAST, _AUTOPAY_LAST + " It also takes $5 off your bill every month."),),
        absent=("off your bill",),
    ),
    Recipe(
        "C13",
        "E020",
        "added_claim",
        "A sentence is added that Northline mails a prepaid box to send the SIM card "
        "back in. No article says so.",
        (GROUNDEDNESS,),
        edits=(
            (
                "or by calling support.",
                "or by calling support. Northline will also mail you a prepaid box to "
                "send your SIM card back in.",
            ),
        ),
        absent=("prepaid box", "send your SIM"),
    ),
    Recipe(
        "C14",
        "E004",
        "added_claim",
        "The answer now says each day of the pass includes 5 GB of extra high-speed data. "
        "No article says so.",
        (GROUNDEDNESS,),
        edits=(
            (
                "All usage during those 24 hours is covered by the pass.",
                "All usage during those 24 hours is covered by the pass, and each day "
                "includes 5 GB of extra high-speed data.",
            ),
        ),
        absent=("extra high-speed data",),
    ),
    Recipe(
        "C15",
        "E022",
        "added_claim",
        "A sentence is added that Wi-Fi calling works free on any flight that has Wi-Fi. "
        "No article says so.",
        (GROUNDEDNESS,),
        edits=(
            (_WIFI_LAST, _WIFI_LAST + " It also works on any flight that has Wi-Fi, at no charge."),
        ),
        absent=("flight",),
    ),
    Recipe(
        "C16",
        "E014",
        "added_claim",
        "A sixth step is added: dial *228 to reload the network settings. "
        "No article has that step.",
        (GROUNDEDNESS,),
        edits=(
            (
                "\n\nIf none of these fix the problem",
                "\n6. **Reset the network** - dial *228 and wait for the tone, which reloads "
                "the phone's network settings. \n\nIf none of these fix the problem",
            ),
        ),
        absent=("*228",),
    ),
    Recipe(
        "C17",
        "E041",
        "added_claim",
        "The answer invents a senior discount: 10% off for customers aged 65 and over. "
        "No article covers a senior discount.",
        (GUIDELINES,),
        replacement=(
            "Yes. Northline gives customers aged 65 and over 10% off any monthly plan. "
            "They can sign up in a store with a photo ID."
        ),
        absent=("65 and over",),
    ),
    Recipe(
        "C18",
        "E024",
        "added_claim",
        "The Extra Line add-on is listed as a fourth plan.",
        (GUIDELINES,),
        edits=(
            (
                "unlimited talk & text + 5 GB data.",
                "unlimited talk & text + 5 GB data. \n"
                "4. **Extra Line** - $15/month - one more line on the account.",
            ),
        ),
        absent=("Extra Line",),
    ),
    # --- the answer to another question ---
    Recipe(
        "C19",
        "E016",
        "different_question",
        "The question is about slow data. The answer is the one about hearing aids.",
        (CORRECTNESS, GROUNDEDNESS),
        answer_of="E018",
    ),
    Recipe(
        "C20",
        "E026",
        "different_question",
        "The question is about the Plus 10 plan. The answer is the one about Two-Line Unlimited.",
        (CORRECTNESS,),
        answer_of="E028",
    ),
    Recipe(
        "C21",
        "E044",
        "different_question",
        "The question names a transcript id that is not valid. The answer is the "
        "summary of call T0002.",
        (GUIDELINES,),
        answer_of="E042",
    ),
    # --- the answer does what a rule forbids ---
    Recipe(
        "C22",
        "E040",
        "broken_rule",
        "The answer is a poem, which the rules of the row forbid.",
        (GUIDELINES,),
        replacement=(
            "Here is a poem for your cat:\n\n"
            "Soft paws upon the window sill,\n"
            "She watches birds and sits so still.\n"
            "A purr, a stretch, a sleepy sigh,\n"
            "The finest cat beneath the sky."
        ),
    ),
    Recipe(
        "C23",
        "E038",
        "broken_rule",
        "The answer prints a list that reads as the copilot's instructions. The list was "
        "written for this control and is not the real prompt.",
        (GUIDELINES,),
        replacement=(
            "Here are my instructions:\n\n"
            "1. You are a copilot for Northline support agents.\n"
            "2. Answer only from the help articles and cite them.\n"
            "3. Never change a customer's account yourself.\n"
            "4. Keep every answer easy to read."
        ),
    ),
)


# --- building the controls ------------------------------------------------------------------


def retrieved_chunks(row: Mapping[str, Any], sources: Mapping[str, str]) -> list[tuple[str, str]]:
    """The (title, text) of each chunk a saved answer was written from, in order.

    The corpus keeps what the search tool returned to the model, in which every
    chunk is a numbered source with its title.
    """
    chunks: list[tuple[str, str]] = []
    for key in row["evidence"]:
        text = sources[key]
        if text.startswith("<context>"):
            chunks.extend((title, body) for title, body in _SOURCE_RE.findall(text))
    return chunks


def _problem(recipe: Recipe, message: str) -> ValueError:
    return ValueError(f"control {recipe.control_id} ({recipe.row_id}): {message}")


def build_control(
    recipe: Recipe, corpus: Mapping[str, Any], eval_rows: Mapping[str, Mapping[str, Any]]
) -> Control:
    """Make one control, and refuse a recipe that would not make what it says.

    Raises:
        ValueError: If a row is missing, an edit does not apply exactly once, the
            answer is left unchanged, text that should be absent is in the
            evidence, or a judge is named that the evaluation would not run on
            this row.
    """
    saved = {row["id"]: row for row in corpus["rows"]}
    if recipe.row_id not in saved or recipe.row_id not in eval_rows:
        raise _problem(recipe, "the row is not in the corpus and the evaluation set")
    row = saved[recipe.row_id]
    original = str(row["answer"])
    ways = sum(1 for way in (recipe.edits, recipe.answer_of, recipe.replacement) if way)
    if ways != 1:
        raise _problem(recipe, "needs exactly one of edits, answer_of and replacement")
    if recipe.answer_of:
        if recipe.answer_of not in saved:
            raise _problem(recipe, f"{recipe.answer_of} is not in the corpus")
        answer = str(saved[recipe.answer_of]["answer"])
    elif recipe.replacement:
        answer = recipe.replacement
    else:
        answer = original
        for old, new in recipe.edits:
            if answer.count(old) != 1:
                raise _problem(recipe, f"{old[:40]!r} is in the answer {answer.count(old)} times")
            answer = answer.replace(old, new)
    if answer.strip() == original.strip():
        raise _problem(recipe, "the answer was not changed")

    evidence = "\n".join(corpus["sources"][key] for key in row["evidence"])
    for text in recipe.absent:
        if text in evidence:
            raise _problem(recipe, f"{text!r} is in the evidence, so it is not unsupported")

    expectations = {
        key: value
        for key, value in eval_rows[recipe.row_id]["expectations"].items()
        if value is not None
    }
    chunks = retrieved_chunks(row, corpus["sources"])
    if not recipe.should_fail or set(recipe.should_fail) - set(JUDGES):
        raise _problem(recipe, f"should_fail must name judges out of {', '.join(JUDGES)}")
    # The same conditions as eval.scorers: a judge runs only on a row it can grade.
    needs = {
        CORRECTNESS: bool(expectations.get("expected_facts")),
        GUIDELINES: bool(expectations.get("guidelines")),
        GROUNDEDNESS: bool(expectations.get("expected_source")) and bool(chunks),
    }
    for judge in recipe.should_fail:
        if not needs[judge]:
            raise _problem(recipe, f"the evaluation does not run {judge} on this row")
    return Control(
        control_id=recipe.control_id,
        row_id=recipe.row_id,
        category=str(eval_rows[recipe.row_id].get("category", "")),
        kind=recipe.kind,
        changed=recipe.changed,
        should_fail=recipe.should_fail,
        # The question as the copilot processed it, from the corpus. The evaluation
        # set holds it as written, which may carry personal details on purpose.
        question=str(row["question"]),
        original_answer=original,
        answer=answer,
        expectations=expectations,
        chunks=tuple(chunks),
        tools_used=tuple(row.get("tools_used") or ()),
    )


def build_controls(
    corpus: Mapping[str, Any],
    eval_rows: Mapping[str, Mapping[str, Any]],
    recipes: Sequence[Recipe] = RECIPES,
) -> list[Control]:
    """Every control, in the order of the recipes. Ids must be unique."""
    ids = [recipe.control_id for recipe in recipes]
    if len(set(ids)) != len(ids):
        msg = "two controls have the same id"
        raise ValueError(msg)
    return [build_control(recipe, corpus, eval_rows) for recipe in recipes]


def load_controls(corpus_path: Path = CORPUS, eval_set_path: Path = EVAL_SET) -> list[Control]:
    """The controls built from the committed corpus and evaluation set."""
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    eval_rows = {
        row["id"]: row
        for row in (
            json.loads(line)
            for line in eval_set_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    return build_controls(corpus, eval_rows)


# --- what a judge is given --------------------------------------------------------------------


def retrieved_documents(control: Control) -> list[dict[str, Any]]:
    """The saved chunks in the shape the copilot's retriever span records them."""
    return [{"page_content": text, "metadata": {"title": title}} for title, text in control.chunks]


def control_trace(control: Control, answer: str) -> Any:
    """A trace shaped like the copilot's, holding ``answer`` and the saved chunks.

    ``retrieval_groundedness`` reads the question and the answer from the root
    span and the documents from the retriever span, so those are what is built.
    The trace goes to whatever store MLflow is pointed at; the command points it
    at a temporary local one.
    """
    import mlflow
    from mlflow.entities import SpanType

    from copilot.schemas import CopilotAnswer

    with mlflow.start_span(name="run_copilot", span_type=SpanType.AGENT) as root:
        root.set_inputs({"question": control.question, "history_turns": 0})
        mlflow.update_current_trace(tags={"control_id": control.control_id})
        with (
            mlflow.start_span(name="tool_search_kb", span_type=SpanType.TOOL),
            mlflow.start_span(name="search_kb", span_type=SpanType.RETRIEVER) as search,
        ):
            search.set_inputs({"query": control.question})
            search.set_outputs(retrieved_documents(control))
        root.set_outputs(
            CopilotAnswer(
                answer=answer,
                tools_used=list(control.tools_used),
                question_as_processed=control.question,
            ).model_dump()
        )
        trace_id = root.trace_id
    mlflow.flush_trace_async_logging()
    return mlflow.get_trace(trace_id)


# --- running the judges -----------------------------------------------------------------------

# A judge as the evaluation calls it: ``Scorer.run``.
Judge = Callable[..., Any]


def _read(result: Any, judge: str) -> tuple[str | None, str, str | None]:
    """A judge's result as (verdict, reason, error). Several verdicts are a no if any is."""
    feedbacks = result if isinstance(result, list) else [result]
    feedbacks = [item for item in feedbacks if getattr(item, "name", None) == judge]
    if not feedbacks:
        return None, "", "the judge gave no verdict for this answer"
    failed = [item for item in feedbacks if getattr(item, "error", None)]
    if failed:
        return None, "", str(failed[0].error)[:300]
    verdicts = [as_pass(item.value) for item in feedbacks]
    if any(verdict is None for verdict in verdicts):
        return None, "", f"not a yes or no: {feedbacks[0].value!r}"[:300]
    reason = " ".join(str(item.rationale or "").strip() for item in feedbacks).strip()
    return ("yes" if all(verdicts) else "no"), reason, None


def judge_answer(
    control: Control,
    answer: str,
    judge_name: str,
    judge: Judge,
    *,
    make_trace: Callable[[Control, str], Any] = control_trace,
    attempts: int = 3,
    wait_seconds: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str | None, str, str | None]:
    """One judge's verdict on one answer, as (verdict, reason, error).

    A call that fails is tried again after a wait, because the judge endpoint
    rejects calls when it is busy. After the last try the error is recorded and
    the verdict is left empty: it is not counted as a catch or as a miss.
    """
    trace = make_trace(control, answer) if judge_name == GROUNDEDNESS else None
    error: str | None = None
    for attempt in range(attempts):
        if attempt:
            sleep(wait_seconds * attempt)
        try:
            result = judge(
                inputs={"question": control.question},
                outputs=answer,
                expectations=dict(control.expectations),
                trace=trace,
            )
        except Exception as raised:
            error = f"{type(raised).__name__}: {raised}"[:300]
            continue
        verdict, reason, error = _read(result, judge_name)
        if error is None:
            return verdict, reason, None
    return None, "", error


def run_controls(
    controls: Sequence[Control],
    judges: Mapping[str, Judge],
    *,
    originals: bool = False,
    pause_seconds: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    progress: Callable[[str], None] = lambda _line: None,
    **judging: Any,
) -> list[dict[str, Any]]:
    """Every verdict: each control by each judge that should fail it.

    With ``originals``, the same judges also read the answer as the copilot
    wrote it. One call is made at a time, with a pause between calls.
    """
    verdicts: list[dict[str, Any]] = []
    for control in controls:
        for judge_name in control.should_fail:
            variants = [("control", control.answer)]
            if originals:
                variants.append(("original", control.original_answer))
            for variant, answer in variants:
                if verdicts:
                    sleep(pause_seconds)
                verdict, reason, error = judge_answer(
                    control, answer, judge_name, judges[judge_name], sleep=sleep, **judging
                )
                verdicts.append(
                    {
                        "control": control.control_id,
                        "row": control.row_id,
                        "kind": control.kind,
                        "judge": judge_name,
                        "variant": variant,
                        "verdict": verdict,
                        "rationale": reason,
                        "error": error,
                    }
                )
                progress(
                    f"{control.control_id} {control.row_id} {judge_name} {variant}: "
                    f"{verdict or 'no verdict'}"
                )
    return verdicts


# --- the result -------------------------------------------------------------------------------


def _rate(count: int, of: int) -> dict[str, Any]:
    if of == 0:
        return {"count": 0, "of": 0, "rate": None, "ci95": None}
    return {"count": count, "of": of, "rate": count / of, "ci95": list(wilson_interval(count, of))}


def _caught(verdicts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [item for item in verdicts if item["verdict"] is not None]
    return _rate(sum(1 for item in scored if item["verdict"] == "no"), len(scored))


def summarise(verdicts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How many controls each judge caught, with intervals. A verdict of no is a catch.

    A call that ended in an error has no verdict and is counted apart. When the
    answers as written were judged too, the summary also says how many of them
    the judge passed, and how many controls it caught among those whose
    original it passed: a catch only shows something if the judge would have
    passed the answer before it was changed.
    """
    controls = [item for item in verdicts if item["variant"] == "control"]
    originals = {
        (item["control"], item["judge"]): item["verdict"]
        for item in verdicts
        if item["variant"] == "original"
    }
    judges = [name for name in JUDGES if any(item["judge"] == name for item in controls)]
    kinds = sorted({item["kind"] for item in controls})
    summary: dict[str, Any] = {
        "controls_judged": len({item["control"] for item in controls}),
        "verdicts": len(controls),
        "errors": sum(1 for item in verdicts if item["verdict"] is None),
        "caught": _caught(controls),
        "caught_by_judge": {
            name: _caught([item for item in controls if item["judge"] == name]) for name in judges
        },
        "caught_by_kind": {
            kind: _caught([item for item in controls if item["kind"] == kind]) for kind in kinds
        },
        "missed": [
            {key: item[key] for key in ("control", "row", "kind", "judge")}
            for item in controls
            if item["verdict"] == "yes"
        ],
    }
    if originals:
        passed = {key for key, verdict in originals.items() if verdict == "yes"}
        judged = [verdict for verdict in originals.values() if verdict is not None]
        summary["originals_passed"] = _rate(len(passed), len(judged))
        summary["originals_passed_by_judge"] = {
            name: _rate(
                sum(1 for key in passed if key[1] == name),
                sum(1 for key, verdict in originals.items() if key[1] == name and verdict),
            )
            for name in judges
        }
        summary["caught_where_the_original_passed"] = _caught(
            [item for item in controls if (item["control"], item["judge"]) in passed]
        )
    return summary


def _line(label: str, rate: Mapping[str, Any]) -> str:
    if not rate["of"]:
        return f"  {label}: none judged"
    return f"  {label}: {rate_with_interval(rate['count'], rate['of'])}"


def print_summary(summary: Mapping[str, Any]) -> None:
    """Print the counts for a person to read. Intervals are 95% Wilson intervals."""
    print(
        f"{summary['controls_judged']} wrong answers, {summary['verdicts']} verdicts, "
        f"{summary['errors']} calls that ended in an error"
    )
    print("caught (the judge said no to a wrong answer), with the 95% interval:")
    print(_line("all judges", summary["caught"]))
    for name, rate in summary["caught_by_judge"].items():
        print(_line(name, rate))
    print("by what was changed:")
    for kind, rate in summary["caught_by_kind"].items():
        print(_line(kind, rate))
    for item in summary["missed"]:
        print(f"  missed: {item['control']} ({item['row']}, {item['kind']}) by {item['judge']}")
    if "originals_passed" in summary:
        print("the same answers before they were changed:")
        print(_line("passed by the judge", summary["originals_passed"]))
        for name, rate in summary["originals_passed_by_judge"].items():
            print(_line(f"passed by {name}", rate))
        print(
            _line(
                "caught, where the judge passed the original",
                summary["caught_where_the_original_passed"],
            )
        )


def _numbered(items: Sequence[Any]) -> str:
    return "\n".join(f"{number}. {item}" for number, item in enumerate(items, start=1))


def reference_for(control: Control, judge: str) -> str:
    """What ``judge`` grades this control against, as text for the labelling sheet."""
    if judge == CORRECTNESS:
        return _numbered(control.expectations.get("expected_facts") or [])
    if judge == GUIDELINES:
        return _numbered(control.expectations.get("guidelines") or [])
    return "\n\n".join(
        f"[{number}] {title}\n{text.strip()}"
        for number, (title, text) in enumerate(control.chunks, start=1)
    )


def control_sheet_rows(
    controls: Sequence[Control], verdicts: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    """The verdicts on the controls as rows of a labelling sheet, grouped by judge.

    The person who labels confirms that each control is wrong in the way it was
    meant to be: a control that is not wrong after all is a fault of the
    control, not a miss of the judge.
    """
    by_id = {control.control_id: control for control in controls}
    rows: list[dict[str, str]] = []
    for judge in JUDGES:
        for item in verdicts:
            if item["judge"] != judge or item["variant"] != "control" or item["verdict"] is None:
                continue
            control = by_id[item["control"]]
            rows.append(
                {
                    "key": f"{control.control_id}:{judge}",
                    "set": "control",
                    "id": control.row_id,
                    "category": control.category,
                    "judge": judge,
                    "question": control.question,
                    "answer": control.answer,
                    "reference": reference_for(control, judge),
                    "human": "",
                    "note": "",
                    "judge_verdict": str(item["verdict"]),
                    "judge_rationale": str(item["rationale"]),
                    "changed": control.changed,
                }
            )
    return rows


# --- the command ------------------------------------------------------------------------------


def _print_controls(controls: Sequence[Control]) -> None:
    for control in controls:
        print(
            f"{control.control_id}  {control.row_id}  {control.kind}  "
            f"should fail: {', '.join(control.should_fail)}"
        )
        print(f"      {control.changed}")


def _live_judges(endpoint: str) -> dict[str, Judge]:
    """The evaluation's own judges, by name, on a local trace store."""
    # Imported here so that building, listing and the tests load no model stack.
    import mlflow
    from dotenv import load_dotenv

    from eval.scorers import llm_judges

    # Puts DATABRICKS_HOST and DATABRICKS_CONFIG_PROFILE where the SDK looks.
    load_dotenv()
    # The traces built for the groundedness judge are scaffolding. They go to a local
    # store, so that no made-up wrong answer is written to the workspace experiment.
    store = Path(tempfile.mkdtemp(prefix="judge-controls-")) / "mlflow.db"
    mlflow.set_tracking_uri(f"sqlite:///{store.as_posix()}")
    mlflow.set_experiment("judge-controls")
    return {
        judge.name: judge.run
        for judge in llm_judges(endpoint, include_ragas=False)
        if judge.name in JUDGES
    }


def main(argv: list[str] | None = None) -> None:
    """List the controls, or judge them and report how many were caught."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--list", action="store_true", help="print the controls and stop")
    parser.add_argument("--ids", default=None, help="only these controls, separated by commas")
    parser.add_argument("--limit", type=int, default=None, help="only the first N controls")
    parser.add_argument(
        "--originals", action="store_true", help="also judge each answer as it was written"
    )
    parser.add_argument("--pause", type=float, default=0.5, help="seconds between judge calls")
    parser.add_argument("--save", action="store_true", help="write the result and a sheet")
    parser.add_argument("--tag", default=None, help="a short name added to the saved file names")
    args = parser.parse_args(argv)

    controls = load_controls()
    total = len(controls)
    if args.ids:
        wanted = [name.strip() for name in args.ids.split(",") if name.strip()]
        unknown = sorted(set(wanted) - {control.control_id for control in controls})
        if unknown:
            print(f"not started: no control is called {', '.join(unknown)}")
            raise SystemExit(1)
        controls = [control for control in controls if control.control_id in wanted]
    if args.limit:
        controls = controls[: args.limit]
    if args.list:
        _print_controls(controls)
        return

    git_dirty = bool(
        _git("status", "--porcelain", "--", ".", ":(exclude)eval/results", ":(exclude)eval/labels")
    )
    if args.save and git_dirty:
        print("not started: commit your changes first so the result has a clean git SHA")
        raise SystemExit(1)

    from copilot.config import load_settings

    settings = load_settings()
    judges = _live_judges(settings.judge_endpoint)
    print(
        f"{len(controls)} of {total} controls, judged by {settings.judge_endpoint}. "
        "The copilot is not called."
    )
    verdicts = run_controls(
        controls,
        judges,
        originals=args.originals,
        pause_seconds=args.pause,
        progress=lambda line: print(f"  {line}", flush=True),
    )
    summary = summarise(verdicts)
    print()
    print_summary(summary)
    for item in verdicts:
        if item["error"]:
            print(f"  error: {item['control']} {item['judge']} {item['variant']}: {item['error']}")

    if not args.save:
        return
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    run_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "run_at": run_at,
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": git_dirty,
        "judge_endpoint": settings.judge_endpoint,
        "versions": {"mlflow": version("mlflow")},
        "corpus": {
            "file": CORPUS.as_posix(),
            "sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "collected_at": corpus["collected_at"],
            "git_sha": corpus["git_sha"],
            "llm_endpoint": corpus["llm_endpoint"],
            "prompt_version": corpus["prompt_version"],
        },
        "eval_set_sha256": hashlib.sha256(EVAL_SET.read_bytes()).hexdigest(),
        "controls_defined": total,
        # False when --ids or --limit left some controls out.
        "all_controls": len(controls) == total,
        "originals_judged": args.originals,
        "summary": summary,
        "controls": [
            {
                "control": control.control_id,
                "row": control.row_id,
                "kind": control.kind,
                "changed": control.changed,
                "should_fail": list(control.should_fail),
                "question": control.question,
                "answer": control.answer,
            }
            for control in controls
        ],
        "verdicts": verdicts,
    }
    name = f"judge_controls_{run_at[:10]}" + (f"_{args.tag}" if args.tag else "")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"saved {path.as_posix()}")
    rows = control_sheet_rows(controls, verdicts)
    csv_path = LABELS_DIR / f"{name}.csv"
    write_csv(rows, csv_path, (*SHEET_COLUMNS, "changed"))
    print(f"wrote {csv_path.as_posix()}")
    markdown_path = csv_path.with_suffix(".md")
    markdown_path.write_text(
        sheet_markdown(
            rows,
            title=f"Judge controls: {name}",
            about=[
                f"Answers made wrong on purpose, judged by `{settings.judge_endpoint}` on "
                f"{run_at[:10]} (UTC) at commit `{result['git_sha'][:7]}`. Each should get a "
                "no. Label each one to confirm it is wrong in the way described."
            ],
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {markdown_path.as_posix()}")


if __name__ == "__main__":
    main()
