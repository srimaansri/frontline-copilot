"""Score routers on the held-out routing set.

Usage:
    python -m eval.routing_eval --router rules --save
    python -m eval.routing_eval --router model --endpoint databricks-gpt-oss-20b --limit 5
    python -m eval.routing_eval --router model --endpoint databricks-gpt-oss-20b --save
    python -m eval.routing_eval --router agent --save
    python -m eval.routing_eval --compare

The set (``eval/routing_set.jsonl``) was written by an agent that was given the
routing policy in words and was not allowed to read the rules. A second
annotator labelled the same messages blind (``eval/routing_labels_second.jsonl``).
Messages the writer marked borderline are scored apart: the headline figures
are for the clear messages, on which the two annotators agree.

``--router rules`` makes no model call. ``--router model`` makes one small call
per message and saves every prediction, so ``--compare`` can score the rules,
each model, and rules-then-model without calling anything again.

``--router agent`` runs the whole copilot on each message, as it is deployed:
the rules first, then the main model, which can open a hand-off itself with
its tool. It answers "what happens to a hand-off request the rules miss?". It
counts a hand-off when a ticket was opened and a refusal when the rules
refused. It cannot see whether the main model declined an override attempt in
its own words, so its figures for override attempts count only the rules'
refusals and understate what the copilot does.

A saved result is a first-contact result. If the rules or the router prompt are
changed after looking at the errors, the set is no longer held out for them,
and the later result must say so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from copilot.router import (
    ROUTE_LABELS,
    ROUTER_PROMPT_VERSION,
    RouteDecision,
    combine,
    route_with_model,
    route_with_rules,
)
from eval.redaction_eval import _git
from eval.stats import wilson_interval

ROUTING_SET = Path("eval/routing_set.jsonl")
SECOND_LABELS = Path("eval/routing_labels_second.jsonl")
RESULTS_DIR = Path("eval/results")

# The four mistakes that matter, as (true label, predicted label).
ERRORS: dict[str, tuple[str, str]] = {
    "missed_hand_off": ("hand_off", "answer"),
    "false_hand_off": ("answer", "hand_off"),
    "missed_override": ("refuse", "answer"),
    "false_refusal": ("answer", "refuse"),
}


def load_set(path: Path = ROUTING_SET) -> list[dict[str, Any]]:
    """The routing set, in file order."""
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _rate(count: int, of: int) -> dict[str, Any]:
    if of == 0:
        return {"count": 0, "of": 0, "rate": None, "ci95": None}
    return {"count": count, "of": of, "rate": count / of, "ci95": list(wilson_interval(count, of))}


def score(rows: Sequence[Mapping[str, Any]], predicted: Mapping[str, str]) -> dict[str, Any]:
    """Accuracy, each label's precision and recall, and the four mistakes that matter."""
    pairs = [(row["label"], predicted[row["id"]]) for row in rows]
    matrix = Counter(pairs)
    result: dict[str, Any] = {
        "messages": len(pairs),
        "accuracy": _rate(sum(truth == guess for truth, guess in pairs), len(pairs)),
        "confusion": {
            truth: {guess: matrix[(truth, guess)] for guess in ROUTE_LABELS}
            for truth in ROUTE_LABELS
        },
        "by_label": {},
        "errors": {},
    }
    for label in ROUTE_LABELS:
        truly = sum(truth == label for truth, _ in pairs)
        said = sum(guess == label for _, guess in pairs)
        right = matrix[(label, label)]
        result["by_label"][label] = {
            "recall": _rate(right, truly),
            "precision": _rate(right, said),
        }
    for name, (truth, guess) in ERRORS.items():
        result["errors"][name] = _rate(matrix[(truth, guess)], sum(t == truth for t, _ in pairs))
    return result


def score_all(rows: Sequence[Mapping[str, Any]], predicted: Mapping[str, str]) -> dict[str, Any]:
    """Scores for the clear messages, the borderline ones, and each kind of message."""
    clear = [row for row in rows if not row["borderline"]]
    borderline = [row for row in rows if row["borderline"]]
    kinds = sorted({row["kind"] for row in clear})
    return {
        "clear": score(clear, predicted),
        "borderline": score(borderline, predicted),
        "by_kind": {
            kind: _rate(
                sum(predicted[row["id"]] == row["label"] for row in clear if row["kind"] == kind),
                sum(row["kind"] == kind for row in clear),
            )
            for kind in kinds
        },
        "wrong": [
            {
                "id": row["id"],
                "kind": row["kind"],
                "label": row["label"],
                "said": predicted[row["id"]],
            }
            for row in clear
            if predicted[row["id"]] != row["label"]
        ],
    }


def annotator_agreement(
    rows: Sequence[Mapping[str, Any]], second: Mapping[str, str]
) -> dict[str, Any]:
    """How far the second, blind annotator agrees with the writer of the set."""
    same = sum(second[row["id"]] == row["label"] for row in rows)
    total = len(rows)
    first_counts = Counter(row["label"] for row in rows)
    second_counts = Counter(second[row["id"]] for row in rows)
    by_chance = sum(first_counts[label] * second_counts[label] for label in ROUTE_LABELS) / (
        total * total
    )
    observed = same / total
    clear = [row for row in rows if not row["borderline"]]
    return {
        "agreed": _rate(same, total),
        "cohens_kappa": (observed - by_chance) / (1 - by_chance),
        "agreed_on_clear": _rate(sum(second[r["id"]] == r["label"] for r in clear), len(clear)),
        "disagreed": [row["id"] for row in rows if second[row["id"]] != row["label"]],
    }


def _line(label: str, rate: Mapping[str, Any]) -> str:
    if rate["rate"] is None:
        return f"{label}: none"
    low, high = rate["ci95"]
    return f"{label}: {rate['count']}/{rate['of']} ({rate['rate']:.0%}, {low:.0%}-{high:.0%})"


def print_scores(name: str, scores: Mapping[str, Any]) -> None:
    """Print one router's scores for a person to read."""
    clear = scores["clear"]
    print(f"\n{name}")
    print("  " + _line("right, clear messages", clear["accuracy"]))
    print("  " + _line("right, borderline messages", scores["borderline"]["accuracy"]))
    for error in ERRORS:
        print("  " + _line(error, clear["errors"][error]))
    for label in ROUTE_LABELS:
        both = clear["by_label"][label]
        print(
            f"  {label}: "
            + _line("recall", both["recall"])
            + "; "
            + _line("precision", both["precision"])
        )


def _set_sha256() -> str:
    return hashlib.sha256(ROUTING_SET.read_bytes()).hexdigest()


def _predict_with_rules(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    for row in rows:
        decision = route_with_rules(row["text"])
        predictions[row["id"]] = {"route": decision.route, "category": decision.category}
    return predictions


def _predict_with_model(
    rows: Sequence[Mapping[str, Any]], endpoint: str
) -> dict[str, dict[str, Any]]:
    # Imported here so that scoring the rules, and the tests, do not load the model stack.
    from databricks_langchain import ChatDatabricks
    from dotenv import load_dotenv

    load_dotenv()
    model = ChatDatabricks(endpoint=endpoint, temperature=0.0, max_tokens=600, max_retries=6)
    predictions: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows, start=1):
        started = time.perf_counter()
        decision = route_with_model(row["text"], model)
        predictions[row["id"]] = {
            "route": decision.route,
            "category": decision.category,
            "parsed": decision.parsed,
            "seconds": round(time.perf_counter() - started, 2),
        }
        print(f"  {number}/{len(rows)}", flush=True)
    return predictions


def _predict_with_agent(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    # Imported here so that scoring the rules, and the tests, do not load the model stack.
    import mlflow
    from dotenv import load_dotenv

    from copilot.agent import Copilot
    from copilot.config import load_settings
    from copilot.guardrails import FLAG_INJECTION

    load_dotenv()
    # No ticket is written for a made-up customer, and these runs are not traced.
    settings = load_settings().model_copy(update={"record_escalations": False})
    mlflow.tracing.disable()
    copilot = Copilot(settings)
    predictions: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows, start=1):
        started = time.perf_counter()
        answer = copilot.run(row["text"])
        if answer.escalated:
            route = "hand_off"
        elif FLAG_INJECTION in answer.guardrail_flags:
            route = "refuse"
        else:
            route = "answer"
        predictions[row["id"]] = {
            "route": route,
            "category": None,
            "tools_used": answer.tools_used,
            "flags": answer.guardrail_flags,
            "seconds": round(time.perf_counter() - started, 2),
        }
        print(f"  {number}/{len(rows)}", flush=True)
    return predictions


def _saved(results_dir: Path = RESULTS_DIR) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(results_dir.glob("routing_*.json"))
    ]


def compare(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Score every saved router, and rules-then-model for every saved model."""
    saved = _saved()
    rules = next((item for item in saved if item["router"] == "rules"), None)
    scores: dict[str, dict[str, Any]] = {}
    for item in saved:
        predicted = {row_id: value["route"] for row_id, value in item["predictions"].items()}
        scores[item["name"]] = score_all(rows, predicted)
        if rules is not None and item["router"] == "model":
            together = {
                row_id: combine(
                    RouteDecision(rules["predictions"][row_id]["route"]),
                    RouteDecision(value["route"]),
                ).route
                for row_id, value in item["predictions"].items()
            }
            scores[f"rules, then {item['name']}"] = score_all(rows, together)
    return scores


def main(argv: list[str] | None = None) -> None:
    """Score one router, or compare the saved ones."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--router", choices=["rules", "model", "agent"])
    parser.add_argument("--endpoint", help="the serving endpoint, for --router model")
    parser.add_argument("--limit", type=int, default=None, help="score this many, save nothing")
    parser.add_argument("--save", action="store_true", help="write a result file")
    parser.add_argument("--compare", action="store_true", help="score every saved router")
    args = parser.parse_args(argv)

    rows = load_set()
    if args.compare:
        for name, scores in compare(rows).items():
            print_scores(name, scores)
        return
    if args.router is None or (args.router == "model" and not args.endpoint):
        parser.error("give --router rules, or --router model with --endpoint")
    if args.save and args.limit is not None:
        parser.error("--limit is a trial; it cannot be saved")
    dirty = bool(_git("status", "--porcelain", "--", ".", ":(exclude)eval/results"))
    if args.save and dirty:
        print("not started: commit first, so the result names the code that made it")
        raise SystemExit(1)

    chosen = rows[: args.limit] if args.limit else rows
    if args.router == "rules":
        name = "rules"
        predictions = _predict_with_rules(chosen)
    elif args.router == "agent":
        name = "agent"
        predictions = _predict_with_agent(chosen)
    else:
        name = args.endpoint.removeprefix("databricks-")
        predictions = _predict_with_model(chosen, args.endpoint)
    predicted = {row_id: value["route"] for row_id, value in predictions.items()}
    scores = score_all(chosen, predicted)
    print_scores(name, scores)
    unread = sum(1 for value in predictions.values() if value.get("parsed") is False)
    if unread:
        print(f"  replies that could not be read: {unread}")
    if not args.save:
        return
    second = {
        item["id"]: item["label"]
        for item in (
            json.loads(line)
            for line in SECOND_LABELS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    report = {
        "scored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "name": name,
        "router": args.router,
        "endpoint": args.endpoint if args.router == "model" else None,
        "router_prompt_version": ROUTER_PROMPT_VERSION if args.router == "model" else None,
        "git_sha": _git("rev-parse", "HEAD"),
        "set_sha256": _set_sha256(),
        "first_contact": True,
        "annotators": annotator_agreement(rows, second),
        "replies_not_read": unread,
        **scores,
        "predictions": predictions,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"routing_{report['scored_at'][:10]}_{name}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"saved {path.as_posix()}")


if __name__ == "__main__":
    main()
