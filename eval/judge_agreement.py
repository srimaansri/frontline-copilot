"""Score the judge against a person's labels.

Usage:
    python -m eval.judge_agreement eval/labels/<run>_judge_sheet.csv
    python -m eval.judge_agreement <sheet>.csv eval/labels/judge_controls_<date>.csv
    python -m eval.judge_agreement <sheet>.csv --verdicts <sheet>_verdicts.csv
    python -m eval.judge_agreement <sheet>.csv <controls>.csv --save --tag first

Reads one or more labelling sheets written by ``eval/judge_sheet.py`` or
``eval/judge_controls.py`` once a person has filled in the ``human`` column, and
reports for each judge:

- how often the judge and the person gave the same verdict, with a 95% Wilson
  interval;
- Cohen's kappa, which is that agreement with the part two raters would reach
  by chance taken out, with a bootstrap interval;
- the four counts behind both: the judge's yes and no against the person's;
- of the answers the person marked wrong, how many the judge failed, and of the
  answers the person marked right, how many it passed;
- every row where they disagree, with the judge's reason and the person's note.

A row with an empty ``human`` cell is not labelled yet. It is counted and left
out. A label that is not a yes or a no stops the run, so a typing slip cannot
be scored as either.

This module makes no model call and reads nothing but the sheets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.judge_sheet import read_csv, with_verdicts
from eval.redaction_eval import _git
from eval.stats import percentile, rate_with_interval, wilson_interval

RESULTS_DIR = Path("eval/results")
BOOTSTRAP_SEED = 20261116
BOOTSTRAP_RESAMPLES = 2000

_YES = frozenset({"yes", "y", "true", "1", "pass", "right", "correct"})
_NO = frozenset({"no", "n", "false", "0", "fail", "wrong", "incorrect"})

# (the judge's verdict, the person's verdict) for one row. True is yes.
Pair = tuple[bool, bool]


def parse_label(text: str) -> bool | None:
    """A yes or no typed into a sheet. Empty text is None: not labelled yet.

    Raises:
        ValueError: If the text is neither empty nor a yes or a no.
    """
    cleaned = text.strip().strip(".").lower()
    if not cleaned:
        return None
    if cleaned in _YES:
        return True
    if cleaned in _NO:
        return False
    msg = f"not a yes or a no: {text!r}"
    raise ValueError(msg)


def labelled_rows(
    rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """The rows a person has labelled, the number not labelled yet, and what is wrong.

    Each returned row is the sheet's row with ``judge_yes`` and ``human_yes``
    added. A row whose label or verdict cannot be read is named in the third
    value and left out of the first.
    """
    usable: list[dict[str, Any]] = []
    unlabelled = 0
    problems: list[str] = []
    seen: set[str] = set()
    for row in rows:
        key = row.get("key", "")
        if not key or key in seen:
            problems.append(f"{key or '(no key)'}: a row needs a key that no other row has")
            continue
        seen.add(key)
        try:
            human = parse_label(row.get("human", ""))
        except ValueError as error:
            problems.append(f"{key}: human is {error}")
            continue
        if human is None:
            unlabelled += 1
            continue
        try:
            judge = parse_label(row.get("judge_verdict", ""))
        except ValueError as error:
            problems.append(f"{key}: judge_verdict is {error}")
            continue
        if judge is None:
            problems.append(f"{key}: no judge verdict (a blind sheet needs --verdicts)")
            continue
        usable.append({**row, "judge_yes": judge, "human_yes": human})
    return usable, unlabelled, problems


# --- the statistics ---------------------------------------------------------------------------


def confusion(pairs: Sequence[Pair]) -> dict[str, int]:
    """The four counts: each of the judge's verdicts against each of the person's."""
    return {
        "judge_yes_human_yes": sum(1 for judge, human in pairs if judge and human),
        "judge_yes_human_no": sum(1 for judge, human in pairs if judge and not human),
        "judge_no_human_yes": sum(1 for judge, human in pairs if not judge and human),
        "judge_no_human_no": sum(1 for judge, human in pairs if not judge and not human),
    }


def cohens_kappa(pairs: Sequence[Pair]) -> float | None:
    """Cohen's kappa for two raters and two labels, or None where it is not defined.

    Kappa is ``(observed - expected) / (1 - expected)``, where expected is the
    agreement two raters with these yes-rates would reach if their verdicts
    were unrelated. It is 1 for full agreement and 0 for no more than chance.
    When both raters gave the same single answer to every row, expected is 1
    and there is nothing left to divide by.
    """
    total = len(pairs)
    if total == 0:
        return None
    observed = sum(1 for judge, human in pairs if judge == human) / total
    judge_yes = sum(1 for judge, _ in pairs if judge) / total
    human_yes = sum(1 for _, human in pairs if human) / total
    expected = judge_yes * human_yes + (1 - judge_yes) * (1 - human_yes)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def kappa_interval(
    pairs: Sequence[Pair], *, seed: int = BOOTSTRAP_SEED, resamples: int = BOOTSTRAP_RESAMPLES
) -> tuple[float, float] | None:
    """A 95% percentile bootstrap interval for kappa. The same every time, by its seed.

    The rows are drawn again with replacement and kappa is worked out on each
    draw. A draw in which kappa is not defined is left out: with one wrong
    answer among the rows, about a third of the draws hold none. The interval
    is wide when there are few rows of one kind, which is the honest answer.
    """
    if cohens_kappa(pairs) is None:
        return None
    rng = random.Random(seed)  # noqa: S311 - a fixed seed for a repeatable interval, not security
    values: list[float] = []
    for _ in range(resamples):
        drawn = cohens_kappa([pairs[rng.randrange(len(pairs))] for _ in pairs])
        if drawn is not None:
            values.append(drawn)
    if not values:
        return None
    return percentile(values, 0.025), percentile(values, 0.975)


def _rate(count: int, of: int) -> dict[str, Any]:
    if of == 0:
        return {"count": 0, "of": 0, "rate": None, "ci95": None}
    return {"count": count, "of": of, "rate": count / of, "ci95": list(wilson_interval(count, of))}


def agreement(pairs: Sequence[Pair]) -> dict[str, Any]:
    """Everything reported about one set of (judge, person) verdicts."""
    counts = confusion(pairs)
    wrong = counts["judge_yes_human_no"] + counts["judge_no_human_no"]
    right = counts["judge_yes_human_yes"] + counts["judge_no_human_yes"]
    interval = kappa_interval(pairs)
    return {
        "labelled": len(pairs),
        "agree": _rate(counts["judge_yes_human_yes"] + counts["judge_no_human_no"], len(pairs)),
        "kappa": cohens_kappa(pairs),
        "kappa_ci95": list(interval) if interval else None,
        "confusion": counts,
        # Of the answers the person marked wrong, the ones the judge failed.
        "wrong_answers_failed_by_judge": _rate(counts["judge_no_human_no"], wrong),
        # Of the answers the person marked right, the ones the judge passed.
        "right_answers_passed_by_judge": _rate(counts["judge_yes_human_yes"], right),
    }


def _pairs(rows: Sequence[Mapping[str, Any]]) -> list[Pair]:
    return [(bool(row["judge_yes"]), bool(row["human_yes"])) for row in rows]


def score(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Agreement for every judge, and for every judge within each set of rows.

    ``rows`` are labelled rows from ``labelled_rows``. A set is where a row came
    from: ``evaluation`` for a verdict of a saved run, ``control`` for an answer
    made wrong on purpose. The two are also reported apart, because agreement on
    answers that are nearly all right says little about catching a wrong one.
    """
    judges = sorted({row["judge"] for row in rows})
    sets = sorted({row.get("set") or "evaluation" for row in rows})
    result: dict[str, Any] = {
        "by_judge": {
            judge: agreement(_pairs([row for row in rows if row["judge"] == judge]))
            for judge in judges
        },
        "all_judges": agreement(_pairs(rows)),
        "disagreements": [
            {
                "key": row["key"],
                "set": row.get("set") or "evaluation",
                "judge": row["judge"],
                "judge_verdict": "yes" if row["judge_yes"] else "no",
                "human": "yes" if row["human_yes"] else "no",
                "note": row.get("note", "").strip(),
                "judge_rationale": row.get("judge_rationale", "").strip(),
            }
            for row in rows
            if row["judge_yes"] != row["human_yes"]
        ],
    }
    if len(sets) > 1:
        result["by_set_and_judge"] = {
            name: {
                judge: agreement(
                    _pairs(
                        [
                            row
                            for row in rows
                            if row["judge"] == judge and (row.get("set") or "evaluation") == name
                        ]
                    )
                )
                for judge in judges
                if any(
                    row["judge"] == judge and (row.get("set") or "evaluation") == name
                    for row in rows
                )
            }
            for name in sets
        }
    return result


# --- the report -------------------------------------------------------------------------------


def _show(rate: Mapping[str, Any]) -> str:
    return rate_with_interval(rate["count"], rate["of"]) if rate["of"] else "none labelled"


def agreement_lines(name: str, stats: Mapping[str, Any]) -> list[str]:
    """One judge's figures as lines of text."""
    counts = stats["confusion"]
    kappa = stats["kappa"]
    if kappa is None:
        kappa_text = "not defined: the judge and the person each gave one answer to every row"
    elif stats["kappa_ci95"] is None:
        kappa_text = f"{kappa:.2f} (no interval)"
    else:
        low, high = stats["kappa_ci95"]
        kappa_text = f"{kappa:.2f} (95% bootstrap interval {low:.2f} to {high:.2f})"
    yes_yes, yes_no = counts["judge_yes_human_yes"], counts["judge_yes_human_no"]
    no_yes, no_no = counts["judge_no_human_yes"], counts["judge_no_human_no"]
    return [
        f"{name}: {stats['labelled']} labelled",
        f"  same verdict                     {_show(stats['agree'])}",
        f"  Cohen's kappa                    {kappa_text}",
        "                    person yes   person no",
        f"  judge yes         {yes_yes:>10}  {yes_no:>10}",
        f"  judge no          {no_yes:>10}  {no_no:>10}",
        f"  wrong answers the judge failed   {_show(stats['wrong_answers_failed_by_judge'])}",
        f"  right answers the judge passed   {_show(stats['right_answers_passed_by_judge'])}",
    ]


def report_lines(result: Mapping[str, Any], unlabelled: int) -> list[str]:
    """The whole report as lines of text. Rates are count/total with a 95% Wilson interval."""
    lines: list[str] = []
    for judge, stats in result["by_judge"].items():
        lines += [*agreement_lines(judge, stats), ""]
    if len(result["by_judge"]) > 1:
        lines += [*agreement_lines("all judges together", result["all_judges"]), ""]
    for name, by_judge in result.get("by_set_and_judge", {}).items():
        lines += [f"--- rows of the set '{name}' only ---", ""]
        for judge, stats in by_judge.items():
            lines += [*agreement_lines(judge, stats), ""]
    lines.append(f"{len(result['disagreements'])} rows where the judge and the person disagree:")
    for item in result["disagreements"]:
        lines.append(
            f"  {item['key']} ({item['set']}): judge {item['judge_verdict']}, "
            f"person {item['human']}"
        )
        if item["note"]:
            lines.append(f"      person's note: {item['note']}")
        if item["judge_rationale"]:
            lines.append(f"      judge's reason: {item['judge_rationale']}")
    if unlabelled:
        lines += ["", f"{unlabelled} rows are not labelled yet and were left out."]
    return lines


def main(argv: list[str] | None = None) -> None:
    """Score the labelled sheets and print the report."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("sheets", nargs="+", type=Path, help="labelled CSV sheets")
    parser.add_argument(
        "--verdicts",
        nargs="*",
        type=Path,
        default=[],
        help="the judge's verdicts of sheets that were labelled blind",
    )
    parser.add_argument("--save", action="store_true", help="write the result to eval/results")
    parser.add_argument("--tag", default=None, help="a short name added to the saved file name")
    args = parser.parse_args(argv)

    hidden = [row for path in args.verdicts for row in read_csv(path)]
    rows: list[dict[str, str]] = []
    sheets: list[dict[str, Any]] = []
    for path in args.sheets:
        found = read_csv(path)
        if found and not any(row.get("judge_verdict", "").strip() for row in found):
            found = with_verdicts(found, hidden)
        rows += found
        sheets.append(
            {
                "file": path.as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "rows": len(found),
            }
        )
    usable, unlabelled, problems = labelled_rows(rows)
    for problem in problems:
        print(f"cannot be read: {problem}")
    if problems:
        print("stopped: correct these cells and run again. Nothing was scored.")
        raise SystemExit(1)
    if not usable:
        print(f"no row is labelled yet ({unlabelled} rows). Fill in the human column.")
        raise SystemExit(1)

    result = score(usable)
    print("\n".join(report_lines(result, unlabelled)))
    if not args.save:
        return
    git_dirty = bool(
        _git("status", "--porcelain", "--", ".", ":(exclude)eval/results", ":(exclude)eval/labels")
    )
    if git_dirty:
        print("not saved: commit your changes first so the result has a clean git SHA")
        raise SystemExit(1)
    run_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    saved = {
        "run_at": run_at,
        "git_sha": _git("rev-parse", "HEAD"),
        "sheets": sheets,
        "rows_labelled": len(usable),
        "rows_not_labelled": unlabelled,
        "kappa_interval": {
            "method": "percentile bootstrap over rows",
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
        },
        **result,
        "labels": [
            {
                "key": row["key"],
                "set": row.get("set") or "evaluation",
                "judge": row["judge"],
                "judge_verdict": "yes" if row["judge_yes"] else "no",
                "human": "yes" if row["human_yes"] else "no",
                "note": row.get("note", "").strip(),
            }
            for row in usable
        ],
    }
    name = f"judge_agreement_{run_at[:10]}" + (f"_{args.tag}" if args.tag else "")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\nsaved {path.as_posix()}")


if __name__ == "__main__":
    main()
