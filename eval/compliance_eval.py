"""Measure the compliance checker on calls with seeded rule breaches.

Usage:
    python -m eval.compliance_eval                  # development half only
    python -m eval.compliance_eval --show-errors    # and print the calls it got wrong
    python -m eval.compliance_eval --held-out       # all three sets
    python -m eval.compliance_eval --held-out --save

Three sets, generated in memory from fixed seeds and redacted the way the
pipeline redacts them, so the checker only ever sees placeholders:

* development (``data_gen.synth_breaches``, first half): the rules in
  ``copilot.compliance`` are tuned on these calls. In-sample.
* held out (second half): the same kinds of call, built from wording written
  without sight of the rules. Not scored unless ``--held-out`` is given.
* clean (``data_gen.synth_transcripts --seed 42``, T0001 to T0200): calls in
  which no rule is broken. Any finding here is a false alarm. Also scored only
  with ``--held-out``, so the rules are not tuned on it either.

Scoring is per call and per rule: a rule is right on a call when it fires and
the call is labelled with that rule. Precision here depends on the mix of
calls, and breaches are far more common in the seeded sets than in real calls,
so read it together with the false-alarm rate on the clean calls.

The first saved result is a first-contact result. A later one, saved after a
rule was changed, says that it is not.

``--show-errors`` prints redacted synthetic text, for the development half only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from copilot.compliance import RULES, Finding, check_call
from copilot.redaction import DEFAULT_SPACY_MODEL, Redactor, get_redactor
from data_gen.breach_wording import DEV_WORDING, HELD_OUT_WORDING
from data_gen.plans import PLANS
from data_gen.synth_breaches import BREACH_SEED, CallLabel
from data_gen.synth_breaches import generate as generate_breaches
from data_gen.synth_transcripts import generate as generate_clean
from eval.redaction_eval import _git
from eval.stats import wilson_interval

RESULTS_DIR = Path("eval/results")
CLEAN_SEED = 42


def _rate(count: int, of: int) -> dict[str, Any]:
    if of == 0:
        return {"count": 0, "of": 0, "rate": None, "ci95": None}
    return {"count": count, "of": of, "rate": count / of, "ci95": list(wilson_interval(count, of))}


def redact_call(transcript: Mapping[str, Any], redactor: Redactor) -> list[dict[str, str]]:
    """The turns of one call with personal data replaced, as the checker expects them."""
    turns = transcript["turns"]
    redacted = redactor.redact_turns([turn["text"] for turn in turns])
    return [
        {"speaker": turn["speaker"], "text": result.text}
        for turn, result in zip(turns, redacted, strict=True)
    ]


def find_all(
    transcripts: Sequence[Mapping[str, Any]], redactor: Redactor
) -> dict[str, list[Finding]]:
    """Redact every call and run the checker on it."""
    return {
        transcript["transcript_id"]: check_call(redact_call(transcript, redactor))
        for transcript in transcripts
    }


def score(labels: Sequence[CallLabel], found: Mapping[str, Sequence[Finding]]) -> dict[str, Any]:
    """Precision and recall for each rule over one set of labelled calls.

    ``right_turn`` is, of the breaches a rule caught, how many it placed at the
    labelled turn.
    """
    rules_found = {
        label.transcript_id: {f.rule for f in found[label.transcript_id]} for label in labels
    }
    by_rule: dict[str, Any] = {}
    other_turn: list[dict[str, Any]] = []
    for rule in RULES:
        caught = [
            label
            for label in labels
            if label.rule == rule and rule in rules_found[label.transcript_id]
        ]
        breaches = sum(label.rule == rule for label in labels)
        fired = sum(rule in rules_found[label.transcript_id] for label in labels)
        for label in caught:
            first = next(f.turn_index for f in found[label.transcript_id] if f.rule == rule)
            if first != label.turn_index:
                other_turn.append(
                    {
                        "transcript_id": label.transcript_id,
                        "rule": rule,
                        "labelled_turn": label.turn_index,
                        "found_turn": first,
                    }
                )
        at_other_turn = sum(row["rule"] == rule for row in other_turn)
        by_rule[rule] = {
            "recall": _rate(len(caught), breaches),
            "precision": _rate(len(caught), fired),
            "right_turn": _rate(len(caught) - at_other_turn, len(caught)),
        }
    by_variant: dict[str, Any] = {}
    for variant in sorted({label.variant for label in labels}):
        chosen = [label for label in labels if label.variant == variant]
        right = sum(
            rules_found[label.transcript_id] == ({label.rule} if label.rule else set())
            for label in chosen
        )
        by_variant[variant] = _rate(right, len(chosen))
    wrong = [
        {
            "transcript_id": label.transcript_id,
            "variant": label.variant,
            "scenario": label.scenario,
            "wording": label.wording,
            "rule": label.rule,
            "found": sorted(rules_found[label.transcript_id]),
        }
        for label in labels
        if rules_found[label.transcript_id] != ({label.rule} if label.rule else set())
    ]
    return {
        "calls": len(labels),
        "breaches": sum(label.rule is not None for label in labels),
        "by_rule": by_rule,
        "right_by_variant": by_variant,
        "wrong": wrong,
        "caught_at_another_turn": other_turn,
    }


def false_alarms(found: Mapping[str, Sequence[Finding]]) -> dict[str, Any]:
    """How many calls of a set with no breach in it get at least one finding."""
    flagged = {call_id: findings for call_id, findings in found.items() if findings}
    by_rule = Counter(rule for findings in flagged.values() for rule in {f.rule for f in findings})
    return {
        "calls_flagged": _rate(len(flagged), len(found)),
        "by_rule": {rule: by_rule[rule] for rule in RULES},
        "flagged": {
            call_id: [{"rule": f.rule, "turn_index": f.turn_index} for f in findings]
            for call_id, findings in sorted(flagged.items())
        },
    }


def _line(label: str, rate: Mapping[str, Any]) -> str:
    if rate["rate"] is None:
        return f"{label}: none"
    low, high = rate["ci95"]
    return f"{label}: {rate['count']}/{rate['of']} ({rate['rate']:.0%}, {low:.0%}-{high:.0%})"


def format_scores(name: str, scores: Mapping[str, Any]) -> str:
    """One set's scores for a person to read. Contains no transcript text."""
    lines = [f"\n{name}: {scores['calls']} calls, {scores['breaches']} with a breach"]
    for rule, both in scores["by_rule"].items():
        lines.append(f"  {rule}")
        lines.append("    " + _line("recall", both["recall"]))
        lines.append("    " + _line("precision", both["precision"]))
        lines.append("    " + _line("at the labelled turn", both["right_turn"]))
    lines.append("  calls judged exactly right, by kind of call")
    lines += ["    " + _line(variant, rate) for variant, rate in scores["right_by_variant"].items()]
    for row in scores["wrong"]:
        lines.append(
            f"  wrong: {row['transcript_id']} {row['variant']} on {row['scenario']}"
            f" ({row['wording'] or 'no wording entry'}): found {row['found'] or 'nothing'}"
        )
    for row in scores["caught_at_another_turn"]:
        lines.append(
            f"  other turn: {row['transcript_id']} {row['rule']}: labelled turn "
            f"{row['labelled_turn']}, found at {row['found_turn']}"
        )
    return "\n".join(lines)


def format_false_alarms(result: Mapping[str, Any]) -> str:
    """The false-alarm figures for a person to read."""
    lines = ["\n" + _line("clean calls (seed 42) with any finding", result["calls_flagged"])]
    lines += [f"  {rule}: {count}" for rule, count in result["by_rule"].items() if count]
    lines += [
        f"  flagged: {call_id} {[item['rule'] for item in findings]}"
        for call_id, findings in result["flagged"].items()
    ]
    return "\n".join(lines)


def _jsonl_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    """The hash of the rows as ``data_gen`` writes them to a ``.jsonl`` file."""
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _predictions(found: Mapping[str, Sequence[Finding]]) -> dict[str, list[dict[str, Any]]]:
    return {
        call_id: [{"rule": f.rule, "turn_index": f.turn_index} for f in findings]
        for call_id, findings in found.items()
    }


def _show_errors(
    scores: Mapping[str, Any],
    transcripts: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, CallLabel],
    found: Mapping[str, Sequence[Finding]],
    redactor: Redactor,
) -> None:
    for row in [*scores["wrong"], *scores["caught_at_another_turn"]]:
        call_id = row["transcript_id"]
        label = labels[call_id]
        print(f"\n{call_id} {label.variant}: labelled {label.rule} at turn {label.turn_index}")
        for finding in found[call_id]:
            print(f"  found {finding.rule} at turn {finding.turn_index}")
        for index, turn in enumerate(redact_call(transcripts[call_id], redactor)):
            print(f"  {index:>2} {turn['speaker']:<8} {turn['text']}")


def main(argv: list[str] | None = None) -> None:
    """Score the checker and optionally save the result."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--held-out", action="store_true", help="also score the held-out half")
    parser.add_argument("--save", action="store_true", help="write a result file")
    parser.add_argument("--tag", default="", help="suffix for the saved file name")
    parser.add_argument("--show-errors", action="store_true", help="development half only")
    parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    args = parser.parse_args(argv)
    if args.save and not args.held_out:
        parser.error("--save records all three sets, so it needs --held-out")
    dirty = bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results"))
    if args.save and dirty:
        print("not started: commit first, so the result names the code that made it")
        raise SystemExit(1)

    # The same allow-list as the pipeline, so plan names survive redaction.
    redactor = get_redactor(args.spacy_model, tuple(row.name for row in PLANS))
    transcripts, labels = generate_breaches(BREACH_SEED)
    by_id = {transcript["transcript_id"]: transcript for transcript in transcripts}

    def run(split: str) -> tuple[dict[str, Any], dict[str, list[Finding]]]:
        chosen = [label for label in labels if label.split == split]
        found = find_all([by_id[label.transcript_id] for label in chosen], redactor)
        return score(chosen, found), found

    dev_scores, dev_found = run("dev")
    print(format_scores("development half (the rules were tuned on it)", dev_scores))
    if args.show_errors:
        label_by_id = {label.transcript_id: label for label in labels}
        _show_errors(dev_scores, by_id, label_by_id, dev_found, redactor)
    if not args.held_out:
        return

    held_scores, held_found = run("held_out")
    print(format_scores("held-out half", held_scores))
    clean, _ = generate_clean(CLEAN_SEED)
    clean_found = find_all(clean, redactor)
    clean_result = false_alarms(clean_found)
    print(format_false_alarms(clean_result))
    if not args.save:
        return

    earlier = sorted(path.name for path in RESULTS_DIR.glob("compliance_*.json"))
    report = {
        "scored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git("rev-parse", "HEAD"),
        # False once any result has been saved: the held-out half has been seen.
        "first_contact": not earlier,
        "earlier_results": earlier,
        "spacy_model": args.spacy_model,
        "versions": {
            "presidio-analyzer": version("presidio-analyzer"),
            "spacy": version("spacy"),
            args.spacy_model: version(args.spacy_model),
            "faker": version("faker"),
        },
        "breach_seed": BREACH_SEED,
        "clean_seed": CLEAN_SEED,
        "data_sha256": {
            "breach_transcripts": _jsonl_sha256(transcripts),
            "breach_labels": _jsonl_sha256([asdict(label) for label in labels]),
            "clean_transcripts": _jsonl_sha256(clean),
            DEV_WORDING.name: hashlib.sha256(DEV_WORDING.read_bytes()).hexdigest(),
            HELD_OUT_WORDING.name: hashlib.sha256(HELD_OUT_WORDING.read_bytes()).hexdigest(),
        },
        "dev": dev_scores,
        "held_out": held_scores,
        "clean": clean_result,
        "predictions": {**_predictions(dev_found), **_predictions(held_found)},
    }
    suffix = f"_{args.tag}" if args.tag else ""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"compliance_{report['scored_at'][:10]}{suffix}.json"
    if path.exists():
        print(f"not saved: {path.as_posix()} exists; give a --tag so it is kept")
        raise SystemExit(1)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"saved {path.as_posix()}")


if __name__ == "__main__":
    main()
