"""The redaction evaluation script: markup parsing, the challenge file, and scoring."""

import pytest

from copilot.luhn import luhn_valid
from copilot.redaction import ALL_ENTITY_TYPES, Redactor
from eval.redaction_eval import (
    CHALLENGE_FILE,
    evaluate,
    format_report,
    load_challenge,
    parse_marked_turn,
)


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor("en_core_web_sm")


def test_markup_is_stripped_and_spans_point_at_the_plain_text() -> None:
    text, spans = parse_marked_turn("Call [[PHONE_NUMBER|480-555-0132]] or [[PERSON|Linda]].")

    assert text == "Call 480-555-0132 or Linda."
    assert [(text[start:end], kind) for start, end, kind in spans] == [
        ("480-555-0132", "PHONE_NUMBER"),
        ("Linda", "PERSON"),
    ]


def test_turn_without_markup_has_no_spans() -> None:
    assert parse_marked_turn("Press 2 for billing.") == ("Press 2 for billing.", [])


def test_challenge_file_is_well_formed() -> None:
    transcripts, labels = load_challenge(CHALLENGE_FILE)
    by_id = {t["transcript_id"]: t for t in transcripts}

    assert len(transcripts) >= 40
    assert {label["entity_type"] for label in labels} == set(ALL_ENTITY_TYPES)
    for label in labels:
        turn_text = by_id[label["transcript_id"]]["turns"][label["turn_index"]]["text"]
        assert turn_text[label["start"] : label["end"]] == label["text"]
    for transcript in transcripts:
        for turn in transcript["turns"]:
            assert "[[" not in turn["text"]
            assert "]]" not in turn["text"]
    # Some lines are negatives and carry no label at all.
    assert len({label["transcript_id"] for label in labels}) < len(transcripts)


def test_challenge_checksummed_values_are_what_they_claim() -> None:
    _, labels = load_challenge(CHALLENGE_FILE)
    cards = [label["text"] for label in labels if label["entity_type"] == "CREDIT_CARD"]

    assert cards
    assert all(luhn_valid(card) for card in cards)
    # One IMEI is deliberately off by one digit, as a mis-transcribed number would be.
    imeis = [label["text"] for label in labels if label["entity_type"] == "IMEI"]
    assert [luhn_valid(imei) for imei in imeis] == [True, True, False]


def test_evaluate_scores_hits_misses_and_negatives(redactor: Redactor) -> None:
    transcripts = [
        {"transcript_id": "A", "turns": [{"speaker": "customer", "text": "Call 480-555-0132."}]},
        {"transcript_id": "B", "turns": [{"speaker": "customer", "text": "My dog is brown."}]},
        {"transcript_id": "C", "turns": [{"speaker": "agent", "text": "Press 2 for billing."}]},
    ]
    labels = [
        {"transcript_id": "A", "turn_index": 0, "start": 5, "end": 17,
         "entity_type": "PHONE_NUMBER"},
        # Labeled as an address on purpose: the redactor will not find one here.
        {"transcript_id": "B", "turn_index": 0, "start": 10, "end": 15,
         "entity_type": "ADDRESS"},
    ]  # fmt: skip

    report = evaluate(transcripts, labels, redactor, score_all=True, collect_errors=True)

    assert report["transcripts"] == 3
    assert report["turns"] == 3
    assert report["per_entity"]["PHONE_NUMBER"]["tp"] == 1
    assert report["per_entity"]["PHONE_NUMBER"]["recall"] == 1.0
    assert report["per_entity"]["ADDRESS"]["fn"] == 1
    assert report["overall_pii"]["support"] == 2
    assert report["overall_pii"]["recall"] == 0.5
    assert report["overall_cpni"]["recall"] is None
    assert report["char_coverage"]["pii"] == {"covered": 12, "total": 17, "rate": 12 / 17}
    assert len(report["errors"]) == 1


def test_unlabeled_transcripts_are_skipped_by_default(redactor: Redactor) -> None:
    transcripts = [
        {"transcript_id": "A", "turns": [{"speaker": "customer", "text": "Call 480-555-0132."}]},
        {"transcript_id": "B", "turns": [{"speaker": "customer", "text": "Call 602-555-0100."}]},
    ]
    labels = [
        {"transcript_id": "A", "turn_index": 0, "start": 5, "end": 17,
         "entity_type": "PHONE_NUMBER"},
    ]  # fmt: skip

    report = evaluate(transcripts, labels, redactor)

    assert report["transcripts"] == 1
    assert report["per_entity"]["PHONE_NUMBER"] == {
        "support": 1, "tp": 1, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0,
    }  # fmt: skip


def test_report_table_contains_no_transcript_text(redactor: Redactor) -> None:
    transcripts = [
        {"transcript_id": "A", "turns": [{"speaker": "customer", "text": "Call 480-555-0132."}]},
    ]
    labels = [
        {"transcript_id": "A", "turn_index": 0, "start": 5, "end": 17,
         "entity_type": "PHONE_NUMBER"},
    ]  # fmt: skip

    table = format_report(evaluate(transcripts, labels, redactor))

    assert "480-555-0132" not in table
    assert "PHONE_NUMBER" in table
    assert "n/a" in table
