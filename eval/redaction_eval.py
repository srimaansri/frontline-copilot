"""Measure the redactor against the labeled synthetic transcripts.

Usage:
    python -m eval.redaction_eval                      # test set, print only
    python -m eval.redaction_eval --save --tag test    # also write eval/results/
    python -m eval.redaction_eval --data-dir data/raw/dev --show-errors
    python -m eval.redaction_eval --challenge --save --tag challenge

Three sets, in increasing order of how much the number can be trusted:

* dev (``data/raw/dev``, seed 7): recognizers are tuned on this set.
* test (``data/raw``, seed 42, transcripts T0001-T0030): never used for tuning,
  but built from the same templates as dev, so it measures new names and
  numbers in familiar phrasings.
* challenge (``eval/data/redaction_challenge.txt``): hand-written phrasings the
  templates do not contain. Never used for tuning.

``--show-errors`` prints the text of each turn with an error. Use it only on
synthetic data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from copilot.redaction import (
    CPNI_ENTITY_TYPES,
    DEFAULT_SPACY_MODEL,
    PII_ENTITY_TYPES,
    Redactor,
)
from copilot.span_metrics import (
    Counts,
    Span,
    char_coverage,
    match_spans,
    merge_counts,
    micro_total,
)

DEFAULT_DATA_DIR = Path("data/raw")
CHALLENGE_FILE = Path("eval/data/redaction_challenge.txt")
RESULTS_DIR = Path("eval/results")
MIN_OVERLAP = 0.5

_MARKUP_RE = re.compile(r"\[\[([A-Z0-9_]+)\|(.+?)\]\]")
_TURN_SEPARATOR = " || "


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def parse_marked_turn(marked: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Strip ``[[TYPE|text]]`` markup and return the plain text with its spans."""
    parts: list[str] = []
    spans: list[tuple[int, int, str]] = []
    position = 0
    cursor = 0
    for match in _MARKUP_RE.finditer(marked):
        literal = marked[cursor : match.start()]
        parts.append(literal)
        position += len(literal)
        entity_type, value = match.group(1), match.group(2)
        spans.append((position, position + len(value), entity_type))
        parts.append(value)
        position += len(value)
        cursor = match.end()
    parts.append(marked[cursor:])
    return "".join(parts), spans


def load_challenge(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the challenge file into the same shape as the generated data."""
    transcripts: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for number, line in enumerate(lines, start=1):
        transcript_id = f"C{number:04d}"
        turns: list[dict[str, str]] = []
        for turn_index, marked in enumerate(line.split(_TURN_SEPARATOR)):
            text, spans = parse_marked_turn(marked)
            turns.append({"speaker": "customer", "text": text})
            labels.extend(
                {
                    "transcript_id": transcript_id,
                    "turn_index": turn_index,
                    "start": start,
                    "end": end,
                    "entity_type": entity_type,
                    "text": text[start:end],
                }
                for start, end, entity_type in spans
            )
        transcripts.append({"transcript_id": transcript_id, "turns": turns})
    return transcripts, labels


def _counts_dict(counts: Counts) -> dict[str, Any]:
    return {
        "support": counts.support,
        "tp": counts.tp,
        "fp": counts.fp,
        "fn": counts.fn,
        "precision": counts.precision,
        "recall": counts.recall,
        "f1": counts.f1,
    }


def evaluate(
    transcripts: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
    redactor: Redactor,
    *,
    collect_errors: bool = False,
    score_all: bool = False,
) -> dict[str, Any]:
    """Run the redactor over the labeled transcripts and score it.

    By default only transcripts that have at least one label are scored, which
    is right for the generated data (labels exist for the first N only). With
    ``score_all`` every transcript is scored, so a transcript with no labels
    counts as a negative.

    Returns a JSON-serialisable report. ``errors`` (only with ``collect_errors``)
    contains raw text and must not be saved.
    """
    gold_by_turn: dict[tuple[str, int], list[Span]] = defaultdict(list)
    for label in labels:
        gold_by_turn[(label["transcript_id"], label["turn_index"])].append(
            Span(label["start"], label["end"], label["entity_type"])
        )
    labeled_ids = {label["transcript_id"] for label in labels}
    if score_all:
        labeled_ids = {transcript["transcript_id"] for transcript in transcripts}

    strict_parts: list[dict[str, Counts]] = []
    any_type_parts: list[dict[str, Counts]] = []
    coverage = {"pii": [0, 0], "cpni": [0, 0]}
    errors: list[str] = []
    turn_count = 0

    for transcript in transcripts:
        transcript_id = transcript["transcript_id"]
        if transcript_id not in labeled_ids:
            continue
        texts = [turn["text"] for turn in transcript["turns"]]
        for turn_index, result in enumerate(redactor.redact_turns(texts)):
            turn_count += 1
            gold = gold_by_turn.get((transcript_id, turn_index), [])
            predicted = [Span(e.start, e.end, e.entity_type) for e in result.entities]
            strict = match_spans(gold, predicted, min_overlap=MIN_OVERLAP)
            strict_parts.append(strict)
            any_type_parts.append(
                match_spans(gold, predicted, min_overlap=MIN_OVERLAP, type_aware=False)
            )
            for group, types in (("pii", PII_ENTITY_TYPES), ("cpni", CPNI_ENTITY_TYPES)):
                covered, total = char_coverage(
                    [span for span in gold if span.entity_type in types], predicted
                )
                coverage[group][0] += covered
                coverage[group][1] += total
            if collect_errors and any(c.fp or c.fn for c in strict.values()):
                text = texts[turn_index]
                gold_view = [(s.entity_type, text[s.start : s.end]) for s in gold]
                predicted_view = [(s.entity_type, text[s.start : s.end]) for s in predicted]
                errors.append(
                    f"{transcript_id}[{turn_index}] {text!r}\n"
                    f"    gold={gold_view}\n    pred={predicted_view}"
                )

    strict_total = merge_counts(strict_parts)
    any_type_total = merge_counts(any_type_parts)
    report: dict[str, Any] = {
        "transcripts": len(labeled_ids),
        "turns": turn_count,
        "labels": len(labels),
        "min_overlap_iou": MIN_OVERLAP,
        "per_entity": {
            entity_type: _counts_dict(strict_total.get(entity_type, Counts()))
            for entity_type in (*PII_ENTITY_TYPES, *CPNI_ENTITY_TYPES)
        },
        "overall_pii": _counts_dict(micro_total(strict_total, PII_ENTITY_TYPES)),
        "overall_cpni": _counts_dict(micro_total(strict_total, CPNI_ENTITY_TYPES)),
        # A value counts as masked when any detection overlaps it, whatever its type.
        "masked_recall_any_type": {
            "pii": micro_total(any_type_total, PII_ENTITY_TYPES).recall,
            "cpni": micro_total(any_type_total, CPNI_ENTITY_TYPES).recall,
        },
        "char_coverage": {
            group: {
                "covered": covered,
                "total": total,
                "rate": covered / total if total else None,
            }
            for group, (covered, total) in coverage.items()
        },
    }
    if collect_errors:
        report["errors"] = errors
    return report


def _fmt(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.3f}"


def format_report(report: Mapping[str, Any]) -> str:
    """Render the report as a plain-text table. Contains no transcript text."""
    lines = [
        f"{report['transcripts']} transcripts, {report['turns']} turns, "
        f"{report['labels']} labeled values (match: IoU >= {report['min_overlap_iou']}, same type)",
        "",
        f"{'entity':<16}{'n':>5}{'tp':>5}{'fp':>5}{'fn':>5}{'prec':>8}{'recall':>8}{'f1':>8}",
    ]
    rows = [
        *report["per_entity"].items(),
        ("PII overall", report["overall_pii"]),
        ("CPNI overall", report["overall_cpni"]),
    ]
    for name, row in rows:
        if name == "PII overall":
            lines.append("-" * 60)
        lines.append(
            f"{name:<16}{row['support']:>5}{row['tp']:>5}{row['fp']:>5}{row['fn']:>5}"
            f"{_fmt(row['precision']):>8}{_fmt(row['recall']):>8}{_fmt(row['f1']):>8}"
        )
    masked = report["masked_recall_any_type"]
    cover = report["char_coverage"]
    lines += [
        "",
        f"masked by any detection (type ignored): PII {_fmt(masked['pii'])}   "
        f"CPNI {_fmt(masked['cpni'])}",
        f"labeled characters covered:             PII {_fmt(cover['pii']['rate'])}   "
        f"CPNI {_fmt(cover['cpni']['rate'])}",
    ]
    return "\n".join(lines)


def _git(*args: str) -> str:
    # Fixed argument list, no shell: nothing here comes from user or model input.
    completed = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance(data_files: Sequence[Path], spacy_model: str) -> dict[str, Any]:
    """Describe exactly what was measured: code version, data files and library versions."""
    return {
        "run_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git("rev-parse", "HEAD"),
        # Saved reports themselves do not make the code "dirty".
        "git_dirty": bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results")),
        "data_files": {path.as_posix(): _sha256(path) for path in data_files},
        "spacy_model": spacy_model,
        "versions": {
            "presidio-analyzer": version("presidio-analyzer"),
            "spacy": version("spacy"),
            spacy_model: version(spacy_model),
            "faker": version("faker"),
        },
    }


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    parser.add_argument("--save", action="store_true", help="write a JSON report to eval/results")
    parser.add_argument("--tag", default="", help="suffix for the saved file name")
    parser.add_argument("--show-errors", action="store_true", help="synthetic data only")
    parser.add_argument(
        "--challenge", action="store_true", help=f"score {CHALLENGE_FILE} instead of --data-dir"
    )
    args = parser.parse_args(argv)

    if args.challenge:
        data_files = [CHALLENGE_FILE]
        transcripts, labels = load_challenge(CHALLENGE_FILE)
    else:
        data_files = [args.data_dir / "transcripts.jsonl", args.data_dir / "pii_labels.jsonl"]
        transcripts, labels = _read_jsonl(data_files[0]), _read_jsonl(data_files[1])
    report = evaluate(
        transcripts,
        labels,
        Redactor(args.spacy_model),
        collect_errors=args.show_errors,
        score_all=args.challenge,
    )
    errors = report.pop("errors", [])
    print(format_report(report))
    if errors:
        print(f"\n{len(errors)} turns with at least one error:")
        print("\n".join(errors))

    if args.save:
        meta = provenance(data_files, args.spacy_model)
        if meta["git_dirty"]:
            print("\nnot saved: commit your changes first so the result has a clean git SHA")
            raise SystemExit(1)
        suffix = f"_{args.tag}" if args.tag else ""
        out_path = RESULTS_DIR / f"redaction_{meta['run_at'][:10]}{suffix}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({**meta, **report}, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"\nsaved {out_path}")


if __name__ == "__main__":
    main()
