"""Data generators: determinism, exact labels, and catalogue integrity."""

import csv
from collections import Counter
from pathlib import Path

import pytest

from copilot.luhn import luhn_valid
from data_gen.plans import PLANS, write_plans
from data_gen.synth_transcripts import generate, render, write_outputs
from data_gen.transcript_templates import (
    CATEGORY_WEIGHTS,
    CLOSINGS,
    ISSUES,
    OPENINGS,
    SLOT_ENTITY,
    VERIFICATION,
)

SEED = 42


@pytest.fixture(scope="module")
def generated() -> tuple[list[dict], list]:
    return generate(SEED)


# --- plans -------------------------------------------------------------------


def test_plan_ids_are_unique() -> None:
    ids = [row.plan_id for row in PLANS]

    assert len(ids) == len(set(ids))


def test_catalogue_has_plans_addons_and_fees() -> None:
    kinds = Counter(row.kind for row in PLANS)

    assert kinds["plan"] == 8
    assert kinds["addon"] + kinds["fee"] == 10


def test_plans_csv_round_trips_and_is_stable(tmp_path: Path) -> None:
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"

    assert write_plans(first) == len(PLANS)
    write_plans(second)

    assert first.read_bytes() == second.read_bytes()
    with first.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["plan_id"] for row in rows] == [row.plan_id for row in PLANS]
    unlimited = next(row for row in rows if row["plan_id"] == "P06")
    assert unlimited["data_gb"] == ""
    assert unlimited["monthly_price_usd"] == "50.00"


# --- transcripts ---------------------------------------------------------------


def test_render_records_exact_spans() -> None:
    text, spans = render(
        "Call {phone} about {plan_name}.", {"phone": "480-555-0132", "plan_name": "Northline Talk"}
    )

    assert text == "Call 480-555-0132 about Northline Talk."
    assert spans == [(5, 17, "PHONE_NUMBER")]
    assert text[5:17] == "480-555-0132"


def test_render_rejects_unknown_slot() -> None:
    with pytest.raises(KeyError, match="unknown slot"):
        render("Hello {nobody}", {"nobody": "x"})


def test_generation_is_deterministic(generated: tuple[list[dict], list]) -> None:
    assert generate(SEED) == generated


def test_different_seeds_differ(generated: tuple[list[dict], list]) -> None:
    assert generate(SEED + 1)[0] != generated[0]


def test_counts_and_ids(generated: tuple[list[dict], list]) -> None:
    transcripts, labels = generated

    assert len(transcripts) == 200
    assert [t["transcript_id"] for t in transcripts[:2]] == ["T0001", "T0002"]
    assert transcripts[-1]["transcript_id"] == "T0200"
    assert {label.transcript_id for label in labels} == {f"T{i:04d}" for i in range(1, 31)}


def test_every_label_matches_the_text(generated: tuple[list[dict], list]) -> None:
    transcripts, labels = generated
    by_id = {t["transcript_id"]: t for t in transcripts}

    assert labels
    for label in labels:
        turn_text = by_id[label.transcript_id]["turns"][label.turn_index]["text"]
        assert turn_text[label.start : label.end] == label.text
        assert label.text.strip() == label.text


def test_labeled_set_covers_every_entity_type_and_category(
    generated: tuple[list[dict], list],
) -> None:
    transcripts, labels = generated

    assert {label.entity_type for label in labels} == set(SLOT_ENTITY.values())
    assert {t["category"] for t in transcripts[:30]} == set(CATEGORY_WEIGHTS)


def test_no_unfilled_slots_remain(generated: tuple[list[dict], list]) -> None:
    transcripts, _ = generated

    for transcript in transcripts:
        for turn in transcript["turns"]:
            assert "{" not in turn["text"]
            assert "}" not in turn["text"]


def test_channel_mix_is_roughly_sixty_forty(generated: tuple[list[dict], list]) -> None:
    transcripts, _ = generated
    calls = sum(t["channel"] == "call" for t in transcripts)

    assert 100 <= calls <= 140


def test_checksummed_values_are_luhn_valid(generated: tuple[list[dict], list]) -> None:
    _, labels = generated
    checked = [label for label in labels if label.entity_type in {"IMEI", "ICCID", "CREDIT_CARD"}]

    assert checked
    for label in checked:
        assert luhn_valid(label.text)


def test_phone_numbers_use_the_fictional_exchange(generated: tuple[list[dict], list]) -> None:
    _, labels = generated
    phones = [label.text for label in labels if label.entity_type == "PHONE_NUMBER"]

    assert phones
    for phone in phones:
        digits = "".join(char for char in phone if char.isdigit())[-10:]
        assert digits[3:8] == "55501"


def test_templates_are_complete() -> None:
    assert set(ISSUES) == set(CATEGORY_WEIGHTS)
    assert set(OPENINGS) == set(CLOSINGS) == {"call", "chat"}
    for closings in CLOSINGS.values():
        assert set(closings) == {"resolved", "escalated", "unresolved"}
    assert len(VERIFICATION) == 6


def test_write_outputs(tmp_path: Path, generated: tuple[list[dict], list]) -> None:
    transcripts, labels = generated

    write_outputs(tmp_path, transcripts, labels)

    assert len((tmp_path / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()) == 200
    label_lines = (tmp_path / "pii_labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(label_lines) == len(labels)
