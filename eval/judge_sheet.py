"""Export the judge's verdicts of a saved run as a sheet for a person to label.

Usage:
    python -m eval.judge_sheet eval/results/2026-11-15_m4-full-A-ann.json
    python -m eval.judge_sheet eval/results/<file>.json --blind
    python -m eval.judge_sheet --render eval/labels/<file>_judge_sheet.csv

The judge is a language model, and a saved result holds its verdicts but not the
answers it read or the reasons it gave. Those are on the traces of the MLflow
run the result names. This reads them back and writes one row for every verdict
of the judges that decide whether an answer is right:

- ``correctness``: does the answer support every expected fact?
- ``expectations_guidelines``: does the answer follow every rule of the row?
- ``retrieval_groundedness``: is what the answer states supported by the
  retrieved text?

Each row has the question as the copilot processed it, the answer, what the
answer is graded against, the judge's verdict and reason, and two empty columns,
``human`` (yes or no) and ``note``, for the person who labels. It is written
twice: a CSV file to label in a spreadsheet, and a Markdown file to read.
``eval/judge_agreement.py`` scores the labelled CSV.

``--blind`` leaves the judge's verdict and reason out of the sheet and writes
them to a file beside it, so the person labels without seeing them.

Everything in the sheet is read from the traces, which hold redacted text only.
The evaluation set, which holds questions as they were written, is not read.
Reading traces needs the workspace; ``--render`` needs nothing and rewrites the
Markdown file from a CSV file, with the labels typed into it.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.report import CATEGORY_NAMES, as_pass

LABELS_DIR = Path("eval/labels")
EVAL_ID_TAG = "eval_id"
ROOT_SPAN_NAME = "run_copilot"
ANSWER_SPAN_NAME = "generate_answer"
SAMPLE_SEED = 20261116

# The judges whose verdict says whether an answer is right, in the order of the sheet.
JUDGES: tuple[str, ...] = ("correctness", "expectations_guidelines", "retrieval_groundedness")
# What the person decides for each judge. It is the question the judge was asked.
JUDGE_QUESTIONS: dict[str, str] = {
    "correctness": (
        "Does the answer state or clearly support every expected fact? Answer yes or no. "
        "Extra detail that the facts do not list does not make an answer wrong."
    ),
    "expectations_guidelines": "Does the answer follow every rule listed? Answer yes or no.",
    "retrieval_groundedness": (
        "Is everything the answer states supported by the retrieved text? Answer yes or no. "
        "One statement the text does not support makes it no."
    ),
}
# What each judge grades against, as the heading of that part of a row.
REFERENCE_HEADINGS: dict[str, str] = {
    "correctness": "Expected facts",
    "expectations_guidelines": "Rules",
    "retrieval_groundedness": "Retrieved text",
}
# The expectation each judge reads, by the name MLflow stores it under on the trace.
_EXPECTATION_NAMES: dict[str, tuple[str, ...]] = {
    "correctness": ("expected_facts", "expected_response"),
    "expectations_guidelines": ("guidelines",),
}

SHEET_COLUMNS: tuple[str, ...] = (
    "key",
    "set",
    "id",
    "category",
    "judge",
    "question",
    "answer",
    "reference",
    "human",
    "note",
    "judge_verdict",
    "judge_rationale",
)
VERDICT_COLUMNS: tuple[str, ...] = ("key", "judge_verdict", "judge_rationale")
# A spreadsheet cell holds 32,767 characters. Longer text is cut in the CSV file and
# kept whole in the Markdown file.
MAX_CELL_CHARS = 30000
CUT_NOTE = "\n[cut here: the Markdown sheet has the whole text]"
_FORMULA_STARTS = frozenset({"=", "+", "-", "@"})


# --- reading a trace ------------------------------------------------------------------------


def _feedbacks(trace: Any) -> list[Any]:
    """The scorer results on a trace that have not been replaced by a later one."""
    return [
        assessment
        for assessment in trace.info.assessments or []
        if getattr(assessment, "feedback", None) is not None
        and getattr(assessment, "valid", True) is not False
    ]


def best_traces(traces: Sequence[Any]) -> dict[str, Any]:
    """One trace per evaluation row: the one with the most scorer results.

    This is the choice ``eval.run_eval.rows_by_eval_id`` makes, so the sheet
    shows the answers the saved result was scored on.
    """
    best: dict[str, Any] = {}
    for trace in traces:
        eval_id = (trace.info.tags or {}).get(EVAL_ID_TAG)
        if not eval_id:
            continue
        if eval_id not in best or len(_score_names(trace)) > len(_score_names(best[eval_id])):
            best[eval_id] = trace
    return best


def _score_names(trace: Any) -> set[str]:
    return {assessment.name for assessment in _feedbacks(trace)}


def _root_span(trace: Any) -> Any:
    spans = trace.search_spans(name=ROOT_SPAN_NAME)
    return spans[0] if spans else None


def question_asked(trace: Any) -> str:
    """The question on the trace, with the earlier turns of the conversation if it had any.

    Both are the redacted text the copilot worked from.
    """
    root = _root_span(trace)
    inputs = root.inputs if root is not None and isinstance(root.inputs, dict) else {}
    question = str(inputs.get("question") or "")
    if not inputs.get("history_turns"):
        return question
    spans = trace.search_spans(name=ANSWER_SPAN_NAME)
    first = spans[0].inputs if spans and isinstance(spans[0].inputs, dict) else {}
    # The first model call is given the system prompt, the earlier turns, then the question.
    earlier = [
        f"{'Copilot' if message.get('role') == 'ai' else 'Agent'}: {message.get('content')}"
        for message in (first.get("messages") or [])[1:-1]
        if isinstance(message, dict) and message.get("role") in {"human", "ai"}
    ]
    if not earlier:
        return question
    return "Earlier in the conversation:\n" + "\n".join(earlier) + f"\n\nQuestion: {question}"


def answer_given(trace: Any) -> str:
    """The copilot's answer, as recorded on the trace."""
    root = _root_span(trace)
    outputs = root.outputs if root is not None and isinstance(root.outputs, dict) else {}
    return str(outputs.get("answer") or "")


def retrieved_text(trace: Any) -> str:
    """Every retrieved chunk on the trace, numbered in the order it was retrieved."""
    blocks: list[str] = []
    for span in trace.search_spans(span_type="RETRIEVER"):
        for document in span.outputs or []:
            if not isinstance(document, dict):
                continue
            metadata = document.get("metadata") or {}
            title = metadata.get("title") or metadata.get("doc_uri") or "untitled"
            text = str(document.get("page_content") or "").strip()
            blocks.append(f"[{len(blocks) + 1}] {title}\n{text}")
    return "\n\n".join(blocks)


def _numbered(value: Any) -> str:
    """A list of facts or rules as numbered lines. A dash would be read as a formula."""
    items = value if isinstance(value, list) else [value]
    return "\n".join(f"{number}. {item}" for number, item in enumerate(items, start=1))


def reference_for(trace: Any, judge: str) -> str:
    """What ``judge`` graded the answer against, read from the trace.

    MLflow stores a row's expected facts and rules on its trace, so they are the
    ones the judge was given, even if the evaluation set has changed since.
    """
    if judge == "retrieval_groundedness":
        return retrieved_text(trace)
    wanted = _EXPECTATION_NAMES.get(judge, ())
    for name in wanted:
        for assessment in trace.info.assessments or []:
            expectation = getattr(assessment, "expectation", None)
            if assessment.name == name and expectation is not None:
                return _numbered(expectation.value)
    return ""


# --- the rows of the sheet --------------------------------------------------------------------


def sheet_rows(
    traces: Sequence[Any],
    *,
    categories: Mapping[str, str] | None = None,
    judges: Sequence[str] = JUDGES,
    set_name: str = "evaluation",
) -> list[dict[str, str]]:
    """One row per verdict of ``judges``, grouped by judge and then by evaluation row.

    A verdict that is not yes or no, or that the judge failed to give, is left
    out: there is nothing to agree or disagree with. If a trace holds more than
    one verdict of a judge, each gets a row and a number after its key.
    """
    chosen = best_traces(traces)
    rows: list[dict[str, str]] = []
    for judge in judges:
        for eval_id in sorted(chosen):
            trace = chosen[eval_id]
            verdicts = [
                assessment
                for assessment in _feedbacks(trace)
                if assessment.name == judge
                and not getattr(assessment.feedback, "error", None)
                and as_pass(assessment.feedback.value) is not None
            ]
            for number, assessment in enumerate(verdicts, start=1):
                key = f"{eval_id}:{judge}" + (f"#{number}" if len(verdicts) > 1 else "")
                rows.append(
                    {
                        "key": key,
                        "set": set_name,
                        "id": eval_id,
                        "category": (categories or {}).get(eval_id, ""),
                        "judge": judge,
                        "question": question_asked(trace),
                        "answer": answer_given(trace),
                        "reference": reference_for(trace, judge),
                        "human": "",
                        "note": "",
                        "judge_verdict": "yes" if as_pass(assessment.feedback.value) else "no",
                        "judge_rationale": str(getattr(assessment, "rationale", None) or ""),
                    }
                )
    return rows


def sample_rows(
    rows: Sequence[Mapping[str, str]], per_judge: int, seed: int = SAMPLE_SEED
) -> list[dict[str, str]]:
    """At most ``per_judge`` rows of each judge, drawn at random, the same ones every time.

    The draw does not look at the verdict, so agreement on the sample estimates
    agreement on all of the judge's verdicts.
    """
    by_judge: dict[str, list[int]] = defaultdict(list)
    for position, row in enumerate(rows):
        by_judge[row["judge"]].append(position)
    rng = random.Random(seed)  # noqa: S311 - a fixed seed for a repeatable sample, not security
    kept: set[int] = set()
    for judge in sorted(by_judge):
        positions = by_judge[judge]
        kept.update(rng.sample(positions, min(per_judge, len(positions))))
    return [dict(row) for position, row in enumerate(rows) if position in kept]


def differences_from_result(
    rows: Sequence[Mapping[str, str]], report: Mapping[str, Any], judges: Sequence[str] = JUDGES
) -> list[str]:
    """Where the sheet and the saved result do not hold the same verdicts.

    The saved result is what the published figures rest on, so a verdict that
    is in one and not the other, or differs, is reported and not hidden.
    """
    in_sheet: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        in_sheet[(row["id"], row["judge"])].add(row["judge_verdict"])
    found: list[str] = []
    for item in report.get("per_row", []):
        for judge in judges:
            saved = as_pass(item["scores"].get(judge))
            if saved is None:
                continue
            verdicts = in_sheet.pop((item["id"], judge), None)
            wanted = "yes" if saved else "no"
            if verdicts is None:
                found.append(f"{item['id']} {judge}: {wanted} in the result, not on a trace")
            elif wanted not in verdicts:
                found.append(
                    f"{item['id']} {judge}: {wanted} in the result, "
                    f"{' and '.join(sorted(verdicts))} on the trace"
                )
    found.extend(
        f"{eval_id} {judge}: on a trace, not in the result" for eval_id, judge in sorted(in_sheet)
    )
    return found


def split_blind(
    rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """The rows without the judge's verdict and reason, and those two apart, by key."""
    hidden = [{column: row[column] for column in VERDICT_COLUMNS} for row in rows]
    shown = [{**row, "judge_verdict": "", "judge_rationale": ""} for row in rows]
    return shown, hidden


def with_verdicts(
    rows: Sequence[Mapping[str, str]], verdicts: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    """Put the judge's verdicts back into rows that were labelled blind.

    Raises:
        ValueError: If a row has no verdict in ``verdicts``.
    """
    by_key = {row["key"]: row for row in verdicts}
    missing = [row["key"] for row in rows if row["key"] not in by_key]
    if missing:
        msg = f"no verdict for: {', '.join(missing[:10])}"
        raise ValueError(msg)
    return [
        {
            **row,
            "judge_verdict": by_key[row["key"]]["judge_verdict"],
            "judge_rationale": by_key[row["key"]].get("judge_rationale", ""),
        }
        for row in rows
    ]


# --- writing and reading the CSV file ---------------------------------------------------------


def spreadsheet_safe(text: str) -> str:
    """Text a spreadsheet will show as text.

    A cell that starts with ``=``, ``+``, ``-`` or ``@`` is run as a formula.
    The answers are written by a model, so such a cell gets a leading apostrophe,
    which a spreadsheet hides. A cell longer than a spreadsheet holds is cut.
    """
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS] + CUT_NOTE
    return "'" + text if text[:1] in _FORMULA_STARTS else text


def _from_spreadsheet(text: str) -> str:
    """Undo the apostrophe ``spreadsheet_safe`` adds, where a spreadsheet kept it."""
    return text[1:] if text[:1] == "'" and text[1:2] in _FORMULA_STARTS else text


def write_csv(
    rows: Sequence[Mapping[str, str]], path: Path, columns: Sequence[str] = SHEET_COLUMNS
) -> None:
    """Write rows as a CSV file that Excel and Google Sheets open as UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # The byte order mark is what makes Excel read the file as UTF-8.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {column: spreadsheet_safe(str(row.get(column, ""))) for column in columns}
            )


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a sheet back. Cells a spreadsheet left empty come back as empty text.

    A sheet is written as UTF-8. Excel's plain "CSV" choice saves it in the
    Windows code page instead, which turns a few symbols in the answers into
    question marks and leaves the keys, the verdicts and the labels as they were.
    Such a file is read too, so that an afternoon of labelling is not lost to it.
    """
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    return [
        {
            str(column): _from_spreadsheet(value or "")
            for column, value in row.items()
            if column is not None
        }
        for row in csv.DictReader(io.StringIO(text, newline=""))
    ]


# --- the Markdown file ------------------------------------------------------------------------


def _quoted(text: str) -> str:
    """Text as a Markdown quote. ``<PERSON_1>`` would otherwise be read as a tag and vanish."""
    escaped = text.strip().replace("<", "\\<")
    return "\n".join(f"> {line}".rstrip() for line in escaped.splitlines()) or "> (empty)"


def _fenced(text: str) -> str:
    """Text as a code block, with a fence longer than any run of backticks inside it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text.strip()}\n{fence}"


def sheet_markdown(
    rows: Sequence[Mapping[str, str]], *, title: str, about: Sequence[str] = ()
) -> str:
    """The sheet as a page to read: one part per judge, one section per verdict.

    The judge's verdict is folded away under each answer, so that it can be read
    after the person has decided. A row with no verdict, from a blind sheet,
    shows none.
    """
    counts = Counter(row["judge"] for row in rows)
    labelled = sum(1 for row in rows if row.get("human", "").strip())
    lines = [f"# {title}", ""]
    lines += [*about, ""] if about else []
    lines += [
        f"{len(rows)} verdicts, {labelled} labelled. Labels are typed into the CSV file of "
        "the same name, in the `human` column (yes or no) and the `note` column. This page "
        "is for reading and is rewritten from that file by "
        "`python -m eval.judge_sheet --render <file>.csv`.",
        "",
        "The questions are the redacted ones the copilot worked from. A name in angle "
        "brackets, such as \\<PERSON_1>, stands for a detail that was removed.",
        "",
    ]
    for judge in [name for name in JUDGES if counts[name]] + sorted(set(counts) - set(JUDGES)):
        heading = REFERENCE_HEADINGS.get(judge, "Graded against")
        lines += [
            f"## {judge} ({counts[judge]})",
            "",
            f"**What to decide.** {JUDGE_QUESTIONS.get(judge, 'Is the answer right?')}",
            "",
        ]
        for row in (row for row in rows if row["judge"] == judge):
            category = CATEGORY_NAMES.get(row.get("category", ""), row.get("category", ""))
            where = " · ".join(part for part in (row["id"], category, row.get("set", "")) if part)
            lines += [f"### `{row['key']}`", "", where, ""]
            if row.get("changed"):
                lines += [f"**What was changed.** {row['changed']}", ""]
            lines += ["**Question**", "", _quoted(row["question"]), ""]
            lines += ["**Answer**", "", _quoted(row["answer"]), ""]
            reference = row.get("reference", "").strip()
            if judge == "retrieval_groundedness" and reference:
                lines += [
                    f"<details><summary><b>{heading}</b> (open to read)</summary>",
                    "",
                    _fenced(reference),
                    "",
                    "</details>",
                    "",
                ]
            else:
                lines += [f"**{heading}**", "", reference or "(none on the trace)", ""]
            if row.get("judge_verdict"):
                lines += [
                    "<details><summary>The judge's verdict (open after deciding)</summary>",
                    "",
                    f"**{row['judge_verdict']}.** {row.get('judge_rationale', '').strip()}",
                    "",
                    "</details>",
                    "",
                ]
            human = row.get("human", "").strip()
            note = row.get("note", "").strip()
            lines += [f"**Human:** {human or '(not labelled)'}" + (f". {note}" if note else ""), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


# --- the command ------------------------------------------------------------------------------


def _about(
    report: Mapping[str, Any], result_name: str, blind: bool, sample: int | None = None
) -> list[str]:
    lines = [
        f"The verdicts of the judge in `{result_name}`: run on {report['run_at'][:10]} (UTC) at "
        f"commit `{report['git_sha'][:7]}`, answers by `{report.get('llm_endpoint')}`, judged by "
        f"`{report.get('judge_endpoint')}`, prompt {report.get('prompt_version')}, MLflow run "
        f"`{report['mlflow_run_id']}`. Exported on "
        f"{datetime.now(UTC).strftime('%Y-%m-%d')} (UTC) by `python -m eval.judge_sheet`.",
    ]
    if sample:
        lines += [
            "",
            f"This is a sample: at most {sample} verdicts of each judge, drawn at random "
            f"with seed {SAMPLE_SEED} without looking at the verdict.",
        ]
    if blind:
        lines += [
            "",
            "This sheet is blind: the judge's verdicts are in the file ending "
            "`_verdicts.csv` and are not shown here.",
        ]
    return lines


def read_traces(run_id: str) -> list[Any]:
    """The traces of one evaluation run, read from the workspace."""
    # Imported here so that rendering, and the tests, need no workspace.
    import mlflow
    from dotenv import load_dotenv

    from copilot.config import load_settings

    # Puts DATABRICKS_HOST and DATABRICKS_CONFIG_PROFILE where the SDK and MLflow look.
    load_dotenv()
    settings = load_settings()
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment(settings.mlflow_experiment)
    return list(mlflow.search_traces(run_id=run_id, return_type="list"))


def render(csv_path: Path) -> Path:
    """Rewrite the Markdown file beside a CSV sheet from what the CSV file holds now."""
    rows = read_csv(csv_path)
    path = csv_path.with_suffix(".md")
    text = sheet_markdown(rows, title=f"Judge labelling sheet: {csv_path.stem}")
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def main(argv: list[str] | None = None) -> None:
    """Export the sheet of one saved run, or rewrite a sheet's Markdown file."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("result", nargs="?", type=Path, help="a saved full-run result file")
    parser.add_argument("--out-dir", type=Path, default=LABELS_DIR)
    parser.add_argument(
        "--judges", default=",".join(JUDGES), help="the judges to export, separated by commas"
    )
    parser.add_argument(
        "--sample", type=int, default=None, help="at most this many verdicts of each judge"
    )
    parser.add_argument(
        "--blind", action="store_true", help="keep the judge's verdicts out of the sheet"
    )
    parser.add_argument(
        "--render", type=Path, default=None, help="rewrite the Markdown file of this CSV sheet"
    )
    args = parser.parse_args(argv)

    if args.render:
        print(f"wrote {render(args.render).as_posix()}")
        return
    if args.result is None:
        parser.error("name a saved result file, or use --render")

    report = json.loads(args.result.read_text(encoding="utf-8"))
    judges = [name.strip() for name in args.judges.split(",") if name.strip()]
    categories = {item["id"]: str(item.get("category", "")) for item in report.get("per_row", [])}
    traces = read_traces(report["mlflow_run_id"])
    rows = sheet_rows(traces, categories=categories, judges=judges)
    if not rows:
        print(f"no verdict of {', '.join(judges)} on the {len(traces)} traces of this run")
        raise SystemExit(1)

    differences = differences_from_result(rows, report, judges)
    for difference in differences:
        print(f"differs from the result file: {difference}")
    if args.sample:
        rows = sample_rows(rows, args.sample)

    stem = f"{args.result.stem}_judge_sheet"
    shown, hidden = split_blind(rows) if args.blind else (list(rows), [])
    csv_path = args.out_dir / f"{stem}.csv"
    write_csv(shown, csv_path)
    print(f"wrote {csv_path.as_posix()}")
    if args.blind:
        verdict_path = args.out_dir / f"{stem}_verdicts.csv"
        write_csv(hidden, verdict_path, VERDICT_COLUMNS)
        print(f"wrote {verdict_path.as_posix()}")
    markdown_path = args.out_dir / f"{stem}.md"
    markdown_path.write_text(
        sheet_markdown(
            shown,
            title=f"Judge labelling sheet: {args.result.name}",
            about=_about(report, args.result.name, args.blind, args.sample),
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {markdown_path.as_posix()}")

    counts = Counter(row["judge"] for row in rows)
    for judge in judges:
        if args.blind:
            print(f"  {judge}: {counts[judge]} verdicts")
            continue
        passed = sum(1 for row in rows if row["judge"] == judge and row["judge_verdict"] == "yes")
        print(f"  {judge}: {counts[judge]} verdicts ({passed} yes, {counts[judge] - passed} no)")
    print(
        f"{len(traces)} traces read, {len(differences)} differences from the result file. "
        "Fill in the human column of the CSV file, then run "
        f"python -m eval.judge_agreement {csv_path.as_posix()}"
    )


if __name__ == "__main__":
    main()
