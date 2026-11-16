"""Measure the check on figures: how often it catches a changed one, and how often it is wrong.

Usage:
    python -m eval.claim_check_eval --collect      ask the live copilot and save its answers
    python -m eval.claim_check_eval                measure on the saved answers
    python -m eval.claim_check_eval --save         measure and write a result file

``--collect`` asks the live copilot the evaluation questions and saves each
answer with the evidence it was written from, as ``eval/data/claim_corpus.json``.
That is the only step that calls a model. It refuses to run from a dirty tree.

The measurement makes no model call and is the same every time:

- **False alarms.** The check is run on the answers as the copilot wrote them.
  Every figure it reports is listed, because a person has to read each one to
  say whether the copilot stated something it was not given or the check
  misread a correct figure.
- **Catch rate.** Each figure the check accepts is changed to a different value
  (a price to another price, a phone number to another number) and the check
  is run again. A changed figure it does not report is a miss. The usual reason
  for a miss is that the new value also appears somewhere in the evidence: the
  check tests presence, not which fact a figure belongs to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from copilot.claims import Claim, Evidence, extract_claims, unsupported_claims
from eval.redaction_eval import _git
from eval.stats import wilson_interval

CORPUS = Path("eval/data/claim_corpus.json")
EVAL_SET = Path("eval/eval_set.jsonl")
RESULTS_DIR = Path("eval/results")
SEED = 20261115
# How many changed versions are made of each figure.
VARIANTS = 3
# Rows that get a fixed reply written by code, which the check does not read.
FIXED_REPLY_CATEGORIES = frozenset({"escalation"})
# Further questions, so the measurement does not rest on the evaluation set alone.
EXTRA_QUESTIONS: tuple[str, ...] = (
    "How do I request a waiver?",
    "Can you show me the rules for international roaming?",
    "This customer forgot their voicemail PIN. How do they reset it?",
    "How do I set up AutoPay, and is there a discount for it?",
    "What does it cost to add a line?",
    "How much hotspot data does each plan include?",
    "What number does a customer call to report a lost phone?",
    "How long does a number transfer take?",
)

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --- changing a figure ----------------------------------------------------------------------


def _changed_number(written: str, rng: random.Random) -> str:
    """Another number in the same form: whole stays whole, cents stay cents."""
    value = Decimal(written.replace(",", ""))
    if "." in written:
        places = len(written.split(".", 1)[1])
        step = Decimal(rng.choice(["0.5", "1", "2.5", "3", "5", "10"]))
        changed = value + step if rng.random() < 0.7 or value <= step else value - step
        return f"{changed:.{places}f}"
    step = Decimal(rng.choice([1, 2, 3, 5, 10, 15]))
    changed = value + step if rng.random() < 0.7 or value <= step else value - step
    return str(int(changed))


def changed_text(claim: Claim, rng: random.Random) -> str | None:
    """The claim's text with its value changed, or None if it cannot be changed."""
    if claim.kind == "url":
        address = claim.text.rstrip(".,;:!?)")
        tail = claim.text[len(address) :]
        if "/" in address.split("//")[-1]:
            return (
                address.rsplit("/", 1)[0] + "/" + rng.choice(["help-2", "contact", "claims"]) + tail
            )
        return address + "/" + rng.choice(["help-2", "contact", "claims"]) + tail
    if claim.kind == "phone":
        # Change the last digit that is not already the replacement.
        for position in range(len(claim.text) - 1, -1, -1):
            if claim.text[position].isdigit():
                digit = str((int(claim.text[position]) + rng.randint(1, 8)) % 10)
                return claim.text[:position] + digit + claim.text[position + 1 :]
        return None
    if claim.kind == "code":
        return str(int(claim.text) + rng.choice([100, 200, 11]))
    match = _NUMBER_RE.search(claim.text)
    if not match:
        return None
    return (
        claim.text[: match.start()]
        + _changed_number(match.group(0), rng)
        + claim.text[match.end() :]
    )


def mutants(answer: str, evidence: Sequence[str], rng: random.Random) -> list[dict[str, Any]]:
    """Versions of ``answer`` with one accepted figure changed in each."""
    index = Evidence(evidence)
    made: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for claim in extract_claims(answer):
        if claim.key in seen or not index.supports(claim):
            continue
        seen.add(claim.key)
        tried: set[str] = set()
        for _ in range(VARIANTS):
            replacement = changed_text(claim, rng)
            if replacement is None or replacement == claim.text or replacement in tried:
                continue
            tried.add(replacement)
            changed = answer[: claim.start] + replacement + answer[claim.end :]
            new_claims = [
                item
                for item in extract_claims(changed)
                if item.start == claim.start and item.kind == claim.kind
            ]
            if not new_claims or new_claims[0].key == claim.key:
                continue
            reported = {item.key for item in unsupported_claims(changed, evidence)}
            made.append(
                {
                    "kind": claim.kind,
                    "from": claim.text,
                    "to": replacement,
                    "caught": new_claims[0].key in reported,
                }
            )
    return made


# --- the measurement --------------------------------------------------------------------------


def _rate(passed: int, scored: int) -> dict[str, Any]:
    if scored == 0:
        return {"count": 0, "of": 0, "rate": None, "ci95": None}
    return {
        "count": passed,
        "of": scored,
        "rate": passed / scored,
        "ci95": list(wilson_interval(passed, scored)),
    }


def measure(corpus: Mapping[str, Any]) -> dict[str, Any]:
    """Run the check on every saved answer and on every changed version of it."""
    rng = random.Random(SEED)  # noqa: S311 - a fixed seed for a repeatable test, not security
    sources: Mapping[str, str] = corpus["sources"]
    figures = 0
    reported_figures: list[dict[str, Any]] = []
    answers_with_report = 0
    answers_with_figures = 0
    by_kind: dict[str, list[bool]] = defaultdict(list)
    misses: list[dict[str, Any]] = []
    for row in corpus["rows"]:
        evidence = [sources[key] for key in row["evidence"]]
        distinct = {claim.key for claim in extract_claims(row["answer"])}
        figures += len(distinct)
        answers_with_figures += bool(distinct)
        reported = unsupported_claims(row["answer"], evidence)
        answers_with_report += bool(reported)
        reported_figures.extend(
            {"id": row["id"], "kind": claim.kind, "figure": claim.text} for claim in reported
        )
        for mutant in mutants(row["answer"], evidence, rng):
            by_kind[mutant["kind"]].append(mutant["caught"])
            if not mutant["caught"]:
                misses.append({"id": row["id"], **mutant})
    every = [caught for outcomes in by_kind.values() for caught in outcomes]
    return {
        "answers": len(corpus["rows"]),
        "answers_with_a_figure": answers_with_figures,
        "figures_in_real_answers": figures,
        "reported_in_real_answers": _rate(len(reported_figures), figures),
        "real_answers_with_a_report": _rate(answers_with_report, len(corpus["rows"])),
        "reported_figures": reported_figures,
        "changed_figures_caught": _rate(sum(every), len(every)),
        "caught_by_kind": {
            kind: _rate(sum(outcomes), len(outcomes)) for kind, outcomes in sorted(by_kind.items())
        },
        "missed": misses,
    }


def _line(label: str, rate: Mapping[str, Any]) -> str:
    if rate["rate"] is None:
        return f"  {label}: none"
    low, high = rate["ci95"]
    return (
        f"  {label}: {rate['count']}/{rate['of']} "
        f"({rate['rate']:.1%}, 95% interval {low:.0%} to {high:.0%})"
    )


def print_report(result: Mapping[str, Any]) -> None:
    """Print the measurement for a person to read."""
    print(f"answers: {result['answers']} ({result['answers_with_a_figure']} state a figure)")
    print(f"distinct figures in them: {result['figures_in_real_answers']}")
    print("on the answers as written (each one needs reading by hand):")
    print(_line("figures reported", result["reported_in_real_answers"]))
    print(_line("answers with a report", result["real_answers_with_a_report"]))
    for item in result["reported_figures"]:
        print(f"    {item['id']}: {item['kind']} {item['figure']!r}")
    print("on answers with one figure changed:")
    print(_line("caught", result["changed_figures_caught"]))
    for kind, rate in result["caught_by_kind"].items():
        print(_line(f"  {kind}", rate))
    kinds = Counter(item["kind"] for item in result["missed"])
    if kinds:
        print(f"  missed, by kind: {dict(kinds)}")
        for item in result["missed"][:12]:
            print(f"    {item['id']}: {item['from']!r} -> {item['to']!r}")


# --- collecting the answers -------------------------------------------------------------------


def collect() -> None:
    """Ask the live copilot the questions and save each answer with its evidence."""
    dirty = _git("status", "--porcelain", "--", ".", f":(exclude){CORPUS.as_posix()}")
    if dirty:
        print("not started: commit first, so the corpus names the code that made it")
        raise SystemExit(1)

    # Imported here so that measuring, and the tests, do not load the model stack.
    import mlflow
    from dotenv import load_dotenv

    from copilot.agent import Copilot
    from copilot.config import load_settings
    from copilot.prompts import PROMPT_VERSION

    load_dotenv()
    settings = load_settings().model_copy(update={"record_escalations": False})
    mlflow.tracing.disable()
    copilot = Copilot(settings)

    questions: list[tuple[str, str]] = []
    for line in EVAL_SET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["category"] not in FIXED_REPLY_CATEGORIES:
                questions.append((row["id"], row["inputs"]["question"]))
    questions += [(f"X{number:03d}", text) for number, text in enumerate(EXTRA_QUESTIONS, 1)]

    sources: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for number, (row_id, question) in enumerate(questions, start=1):
        answer = copilot.run(question)
        keys = []
        for text in answer.evidence:
            sources.setdefault(_digest(text), text)
            keys.append(_digest(text))
        rows.append(
            {
                "id": row_id,
                # The question as processed: personal details are already replaced.
                "question": answer.question_as_processed,
                "answer": answer.answer,
                "tools_used": answer.tools_used,
                "flags": answer.guardrail_flags,
                "evidence": keys,
            }
        )
        print(f"  {number}/{len(questions)} {row_id}", flush=True)
    corpus = {
        "collected_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git("rev-parse", "HEAD"),
        "prompt_version": PROMPT_VERSION,
        "llm_endpoint": settings.llm_endpoint,
        "chunk_config": settings.chunk_config,
        "query_type": settings.query_type,
        "rows": rows,
        "sources": sources,
    }
    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text(json.dumps(corpus, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {CORPUS.as_posix()}: {len(rows)} answers, {len(sources)} pieces of evidence")


def main(argv: list[str] | None = None) -> None:
    """Collect the answers, or measure the check on the saved ones."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--collect", action="store_true", help="ask the live copilot and save")
    parser.add_argument("--save", action="store_true", help="write a result file")
    args = parser.parse_args(argv)
    if args.collect:
        collect()
        return
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    result = measure(corpus)
    print_report(result)
    if args.save:
        report = {
            "measured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_sha": _git("rev-parse", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results")),
            "corpus": {
                "file": CORPUS.as_posix(),
                "sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
                "collected_at": corpus["collected_at"],
                "git_sha": corpus["git_sha"],
                "prompt_version": corpus["prompt_version"],
                "llm_endpoint": corpus["llm_endpoint"],
            },
            "seed": SEED,
            "variants_per_figure": VARIANTS,
            **result,
        }
        if report["git_dirty"]:
            print("not saved: the working tree has uncommitted changes")
            raise SystemExit(1)
        path = RESULTS_DIR / f"claim_check_{report['measured_at'][:10]}.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"saved {path.as_posix()}")


if __name__ == "__main__":
    main()
