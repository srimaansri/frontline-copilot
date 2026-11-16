"""Load and check the wording used to seed rule breaches into synthetic calls.

``synth_breaches.py`` builds calls in which a rule is broken, and calls that
look close to a breach and are not one. The words of those turns come from two
files with the same shape:

* ``breach_wording_dev.json``: written by the author of the compliance rules.
  The rules are tuned on calls built from it.
* ``breach_wording_held_out.json``: written by someone who was given the policy
  in words and was not allowed to read the rules. Calls built from it are
  scored once.

A file has ten lists. Eight hold a pair of lines, one for the agent and one for
the customer. Two hold whole scenarios, written like the ones in
``transcript_templates.py``.

Usage:
    python -m data_gen.breach_wording data_gen/breach_wording_held_out.json

Prints what is wrong with the file, or that it passes. It never prints a line
from the file itself.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from data_gen.transcript_templates import (
    CATEGORY_WEIGHTS,
    PLAIN_SLOTS,
    SLOT_ENTITY,
    Issue,
    Resolution,
    Speaker,
    Turn,
)

WORDING_DIR = Path(__file__).parent
DEV_WORDING = WORDING_DIR / "breach_wording_dev.json"
HELD_OUT_WORDING = WORDING_DIR / "breach_wording_held_out.json"

# Slots that exist only for these calls. Neither is personal data on its own:
# the last four digits of a card are what an agent is allowed to say back.
EXTRA_PLAIN_SLOTS: frozenset[str] = frozenset({"card_last4"})
ALLOWED_SLOTS: frozenset[str] = frozenset(SLOT_ENTITY) | PLAIN_SLOTS | EXTRA_PLAIN_SLOTS

# Slots that state something from this customer's account.
ACCOUNT_SLOTS: frozenset[str] = frozenset(
    {"bill_amount", "prev_bill_amount", "usage_minutes", "data_used", "plan_name", "plan_price"}
)
DISCLOSURE_SLOTS: frozenset[str] = ACCOUNT_SLOTS - {"plan_price"} | {"statement_date"}

# Pool name -> fewest entries a file must have.
PAIR_POOLS: dict[str, int] = {
    "disclosure": 20,
    "catalogue": 10,
    "card_read_back": 20,
    "card_safe": 10,
    "promise": 20,
    "promise_safe": 10,
    "full_ssn": 20,
    "ssn_safe": 10,
}
SCENARIO_POOLS: dict[str, int] = {"account_scenarios": 4, "general_scenarios": 3}

MAX_LINE_CHARS = 320
_RESOLUTIONS = ("resolved", "escalated", "unresolved")
_SLOT_RE = re.compile(r"\{(\w+)\}")
_SUPPORT_NUMBER = "1-800-555-0199"
# A literal value that should have been a slot: a long digit run, a phone or
# Social Security shaped number, or an email address.
_LITERAL_VALUE_RE = re.compile(
    r"\d{5,}|\d{3}[-. ]\d{3}[-. ]\d{4}|\d{3}[-. ]\d{2}[-. ]\d{4}|\d{4}[- ]\d{4}|\S+@\S+\.\w+"
)


@dataclass(frozen=True)
class Pair:
    """Two lines that are placed together: what the agent says and what the customer says."""

    agent: str
    customer: str


@dataclass(frozen=True)
class Scenario:
    """A whole conversation about one problem, with or without account access."""

    category: str
    issue: Issue
    # Index in ``issue.body`` of the first agent turn that reads from or changes
    # the customer's account. ``None`` for a scenario that never does.
    first_account_turn: int | None


@dataclass(frozen=True)
class Wording:
    """Everything one wording file holds."""

    pairs: Mapping[str, tuple[Pair, ...]]
    account_scenarios: tuple[Scenario, ...]
    general_scenarios: tuple[Scenario, ...]


def _slots(text: str) -> set[str]:
    return set(_SLOT_RE.findall(text))


def _line_problems(where: str, text: Any) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return [f"{where}: must be a line of text"]
    problems: list[str] = []
    if len(text) > MAX_LINE_CHARS:
        problems.append(f"{where}: longer than {MAX_LINE_CHARS} characters")
    unknown = sorted(_slots(text) - ALLOWED_SLOTS)
    if unknown:
        problems.append(f"{where}: unknown slot {', '.join(unknown)}")
    if _LITERAL_VALUE_RE.search(_SLOT_RE.sub("", text).replace(_SUPPORT_NUMBER, "")):
        problems.append(f"{where}: a literal number or address that should be a slot")
    if text.count("{") != len(_SLOT_RE.findall(text)) or text.count("}") != text.count("{"):
        problems.append(f"{where}: a brace that is not part of a slot")
    return problems


def _pair_problems(pool: str, index: int, entry: Any) -> list[str]:
    where = f"{pool}[{index}]"
    if not isinstance(entry, dict) or set(entry) != {"agent", "customer"}:
        return [f"{where}: must have exactly the keys agent and customer"]
    problems = _line_problems(f"{where}.agent", entry["agent"])
    problems += _line_problems(f"{where}.customer", entry["customer"])
    if problems:
        return problems
    agent_slots = _slots(entry["agent"])
    if pool == "disclosure" and not agent_slots & DISCLOSURE_SLOTS:
        problems.append(f"{where}.agent: states no account detail through a slot")
    if pool == "catalogue" and (agent_slots | _slots(entry["customer"])) & ACCOUNT_SLOTS:
        problems.append(f"{where}: uses an account slot, so it is not public information")
    if pool == "card_read_back" and "credit_card" not in agent_slots:
        problems.append(f"{where}.agent: does not repeat {{credit_card}}")
    if pool == "card_safe" and "credit_card" in agent_slots:
        problems.append(f"{where}.agent: repeats {{credit_card}}")
    return problems


def _scenario_problems(pool: str, index: int, entry: Any) -> list[str]:
    where = f"{pool}[{index}]"
    account = pool == "account_scenarios"
    keys = {"category", "intro", "body", "resolution"} | (
        {"first_account_turn"} if account else set()
    )
    if not isinstance(entry, dict) or set(entry) != keys:
        return [f"{where}: must have exactly the keys {', '.join(sorted(keys))}"]
    problems = _line_problems(f"{where}.intro", entry["intro"])
    if entry["category"] not in CATEGORY_WEIGHTS:
        problems.append(f"{where}.category: not one of {', '.join(CATEGORY_WEIGHTS)}")
    if entry["resolution"] not in _RESOLUTIONS:
        problems.append(f"{where}.resolution: not one of {', '.join(_RESOLUTIONS)}")
    if not account and entry["resolution"] == "escalated":
        # A hand-off opens a case on the account, so the call is no longer how-to help.
        problems.append(f"{where}.resolution: a how-to call is not escalated")
    body = entry["body"]
    if not isinstance(body, list) or not 4 <= len(body) <= 10:
        return [*problems, f"{where}.body: must be a list of 4 to 10 turns"]
    for number, turn in enumerate(body):
        turn_where = f"{where}.body[{number}]"
        if not isinstance(turn, dict) or set(turn) != {"speaker", "text"}:
            problems.append(f"{turn_where}: must have exactly the keys speaker and text")
            continue
        if turn["speaker"] not in ("agent", "customer"):
            problems.append(f"{turn_where}.speaker: must be agent or customer")
        problems += _line_problems(f"{turn_where}.text", turn["text"])
        states_detail = isinstance(turn["text"], str) and _slots(turn["text"]) & ACCOUNT_SLOTS
        if not account and turn["speaker"] == "agent" and states_detail:
            problems.append(f"{turn_where}: the agent states an account detail")
    if problems:
        return problems
    if body[0]["speaker"] != "agent":
        problems.append(f"{where}.body[0]: the agent speaks first")
    if account:
        first = entry["first_account_turn"]
        if not isinstance(first, int) or not 0 <= first < len(body):
            problems.append(f"{where}.first_account_turn: not the index of a turn in body")
        elif body[first]["speaker"] != "agent":
            problems.append(f"{where}.first_account_turn: must point at an agent turn")
    return problems


def problems_in(data: Any) -> list[str]:
    """Everything wrong with the contents of a wording file. Empty means it can be used."""
    expected = set(PAIR_POOLS) | set(SCENARIO_POOLS)
    if not isinstance(data, dict) or set(data) != expected:
        return [f"the file must be an object with exactly the keys {', '.join(sorted(expected))}"]
    problems: list[str] = []
    for pool, fewest in {**PAIR_POOLS, **SCENARIO_POOLS}.items():
        entries = data[pool]
        if not isinstance(entries, list) or len(entries) < fewest:
            problems.append(f"{pool}: needs a list of at least {fewest} entries")
            continue
        check = _pair_problems if pool in PAIR_POOLS else _scenario_problems
        for index, entry in enumerate(entries):
            problems += check(pool, index, entry)
        seen = [json.dumps(entry, sort_keys=True) for entry in entries]
        if len(set(seen)) != len(seen):
            problems.append(f"{pool}: the same entry appears twice")
    return problems


def _scenario(entry: Mapping[str, Any]) -> Scenario:
    body: tuple[Turn, ...] = tuple(
        (cast(Speaker, turn["speaker"]), str(turn["text"])) for turn in entry["body"]
    )
    issue = Issue(
        intro=(("customer", str(entry["intro"])),),
        body=body,
        resolution=cast(Resolution, entry["resolution"]),
    )
    return Scenario(str(entry["category"]), issue, entry.get("first_account_turn"))


def load_wording(path: Path) -> Wording:
    """Read a wording file.

    Raises:
        ValueError: If the file does not have the expected shape. The message
            names each place that is wrong and quotes none of the wording.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = problems_in(data)
    if problems:
        msg = f"{path.name} cannot be used:\n" + "\n".join(problems)
        raise ValueError(msg)
    return Wording(
        pairs={
            pool: tuple(Pair(entry["agent"], entry["customer"]) for entry in data[pool])
            for pool in PAIR_POOLS
        },
        account_scenarios=tuple(_scenario(entry) for entry in data["account_scenarios"]),
        general_scenarios=tuple(_scenario(entry) for entry in data["general_scenarios"]),
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Check one wording file and say what is wrong with it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    problems = problems_in(json.loads(args.path.read_text(encoding="utf-8")))
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print(f"{args.path.name} passes")


if __name__ == "__main__":
    main()
