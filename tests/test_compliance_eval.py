"""The compliance evaluation's scoring, and that it cannot record a result by accident."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import eval.compliance_eval as compliance_eval
from copilot.compliance import (
    RULE_CARD_READ_BACK,
    RULE_DISCLOSURE,
    RULE_PROMISE,
    RULE_SKIPPED,
    RULES,
    Finding,
)
from copilot.redaction import Redactor
from data_gen.synth_breaches import CallLabel, generate
from data_gen.synth_transcripts import _write_jsonl
from eval.compliance_eval import (
    _jsonl_sha256,
    false_alarms,
    find_all,
    format_false_alarms,
    format_scores,
    redact_call,
    score,
)
from eval.stats import wilson_interval


def label(call_id: str, rule: str | None, turn: int | None, variant: str = "clean") -> CallLabel:
    return CallLabel(call_id, "dev", rule, turn, variant, "billing/1", None)


def finding(rule: str, turn: int) -> Finding:
    return Finding(rule, turn, "A reason.")


LABELS = [
    label("T1", RULE_CARD_READ_BACK, 9, "card_read_back"),
    label("T2", RULE_CARD_READ_BACK, 9, "card_read_back"),
    label("T3", RULE_CARD_READ_BACK, 9, "card_read_back"),
    label("T4", None, None, "card_not_repeated"),
    label("T5", None, None, "clean"),
    label("T6", RULE_PROMISE, 14, "unauthorized_promise"),
]
FOUND = {
    "T1": [finding(RULE_CARD_READ_BACK, 9)],
    # Caught, but at another turn, and with a second rule firing wrongly.
    "T2": [finding(RULE_PROMISE, 3), finding(RULE_CARD_READ_BACK, 11)],
    "T3": [],
    "T4": [finding(RULE_CARD_READ_BACK, 9)],
    "T5": [],
    "T6": [finding(RULE_PROMISE, 14), finding(RULE_PROMISE, 16)],
}


def test_score_counts_recall_precision_and_the_turn() -> None:
    scores = score(LABELS, FOUND)
    card = scores["by_rule"][RULE_CARD_READ_BACK]
    promise = scores["by_rule"][RULE_PROMISE]

    assert (scores["calls"], scores["breaches"]) == (6, 4)
    assert (card["recall"]["count"], card["recall"]["of"]) == (2, 3)
    assert (card["precision"]["count"], card["precision"]["of"]) == (2, 3)
    assert (card["right_turn"]["count"], card["right_turn"]["of"]) == (1, 2)
    assert card["recall"]["ci95"] == list(wilson_interval(2, 3))
    assert (promise["recall"]["count"], promise["recall"]["of"]) == (1, 1)
    assert (promise["precision"]["count"], promise["precision"]["of"]) == (1, 2)
    assert promise["right_turn"]["rate"] == 1.0
    assert scores["caught_at_another_turn"] == [
        {"transcript_id": "T2", "rule": RULE_CARD_READ_BACK, "labelled_turn": 9, "found_turn": 11}
    ]


def test_a_rule_with_no_breaches_and_no_findings_has_no_rate() -> None:
    skipped = score(LABELS, FOUND)["by_rule"][RULE_SKIPPED]

    assert skipped["recall"] == {"count": 0, "of": 0, "rate": None, "ci95": None}
    assert skipped["precision"]["rate"] is None


def test_score_lists_each_call_judged_wrongly_without_any_text() -> None:
    scores = score(LABELS, FOUND)

    assert [row["transcript_id"] for row in scores["wrong"]] == ["T2", "T3", "T4"]
    assert scores["wrong"][0]["found"] == [RULE_CARD_READ_BACK, RULE_PROMISE]
    assert scores["wrong"][1]["found"] == []
    assert scores["right_by_variant"]["card_read_back"]["count"] == 1
    assert scores["right_by_variant"]["card_not_repeated"]["rate"] == 0.0
    assert scores["right_by_variant"]["clean"]["rate"] == 1.0
    assert "A reason." not in json.dumps(scores)


def test_false_alarms_counts_calls_not_findings() -> None:
    result = false_alarms(
        {
            "T0001": [],
            "T0002": [finding(RULE_DISCLOSURE, 4), finding(RULE_DISCLOSURE, 6)],
            "T0003": [finding(RULE_PROMISE, 9)],
            "T0004": [],
        }
    )

    assert (result["calls_flagged"]["count"], result["calls_flagged"]["of"]) == (2, 4)
    assert result["calls_flagged"]["ci95"] == list(wilson_interval(2, 4))
    assert result["by_rule"][RULE_DISCLOSURE] == 1
    assert result["by_rule"][RULE_PROMISE] == 1
    assert set(result["by_rule"]) == set(RULES)
    assert list(result["flagged"]) == ["T0002", "T0003"]
    assert result["flagged"]["T0003"] == [{"rule": RULE_PROMISE, "turn_index": 9}]


def test_the_printed_report_names_counts_and_intervals() -> None:
    text = format_scores("development half", score(LABELS, FOUND))
    alarms = format_false_alarms(false_alarms({"T0001": [], "T0002": [finding(RULE_PROMISE, 9)]}))

    assert "development half: 6 calls, 4 with a breach" in text
    assert "recall: 2/3 (67%, 21%-94%)" in text
    assert "recall: none" in text
    assert "wrong: T3 card_read_back on billing/1 (no wording entry): found nothing" in text
    assert "other turn: T2 card_read_back: labelled turn 9, found at 11" in text
    assert "clean calls (seed 42) with any finding: 1/2 (50%, 9%-91%)" in alarms
    assert "flagged: T0002 ['unauthorized_promise']" in alarms


def test_the_hash_is_the_hash_of_the_file_the_generator_writes(tmp_path: Path) -> None:
    rows = [{"transcript_id": "T0001", "text": "café"}, {"transcript_id": "T0002"}]
    _write_jsonl(tmp_path / "rows.jsonl", rows)

    assert _jsonl_sha256(rows) == hashlib.sha256((tmp_path / "rows.jsonl").read_bytes()).hexdigest()


# --- with the redactor -------------------------------------------------------------------


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


def test_a_generated_read_back_is_found_after_redaction(redactor: Redactor) -> None:
    transcripts, labels = generate()
    by_id = {transcript["transcript_id"]: transcript for transcript in transcripts}
    chosen = [x for x in labels if x.split == "dev" and x.variant == "card_read_back"][:3]

    redacted = redact_call(by_id[chosen[0].transcript_id], redactor)
    found = find_all([by_id[x.transcript_id] for x in chosen], redactor)

    assert [turn["speaker"] for turn in redacted] == [
        turn["speaker"] for turn in by_id[chosen[0].transcript_id]["turns"]
    ]
    assert "<CREDIT_CARD_1>" in redacted[chosen[0].turn_index or 0]["text"]
    for x in chosen:
        assert (RULE_CARD_READ_BACK, x.turn_index) in {
            (f.rule, f.turn_index) for f in found[x.transcript_id]
        }


# --- the command line ---------------------------------------------------------------------


def test_save_needs_the_held_out_half() -> None:
    with pytest.raises(SystemExit):
        compliance_eval.main(["--save"])


def test_nothing_is_scored_or_saved_from_uncommitted_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_scoring(*_: Any, **__: Any) -> None:
        raise AssertionError("the held-out half must not be scored from a dirty tree")

    monkeypatch.setattr(compliance_eval, "_git", lambda *_: " M src/copilot/compliance.py")
    monkeypatch.setattr(compliance_eval, "generate_breaches", no_scoring)

    with pytest.raises(SystemExit):
        compliance_eval.main(["--held-out", "--save"])

    assert "commit first" in capsys.readouterr().out
