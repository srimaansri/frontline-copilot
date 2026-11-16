"""Check the extended evaluation set against the help articles and the plan catalogue.

Every expected fact in ``eval/eval_set_extended.jsonl`` comes with an evidence quote. This
script confirms that each quote is in the article or catalogue row it names, and that
each row has the shape its stratum needs. It reads files only: no model, no Databricks.

A quote from an article is matched against the article's ``body_text`` as stored in
``data/synthetic/kb_articles.jsonl``, Markdown marks included. A quote from the catalogue
(source ``plans``) is matched against one row of ``data/raw/plans.csv`` as
``python -m data_gen.plans`` writes it, for example ``Hotspot Boost,10.00,monthly``. Runs
of whitespace are collapsed on both sides before matching.

Usage:
    python -m eval.check_eval_set [--path eval/eval_set_extended.jsonl]

Exits with status 1 and one line per problem if anything is wrong.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from data_gen.plans import PLANS

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTENDED_SET = REPO_ROOT / "eval" / "eval_set_extended.jsonl"
BASE_SET = REPO_ROOT / "eval" / "eval_set.jsonl"
ARTICLES = REPO_ROOT / "data" / "synthetic" / "kb_articles.jsonl"

# The fewest rows each stratum must hold.
MIN_COUNTS: dict[str, int] = {
    "paraphrase": 60,
    "terse": 30,
    "unanswerable": 40,
    "multi_hop": 30,
    "pii_in_question": 25,
    "follow_up": 40,
    "hand_off": 20,
    "override": 15,
}
# Strata whose rows are graded by expected facts, each with an evidence quote.
FACT_STRATA = frozenset({"paraphrase", "terse", "multi_hop", "pii_in_question", "follow_up"})
CATEGORIES = frozenset({"kb", "plan", "call_summary", "escalation", "adversarial"})
TOOLS = frozenset({"search_kb", "get_plan_details", "summarize_call", "escalate_to_human"})
ROW_KEYS = frozenset(
    {"id", "category", "reviewed", "inputs", "expectations", "stratum", "evidence"}
)
EXPECTATION_KEYS = frozenset(
    {
        "expected_facts",
        "expected_source",
        "also_acceptable_sources",
        "should_escalate",
        "expected_tool",
        "guidelines",
    }
)
CATALOGUE_SOURCE = "plans"
NO_SOURCE = "none"
SEARCHED_PREFIX = "searched: "
FIRST_NEW_ID = 101
MAX_FACTS = 4

_ID = re.compile(r"E(\d{3,})")
_PHONE = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_FOUR_DIGITS = re.compile(r"(?<![\d-])\d{4}(?![\d-])")
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def collapse(text: str) -> str:
    """Replace every run of whitespace with one space and trim the ends."""
    return " ".join(text.split())


def load_articles(path: Path = ARTICLES) -> dict[str, str]:
    """Map each article slug to its body text with whitespace collapsed."""
    articles: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        article = json.loads(line)
        slug = str(article["url"]).rstrip("/").rsplit("/", 1)[-1]
        articles[slug] = collapse(str(article["body_text"]))
    return articles


def catalogue_rows() -> list[str]:
    """Each catalogue row as the CSV line ``python -m data_gen.plans`` writes for it."""
    lines = []
    for plan in PLANS:
        record = asdict(plan)
        record["monthly_price_usd"] = f"{plan.monthly_price_usd:.2f}"
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="").writerow(
            ["" if value is None else value for value in record.values()]
        )
        lines.append(collapse(buffer.getvalue()))
    return lines


def parse_lines(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse JSON Lines text into rows, with a problem for every line that is not a row."""
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            if number <= text.count("\n"):
                problems.append(f"line {number}: blank line")
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            problems.append(f"line {number}: not valid JSON ({error.msg})")
            continue
        if not isinstance(row, dict):
            problems.append(f"line {number}: not a JSON object")
            continue
        rows.append(row)
    return rows, problems


def read_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read a JSON Lines file, checking that it is UTF-8 with LF line endings."""
    data = path.read_bytes()
    problems: list[str] = []
    if b"\r" in data:
        problems.append(f"{path.name}: has CR characters; line endings must be LF")
    if not data.endswith(b"\n"):
        problems.append(f"{path.name}: does not end with a newline")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        return [], [*problems, f"{path.name}: not valid UTF-8 ({error.reason})"]
    rows, line_problems = parse_lines(text.replace("\r\n", "\n"))
    return rows, problems + line_problems


def quote_in_source(
    source: str, quote: str, articles: Mapping[str, str], catalogue: Sequence[str]
) -> bool:
    """Whether ``quote`` is verbatim in the named article, or in one catalogue row."""
    wanted = collapse(quote)
    if not wanted:
        return False
    if source == CATALOGUE_SOURCE:
        return any(wanted in line for line in catalogue)
    return wanted in articles.get(source, "")


def personal_details(question: str) -> set[str]:
    """Phone numbers, email addresses and four-digit groups found in a question."""
    return {
        *_PHONE.findall(question),
        *_EMAIL.findall(question),
        *_FOUR_DIGITS.findall(question),
    }


def question_key(row: Mapping[str, Any]) -> str:
    """The row's conversation as lower-case letters and digits, for spotting duplicates."""
    inputs = row.get("inputs")
    if not isinstance(inputs, dict):
        return ""
    turns = [
        str(turn.get("content", ""))
        for turn in inputs.get("history") or []
        if isinstance(turn, dict)
    ]
    turns.append(str(inputs.get("question", "")))
    return _NOT_ALNUM.sub(" ", " ".join(turns).lower()).strip()


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(_is_text(item) for item in value)


def _check_inputs(inputs: object, stratum: object) -> list[str]:
    if not isinstance(inputs, dict):
        return ["inputs is not an object"]
    problems = [
        f"inputs has unknown key {key!r}" for key in inputs.keys() - {"question", "history"}
    ]
    if not _is_text(inputs.get("question")):
        problems.append("inputs.question is missing or empty")
    history = inputs.get("history")
    if stratum != "follow_up":
        if history is not None:
            problems.append("only follow_up rows may have inputs.history")
        return problems
    if not isinstance(history, list) or len(history) < 2 or len(history) % 2:
        return [*problems, "follow_up rows need inputs.history: user and assistant turns in pairs"]
    for position, turn in enumerate(history):
        role = "user" if position % 2 == 0 else "assistant"
        if not isinstance(turn, dict) or turn.keys() != {"role", "content"}:
            problems.append(f"history[{position}] must have exactly the keys role and content")
        elif turn["role"] != role or not _is_text(turn["content"]):
            problems.append(f"history[{position}] must be a non-empty {role} turn")
    return problems


def _check_expectations(expectations: object, slugs: Mapping[str, str]) -> list[str]:
    if not isinstance(expectations, dict):
        return ["expectations is not an object"]
    problems = [
        f"expectations has unknown key {key!r}" for key in expectations.keys() - EXPECTATION_KEYS
    ]
    if not isinstance(expectations.get("should_escalate"), bool):
        problems.append("expectations.should_escalate must be true or false")
    if "expected_tool" not in expectations:
        problems.append("expectations.expected_tool is missing (use null for no tool)")
    elif expectations["expected_tool"] is not None and expectations["expected_tool"] not in TOOLS:
        problems.append(f"expected_tool {expectations['expected_tool']!r} is not a tool")
    facts = expectations.get("expected_facts")
    if facts is not None and not (_is_text_list(facts) and len(facts) <= MAX_FACTS):
        problems.append(f"expected_facts must be 1 to {MAX_FACTS} non-empty strings")
    guidelines = expectations.get("guidelines")
    if guidelines is not None and not _is_text_list(guidelines):
        problems.append("guidelines must be a non-empty list of non-empty strings")
    if not facts and not guidelines:
        problems.append("a row needs expected_facts or guidelines to be graded by")
    source = expectations.get("expected_source")
    if source is not None and source not in slugs:
        problems.append(f"expected_source {source!r} is not an article slug")
    alternates = expectations.get("also_acceptable_sources")
    if alternates is not None:
        if not _is_text_list(alternates):
            problems.append("also_acceptable_sources must be a non-empty list of slugs")
        else:
            problems += [
                f"also_acceptable_sources entry {slug!r} is not an article slug"
                for slug in alternates
                if slug not in slugs
            ]
            if source is None or source in alternates:
                problems.append(
                    "also_acceptable_sources needs an expected_source that it does not repeat"
                )
    return problems


def _check_evidence(
    row: Mapping[str, Any], articles: Mapping[str, str], catalogue: Sequence[str]
) -> list[str]:
    evidence = row.get("evidence")
    if not isinstance(evidence, list):
        return ["evidence is not a list"]
    problems: list[str] = []
    for position, entry in enumerate(evidence):
        if (
            not isinstance(entry, dict)
            or entry.keys() != {"source", "quote"}
            or not all(_is_text(value) for value in entry.values())
        ):
            problems.append(f"evidence[{position}] must have a non-empty source and quote")
    if problems:
        return problems

    expectations = row.get("expectations")
    facts = (expectations.get("expected_facts") if isinstance(expectations, dict) else None) or []
    if row.get("stratum") == "unanswerable":
        entry = evidence[0] if len(evidence) == 1 else {}
        searched = str(entry.get("quote", ""))
        if (
            entry.get("source") != NO_SOURCE
            or not searched.startswith(SEARCHED_PREFIX)
            or not searched[len(SEARCHED_PREFIX) :].strip()
        ):
            problems.append(
                'unanswerable rows need one evidence entry: source "none" and a quote '
                f'that starts "{SEARCHED_PREFIX}"'
            )
        return problems

    if len(evidence) != len(facts):
        problems.append(f"{len(facts)} expected facts but {len(evidence)} evidence entries")
    for position, entry in enumerate(evidence):
        source, quote = entry["source"], entry["quote"]
        if source != CATALOGUE_SOURCE and source not in articles:
            problems.append(f"evidence[{position}] source {source!r} is not an article or 'plans'")
        elif not quote_in_source(source, quote, articles, catalogue):
            problems.append(f"evidence[{position}] quote is not verbatim in {source!r}: {quote!r}")
    return problems


def _check_stratum(row: Mapping[str, Any]) -> list[str]:
    stratum = row.get("stratum")
    expectations = row.get("expectations")
    if not isinstance(expectations, dict):
        return []
    problems: list[str] = []
    facts = expectations.get("expected_facts")
    guidelines = expectations.get("guidelines") or []
    if stratum in FACT_STRATA:
        if not facts:
            problems.append(f"{stratum} rows need expected_facts")
        if "expected_source" not in expectations:
            problems.append(f"{stratum} rows need an expected_source")
    else:
        if facts:
            problems.append(f"{stratum} rows have no expected_facts")
        if "expected_source" in expectations:
            problems.append(f"{stratum} rows have no expected_source")
        if not guidelines:
            problems.append(f"{stratum} rows need guidelines")
    if (stratum == "hand_off") != (expectations.get("should_escalate") is True):
        problems.append("should_escalate must be true on hand_off rows and false on the others")
    if stratum == "hand_off" and expectations.get("expected_tool") != "escalate_to_human":
        problems.append("hand_off rows expect the tool escalate_to_human")
    if stratum == "multi_hop":
        evidence = row.get("evidence")
        sources = (
            {entry.get("source") for entry in evidence if isinstance(entry, dict)}
            if isinstance(evidence, list)
            else set()
        )
        if len(sources) < 2:
            problems.append("multi_hop rows need evidence from at least two sources")
    if stratum == "pii_in_question":
        inputs = row.get("inputs")
        question = str(inputs.get("question", "")) if isinstance(inputs, dict) else ""
        details = personal_details(question)
        if not details:
            problems.append("pii_in_question rows need a phone number, email or card digits")
        if not any("must not repeat" in str(guideline) for guideline in guidelines):
            problems.append('pii_in_question rows need a "must not repeat" guideline')
        problems += [
            f"a guideline repeats personal data from the question: {detail!r}"
            for detail in sorted(details)
            if any(detail in str(guideline) for guideline in guidelines)
        ]
    return problems


def check_row(
    row: Mapping[str, Any], articles: Mapping[str, str], catalogue: Sequence[str]
) -> list[str]:
    """Every problem with one row, as plain sentences. An empty list means the row is fine."""
    problems = [f"missing key {key!r}" for key in sorted(ROW_KEYS - row.keys())]
    problems += [f"unknown key {key!r}" for key in sorted(row.keys() - ROW_KEYS)]
    if problems:
        return problems

    match = _ID.fullmatch(str(row["id"]))
    if not match or int(match.group(1)) < FIRST_NEW_ID:
        problems.append(f"id must be E{FIRST_NEW_ID} or higher, written as E and digits")
    if row["category"] not in CATEGORIES:
        problems.append(f"category {row['category']!r} is not one of {sorted(CATEGORIES)}")
    if not isinstance(row["reviewed"], bool):
        problems.append("reviewed must be true or false")
    if row["stratum"] not in MIN_COUNTS:
        problems.append(f"stratum {row['stratum']!r} is not one of {sorted(MIN_COUNTS)}")
    problems += _check_inputs(row["inputs"], row["stratum"])
    problems += _check_expectations(row["expectations"], articles)
    problems += _check_evidence(row, articles, catalogue)
    problems += _check_stratum(row)
    return problems


def check_set(
    rows: Sequence[Mapping[str, Any]],
    base_rows: Sequence[Mapping[str, Any]],
    articles: Mapping[str, str],
    catalogue: Sequence[str],
) -> list[str]:
    """Every problem in the set: each row, the ids, repeated questions and the counts."""
    problems: list[str] = []
    seen_ids = Counter(str(row.get("id")) for row in rows)
    base_ids = {str(row.get("id")) for row in base_rows}
    asked: dict[str, str] = {
        question_key(row): f"{row.get('id')} in the base set" for row in base_rows
    }
    for row in rows:
        row_id = str(row.get("id"))
        problems += [f"{row_id}: {problem}" for problem in check_row(row, articles, catalogue)]
        if seen_ids[row_id] > 1:
            problems.append(f"{row_id}: id is used {seen_ids[row_id]} times")
        if row_id in base_ids:
            problems.append(f"{row_id}: id is already used in the base set")
        key = question_key(row)
        if key and key in asked:
            problems.append(f"{row_id}: same question as {asked[key]}")
        asked.setdefault(key, row_id)

    counts = Counter(str(row.get("stratum")) for row in rows)
    problems += [
        f"stratum {stratum}: {counts[stratum]} rows, need at least {minimum}"
        for stratum, minimum in MIN_COUNTS.items()
        if counts[stratum] < minimum
    ]
    return problems


def summary(rows: Sequence[Mapping[str, Any]]) -> str:
    """Row counts per stratum and the number of distinct articles the rows rest on."""
    counts = Counter(str(row.get("stratum")) for row in rows)
    expected: set[str] = set()
    quoted: set[str] = set()
    for row in rows:
        expectations = row.get("expectations")
        if isinstance(expectations, dict) and expectations.get("expected_source"):
            expected.add(str(expectations["expected_source"]))
        evidence = row.get("evidence")
        for entry in evidence if isinstance(evidence, list) else []:
            if isinstance(entry, dict) and entry.get("source") not in {CATALOGUE_SOURCE, NO_SOURCE}:
                quoted.add(str(entry.get("source")))
    lines = [f"{len(rows)} rows"]
    lines += [f"  {stratum}: {counts[stratum]}" for stratum in MIN_COUNTS]
    lines.append(f"distinct articles named as expected_source: {len(expected)}")
    lines.append(f"distinct articles quoted as evidence: {len(quoted)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point. Returns 0 when the set is sound and 1 when it is not."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--path", type=Path, default=EXTENDED_SET, help="the set to check")
    parser.add_argument("--base", type=Path, default=BASE_SET, help="the set whose ids are taken")
    parser.add_argument("--articles", type=Path, default=ARTICLES, help="the help articles")
    args = parser.parse_args(argv)

    rows, problems = read_rows(args.path)
    base_rows, _ = read_rows(args.base)
    problems += check_set(rows, base_rows, load_articles(args.articles), catalogue_rows())
    print(summary(rows))
    if problems:
        print(f"\n{len(problems)} problems:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("OK: every row is well formed and every evidence quote was found in its source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
