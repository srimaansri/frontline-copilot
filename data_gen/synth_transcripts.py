"""Generate synthetic support transcripts with exact PII ground truth.

Every personal value is inserted by code through a template slot, and its
character span is recorded at that moment. No language model is involved, so
the labels are exact and the output is identical for a given seed.

Usage:
    python -m data_gen.synth_transcripts --seed 42
    python -m data_gen.synth_transcripts --seed 7 --out-dir data/raw/dev --labeled 200

The first ``--labeled`` transcripts cycle through the categories in order so
that every entity type appears in the labeled set. The rest are sampled by
``CATEGORY_WEIGHTS``.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any

from faker import Faker

from copilot.luhn import luhn_check_digit
from data_gen.plans import PLANS
from data_gen.transcript_templates import (
    CATEGORY_WEIGHTS,
    CLOSINGS,
    ISSUES,
    OPENINGS,
    PLAIN_SLOTS,
    SLOT_ENTITY,
    VERIFICATION,
    VERIFY_LEAD_IN,
    Turn,
)

DEFAULT_OUT_DIR = Path("data/raw")
DEFAULT_COUNT = 200
DEFAULT_LABELED = 30
CALL_SHARE = 0.6

_SLOT_RE = re.compile(r"\{(\w+)\}")
_START_DATE = datetime(2026, 8, 1, tzinfo=UTC)
_WINDOW_MINUTES = 90 * 24 * 60

# Real US area codes. The 555-01xx exchange is reserved for fiction.
_AREA_CODES = ("480", "602", "503", "971", "206", "312", "404", "615", "813", "919", "702", "303")
_DEVICES = (
    "Galaxy A15", "iPhone 13", "Pixel 8a", "Moto G Power", "iPhone SE", "Galaxy S23",
    "flip phone",
)  # fmt: skip
_COUNTRIES = ("Mexico", "Canada", "Italy", "Ireland", "Japan", "Germany", "the Philippines")
_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)  # fmt: skip


@dataclass(frozen=True)
class Label:
    """Ground truth for one PII or CPNI value inside one turn."""

    transcript_id: str
    turn_index: int
    start: int
    end: int
    entity_type: str
    text: str


def render(template: str, values: Mapping[str, str]) -> tuple[str, list[tuple[int, int, str]]]:
    """Fill ``{slot}`` markers and return the text with ``(start, end, entity_type)`` spans.

    Only slots listed in ``SLOT_ENTITY`` produce a span.
    """
    parts: list[str] = []
    spans: list[tuple[int, int, str]] = []
    position = 0
    cursor = 0
    for match in _SLOT_RE.finditer(template):
        literal = template[cursor : match.start()]
        parts.append(literal)
        position += len(literal)
        slot = match.group(1)
        if slot not in SLOT_ENTITY and slot not in PLAIN_SLOTS:
            msg = f"unknown slot {{{slot}}} in template: {template!r}"
            raise KeyError(msg)
        value = values[slot]
        if slot in SLOT_ENTITY:
            spans.append((position, position + len(value), SLOT_ENTITY[slot]))
        parts.append(value)
        position += len(value)
        cursor = match.end()
    parts.append(template[cursor:])
    return "".join(parts), spans


def _phone(rng: Random) -> str:
    area = rng.choice(_AREA_CODES)
    line = f"01{rng.randrange(100):02d}"
    style = rng.randrange(5)
    if style == 0:
        return f"{area}-555-{line}"
    if style == 1:
        return f"({area}) 555-{line}"
    if style == 2:
        return f"{area}.555.{line}"
    if style == 3:
        return f"{area}555{line}"
    return f"+1 {area} 555 {line}"


def _digits(rng: Random, count: int) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(count))


def _imei(rng: Random) -> str:
    body = "35" + _digits(rng, 12)
    imei = body + luhn_check_digit(body)
    if rng.random() < 0.2:
        return f"{imei[:2]} {imei[2:8]} {imei[8:14]} {imei[14]}"
    return imei


def _iccid(rng: Random) -> str:
    body = "8901" + _digits(rng, rng.choice((14, 15)))
    return body + luhn_check_digit(body)


def _credit_card(rng: Random) -> str:
    prefix = rng.choice(("4", "51", "52", "53", "54", "55"))
    body = prefix + _digits(rng, 15 - len(prefix))
    number = body + luhn_check_digit(body)
    style = rng.randrange(3)
    if style == 0:
        return number
    separator = " " if style == 1 else "-"
    return separator.join(number[index : index + 4] for index in range(0, 16, 4))


def _date_of_birth(rng: Random) -> str:
    year = rng.randrange(1935, 1976)
    month = rng.randrange(1, 13)
    day = rng.randrange(1, 29)
    style = rng.randrange(4)
    if style == 0:
        return f"{month:02d}/{day:02d}/{year}"
    if style == 1:
        return f"{month}/{day}/{year % 100:02d}"
    if style == 2:
        return f"{_MONTHS[month - 1]} {day}, {year}"
    suffix = "th" if 4 <= day <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{_MONTHS[month - 1]} {day}{suffix}, {year}"


def _address(fake: Faker, rng: Random) -> str:
    street = f"{fake.building_number()} {fake.street_name()}"
    if rng.random() < 0.2:
        street += f" Apt {rng.randrange(1, 40)}{rng.choice(('', 'A', 'B', 'C'))}"
    style = rng.randrange(3)
    if style == 0:
        return f"{street}, {fake.city()}, {fake.state_abbr()} {fake.zipcode()}"
    if style == 1:
        return f"{street}, {fake.city()}"
    return street


def _money(rng: Random, low: float, high: float) -> str:
    return f"${rng.uniform(low, high):.2f}"


def build_persona(fake: Faker) -> dict[str, str]:
    """Create every slot value for one transcript."""
    rng = fake.random
    first = fake.first_name()
    last = fake.last_name()
    current, cheaper = rng.sample([row for row in PLANS if row.kind == "plan"], 2)
    if cheaper.monthly_price_usd > current.monthly_price_usd:
        current, cheaper = cheaper, current
    bill = rng.uniform(38.0, 190.0)
    statement = _START_DATE + timedelta(days=rng.randrange(90))
    return {
        "customer_name": f"{first} {last}",
        "customer_name_lower": f"{first} {last}".lower(),
        "customer_first": first,
        "agent_first": fake.first_name(),
        "other_name": f"{fake.first_name()} {last if rng.random() < 0.7 else fake.last_name()}",
        "phone": _phone(rng),
        "alt_phone": _phone(rng),
        "called_number": _phone(rng),
        "scam_number": _phone(rng),
        "email": fake.email(),
        "address": _address(fake, rng),
        "dob": _date_of_birth(rng),
        "account_number": str(rng.randrange(1, 10)) + _digits(rng, rng.choice((8, 9))),
        "imei": _imei(rng),
        "iccid": _iccid(rng),
        "ssn_last4": _digits(rng, 4),
        "credit_card": _credit_card(rng),
        "bill_amount": f"${bill:.2f}",
        "prev_bill_amount": _money(rng, 25.0, max(26.0, bill - 10.0)),
        "usage_minutes": f"{rng.randrange(35, 900)} minutes",
        "data_used": f"{rng.uniform(0.4, 24.0):.1f} {rng.choice(('GB', 'gigs', 'gigabytes'))}",
        "plan_name": current.name,
        "plan_price": f"${current.monthly_price_usd:.0f}",
        "new_plan_name": cheaper.name,
        "new_plan_price": f"${cheaper.monthly_price_usd:.0f}",
        "country": rng.choice(_COUNTRIES),
        "device": rng.choice(_DEVICES),
        "ticket": f"NW-{_digits(rng, 6)}",
        "statement_date": f"{_MONTHS[statement.month - 1]} {statement.day}",
    }


def _compose(category: str, channel: str, rng: Random) -> tuple[list[Turn], str]:
    """Pick the building blocks for one conversation and return its turns and resolution."""
    issue = rng.choice(ISSUES[category])
    turns: list[Turn] = list(rng.choice(OPENINGS[channel]))
    turns.extend(issue.intro)
    turns.append(("agent", rng.choice(VERIFY_LEAD_IN)))
    for item in rng.sample(sorted(VERIFICATION), rng.choice((2, 2, 3))):
        question, answer = rng.choice(VERIFICATION[item])
        turns.append(("agent", question))
        turns.append(("customer", answer))
    turns.extend(issue.body)
    turns.extend(rng.choice(CLOSINGS[channel][issue.resolution]))
    return turns, issue.resolution


def build_transcript(
    transcript_id: str, category: str, channel: str, fake: Faker
) -> tuple[dict[str, Any], list[Label]]:
    """Build one transcript record and the labels for every PII value in it."""
    rng = fake.random
    persona = build_persona(fake)
    templates, resolution = _compose(category, channel, rng)
    turns: list[dict[str, str]] = []
    labels: list[Label] = []
    for turn_index, (speaker, template) in enumerate(templates):
        text, spans = render(template, persona)
        turns.append({"speaker": speaker, "text": text})
        labels.extend(
            Label(transcript_id, turn_index, start, end, entity_type, text[start:end])
            for start, end, entity_type in spans
        )
    created = _START_DATE + timedelta(minutes=rng.randrange(_WINDOW_MINUTES))
    record = {
        "transcript_id": transcript_id,
        "channel": channel,
        "category": category,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "turns": turns,
        "resolution": resolution,
    }
    return record, labels


def generate(
    seed: int, count: int = DEFAULT_COUNT, labeled: int = DEFAULT_LABELED
) -> tuple[list[dict[str, Any]], list[Label]]:
    """Generate ``count`` transcripts and the labels for the first ``labeled`` of them."""
    fake = Faker("en_US")
    fake.seed_instance(seed)
    rng = fake.random
    categories = list(CATEGORY_WEIGHTS)
    weights = list(CATEGORY_WEIGHTS.values())
    transcripts: list[dict[str, Any]] = []
    labels: list[Label] = []
    for index in range(count):
        transcript_id = f"T{index + 1:04d}"
        if index < labeled:
            category = categories[index % len(categories)]
        else:
            category = rng.choices(categories, weights=weights, k=1)[0]
        channel = "call" if rng.random() < CALL_SHARE else "chat"
        record, record_labels = build_transcript(transcript_id, category, channel, fake)
        transcripts.append(record)
        if index < labeled:
            labels.extend(record_labels)
    return transcripts, labels


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_outputs(
    out_dir: Path, transcripts: Sequence[Mapping[str, Any]], labels: Sequence[Label]
) -> None:
    """Write ``transcripts.jsonl`` and ``pii_labels.jsonl`` into ``out_dir``."""
    _write_jsonl(out_dir / "transcripts.jsonl", transcripts)
    _write_jsonl(out_dir / "pii_labels.jsonl", (vars(label) for label in labels))


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--labeled", type=int, default=DEFAULT_LABELED)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    transcripts, labels = generate(args.seed, args.count, args.labeled)
    write_outputs(args.out_dir, transcripts, labels)
    # Counts only: transcript text is never printed.
    print(
        f"seed {args.seed}: wrote {len(transcripts)} transcripts and {len(labels)} labels "
        f"to {args.out_dir}"
    )


if __name__ == "__main__":
    main()
