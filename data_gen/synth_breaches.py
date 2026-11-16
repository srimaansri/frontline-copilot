"""Generate labelled calls in which a compliance rule is, or is nearly, broken.

``synth_transcripts.py --seed 42`` writes T0001 to T0200, and in every one of
them the agent verifies the customer first and breaks no rule. This module
writes new calls, from T0201, with its own seed. Each call is one of:

* a breach: exactly one rule is broken, at one labelled turn;
* a hard negative: it looks close to a breach and is not one (the agent quotes
  a catalogue price before verifying, confirms only the last four digits of a
  card, says the billing team can waive a fee, asks for the last four of a
  Social Security number, or skips verification on a call that never opens the
  account);
* clean: an ordinary verified call.

The calls come in two halves. The development half is built from the wording in
``breach_wording_dev.json`` and the rules in ``copilot.compliance`` are tuned on
it. The held-out half is built from ``breach_wording_held_out.json``, which was
written without sight of the rules, and is scored once. Both halves also reuse
the 22 scenarios of ``transcript_templates.py``.

Nothing here changes what ``--seed 42`` produces: this module only reads the
existing templates and helpers.

Usage:
    python -m data_gen.synth_breaches
    python -m data_gen.synth_breaches --out-dir data/raw/compliance --seed 2718
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from random import Random
from typing import Any

from faker import Faker

from copilot.compliance import (
    RULE_CARD_READ_BACK,
    RULE_DISCLOSURE,
    RULE_FULL_SSN,
    RULE_PROMISE,
    RULE_SKIPPED,
)
from data_gen.breach_wording import (
    DEV_WORDING,
    HELD_OUT_WORDING,
    Pair,
    Scenario,
    Wording,
    load_wording,
)
from data_gen.synth_transcripts import (
    _START_DATE,
    _WINDOW_MINUTES,
    CALL_SHARE,
    _write_jsonl,
    build_persona,
    render,
)
from data_gen.transcript_templates import (
    CLOSINGS,
    ISSUES,
    OPENINGS,
    VERIFICATION,
    VERIFY_LEAD_IN,
    Turn,
)

DEFAULT_OUT_DIR = Path("data/raw/compliance")
BREACH_SEED = 2718
FIRST_ID = 201
SPLITS: tuple[tuple[str, Path], ...] = (("dev", DEV_WORDING), ("held_out", HELD_OUT_WORDING))

# For each scripted scenario, the turn of its body where the agent first reads
# from or changes the customer's account. Three scenarios never do: they are
# how-to help that could be given to anyone. Three are left out because a
# careful reader could argue either way (the agent only hands the request to
# another team, or only names a number to call back on).
SCRIPTED_FIRST_ACCOUNT_TURN: dict[str, int] = {
    "billing/0": 0,
    "billing/1": 0,
    "billing/2": 0,
    "troubleshooting/0": 6,
    "troubleshooting/2": 0,
    "device_setup/0": 4,
    "plan_change/0": 0,
    "plan_change/1": 0,
    "add_line/0": 8,
    "add_line/1": 4,
    "international/0": 4,
    "international/1": 0,
    "lost_stolen/0": 0,
    "lost_stolen/1": 2,
    "scam/0": 4,
    "scam/1": 4,
}
SCRIPTED_GENERAL: frozenset[str] = frozenset(
    {"troubleshooting/1", "device_setup/1", "accessibility/1"}
)
SCRIPTED_UNCLEAR: frozenset[str] = frozenset({"cancel_port/0", "cancel_port/1", "accessibility/0"})

# Scenarios whose first agent turn after verification states an account detail.
# Moving that turn in front of verification makes a disclosure breach.
_DISCLOSING_FIRST_TURN: tuple[str, ...] = (
    "billing/0",
    "billing/1",
    "billing/2",
    "troubleshooting/2",
    "plan_change/0",
    "plan_change/1",
    "international/1",
)
# Scenarios about a bill, a plan or usage. A disclosure or a catalogue price
# said before verification reads naturally in these.
_BILL_AND_PLAN: tuple[str, ...] = (*_DISCLOSING_FIRST_TURN, "cancel_port/0")
# The scenario in which the customer reads out a card number.
_PAYMENT = "billing/1"
_PAYMENT_CARD_TURN = 1
# The scripted late-fee call already has the agent decline to remove the fee.
_NO_PROMISE_HOST = "billing/2"

# Said in place of verification in some calls where it is skipped.
_NO_VERIFICATION_LINES: tuple[str, ...] = (
    "Let me pull up your account.",
    "One moment while I open your account.",
    "Sure, I can help with that.",
)


@dataclass(frozen=True)
class CallLabel:
    """What one generated call is, for scoring the compliance checker."""

    transcript_id: str
    split: str
    # The rule that is broken, or ``None`` for a hard negative or a clean call.
    rule: str | None
    # The agent turn at which it is broken.
    turn_index: int | None
    variant: str
    # ``billing/1`` for a scripted scenario, ``new/account/3`` for one from the wording file.
    scenario: str
    # ``promise/4``: the list and entry of the wording file that was used, if any.
    wording: str | None


@dataclass(frozen=True)
class _Host:
    key: str
    scenario: Scenario


@dataclass(frozen=True)
class _Plan:
    """One call to build: what kind, on which scenario, with which wording."""

    variant: str
    rule: str | None
    host: _Host
    pair: Pair | None = None
    wording: str | None = None


def _hosts(wording: Wording) -> dict[str, _Host]:
    hosts: dict[str, _Host] = {}
    for category, issues in ISSUES.items():
        for number, issue in enumerate(issues):
            key = f"{category}/{number}"
            hosts[key] = _Host(key, Scenario(category, issue, SCRIPTED_FIRST_ACCOUNT_TURN.get(key)))
    for number, scenario in enumerate(wording.account_scenarios):
        hosts[f"new/account/{number}"] = _Host(f"new/account/{number}", scenario)
    for number, scenario in enumerate(wording.general_scenarios):
        hosts[f"new/general/{number}"] = _Host(f"new/general/{number}", scenario)
    return hosts


def _plans(wording: Wording, rng: Random) -> list[_Plan]:
    """Decide every call of one half. Each entry of the wording file is used once."""
    hosts = _hosts(wording)
    account = [
        host
        for host in hosts.values()
        if host.scenario.first_account_turn is not None and host.key not in SCRIPTED_UNCLEAR
    ]
    general = [
        host
        for key, host in hosts.items()
        if key in SCRIPTED_GENERAL or key.startswith("new/general/")
    ]
    bill_and_plan = [hosts[key] for key in _BILL_AND_PLAN]
    promise_hosts = [host for host in hosts.values() if host.key != _NO_PROMISE_HOST]
    everything = list(hosts.values())

    def from_pool(
        pool: str, variant: str, rule: str | None, choices: Sequence[_Host]
    ) -> list[_Plan]:
        return [
            _Plan(variant, rule, rng.choice(choices), pair, f"{pool}/{number}")
            for number, pair in enumerate(wording.pairs[pool])
        ]

    plans = [
        *from_pool("disclosure", "disclosure_inserted", RULE_DISCLOSURE, bill_and_plan),
        *(_Plan("disclosure_moved", RULE_DISCLOSURE, hosts[key]) for key in _DISCLOSING_FIRST_TURN),
        *from_pool("catalogue", "catalogue_before_verification", None, bill_and_plan),
        *(_Plan("verification_skipped", RULE_SKIPPED, host) for host in account),
        *(_Plan("general_no_verification", None, host) for host in general),
        *from_pool("card_read_back", "card_read_back", RULE_CARD_READ_BACK, [hosts[_PAYMENT]]),
        *from_pool("card_safe", "card_not_repeated", None, [hosts[_PAYMENT]]),
        *from_pool("promise", "unauthorized_promise", RULE_PROMISE, promise_hosts),
        *from_pool("promise_safe", "billing_team_decides", None, promise_hosts),
        *from_pool("full_ssn", "full_ssn_requested", RULE_FULL_SSN, everything),
        *from_pool("ssn_safe", "last_four_only", None, everything),
        *(_Plan("clean", None, host) for host in everything),
    ]
    rng.shuffle(plans)
    return plans


def _verification(rng: Random) -> list[Turn]:
    """The lead-in and two or three identity questions, as the scripted calls have them."""
    turns: list[Turn] = [("agent", rng.choice(VERIFY_LEAD_IN))]
    for item in rng.sample(sorted(VERIFICATION), rng.choice((2, 2, 3))):
        question, answer = rng.choice(VERIFICATION[item])
        turns += [("agent", question), ("customer", answer)]
    return turns


def _verification_with(rng: Random, special: Pair) -> tuple[list[Turn], int]:
    """Identity questions with ``special`` among them, and the index of its question.

    ``special`` is a question about the Social Security number from the wording
    file. It stands beside two ordinary questions about other things, so the
    customer is verified whatever they answer to it.
    """
    items = rng.sample(sorted(set(VERIFICATION) - {"ssn_last4"}), 2)
    pairs = [rng.choice(VERIFICATION[item]) for item in items]
    position = rng.randrange(len(pairs) + 1)
    pairs.insert(position, (special.agent, special.customer))
    turns: list[Turn] = [("agent", rng.choice(VERIFY_LEAD_IN))]
    for question, answer in pairs:
        turns += [("agent", question), ("customer", answer)]
    return turns, 1 + 2 * position


def _pair(plan: _Plan) -> Pair:
    if plan.pair is None:
        msg = f"a {plan.variant} call needs an entry from the wording file"
        raise ValueError(msg)
    return plan.pair


def _compose(plan: _Plan, channel: str, rng: Random) -> tuple[list[Turn], int | None]:
    """The turns of one call, and the index of the turn that breaks the rule."""
    issue = plan.host.scenario.issue
    body = list(issue.body)
    turns: list[Turn] = [*rng.choice(OPENINGS[channel]), *issue.intro]
    marked: int | None = None
    variant = plan.variant

    if variant in {"disclosure_inserted", "catalogue_before_verification"}:
        pair = _pair(plan)
        marked = len(turns)
        turns += [("agent", pair.agent), ("customer", pair.customer)]
        turns += _verification(rng)
        turns += body
    elif variant == "disclosure_moved":
        marked = len(turns)
        turns += body[:2]
        turns += _verification(rng)
        turns += body[2:]
    elif variant in {"verification_skipped", "general_no_verification"}:
        if rng.random() < 0.5:
            # On a how-to call the agent never says they are opening the account.
            lines = _NO_VERIFICATION_LINES if plan.rule else _NO_VERIFICATION_LINES[-1:]
            turns.append(("agent", rng.choice(lines)))
        first = plan.host.scenario.first_account_turn
        marked = None if first is None else len(turns) + first
        turns += body
    elif variant in {"card_read_back", "card_not_repeated"}:
        pair = _pair(plan)
        turns += _verification(rng)
        turns += body[: _PAYMENT_CARD_TURN + 1]
        marked = len(turns)
        turns += [("agent", pair.agent), ("customer", pair.customer)]
        turns += body[_PAYMENT_CARD_TURN + 1 :]
    elif variant in {"unauthorized_promise", "billing_team_decides"}:
        pair = _pair(plan)
        turns += _verification(rng)
        turns += body
        turns.append(("customer", pair.customer))
        marked = len(turns)
        turns.append(("agent", pair.agent))
    elif variant in {"full_ssn_requested", "last_four_only"}:
        questions, special_turn = _verification_with(rng, _pair(plan))
        marked = len(turns) + special_turn
        turns += questions
        turns += body
    elif variant == "clean":
        turns += _verification(rng)
        turns += body
    else:
        msg = f"unknown variant {variant!r}"
        raise ValueError(msg)

    turns += rng.choice(CLOSINGS[channel][issue.resolution])
    return turns, marked if plan.rule is not None else None


def _values(fake: Faker) -> dict[str, str]:
    persona = build_persona(fake)
    digits = "".join(char for char in persona["credit_card"] if char.isdigit())
    return {**persona, "card_last4": digits[-4:]}


def build_call(
    transcript_id: str, split: str, plan: _Plan, fake: Faker
) -> tuple[dict[str, Any], CallLabel]:
    """Build one call in the shape of ``synth_transcripts.build_transcript``, and its label."""
    rng = fake.random
    channel = "call" if rng.random() < CALL_SHARE else "chat"
    values = _values(fake)
    templates, marked = _compose(plan, channel, rng)
    turns: list[dict[str, str]] = []
    for speaker, template in templates:
        # ``card_last4`` is not a slot the shared renderer knows, so it is filled first.
        text, _ = render(template.replace("{card_last4}", values["card_last4"]), values)
        turns.append({"speaker": speaker, "text": text})
    created = _START_DATE + timedelta(minutes=rng.randrange(_WINDOW_MINUTES))
    record = {
        "transcript_id": transcript_id,
        "channel": channel,
        "category": plan.host.scenario.category,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "turns": turns,
        "resolution": plan.host.scenario.issue.resolution,
    }
    label = CallLabel(
        transcript_id, split, plan.rule, marked, plan.variant, plan.host.key, plan.wording
    )
    return record, label


def generate(
    seed: int = BREACH_SEED, splits: Sequence[tuple[str, Path]] = SPLITS
) -> tuple[list[dict[str, Any]], list[CallLabel]]:
    """Generate both halves. Ids run on from ``T0201``, the development half first.

    Each half has its own random stream, seeded from ``seed`` and its position,
    so editing one wording file does not change the values in the other half.
    """
    transcripts: list[dict[str, Any]] = []
    labels: list[CallLabel] = []
    for position, (split, path) in enumerate(splits):
        fake = Faker("en_US")
        fake.seed_instance(seed + position)
        for plan in _plans(load_wording(path), fake.random):
            transcript_id = f"T{FIRST_ID + len(transcripts):04d}"
            record, label = build_call(transcript_id, split, plan, fake)
            transcripts.append(record)
            labels.append(label)
    return transcripts, labels


def write_outputs(
    out_dir: Path, transcripts: Sequence[Mapping[str, Any]], labels: Sequence[CallLabel]
) -> None:
    """Write ``transcripts.jsonl`` and ``compliance_labels.jsonl`` into ``out_dir``."""
    _write_jsonl(out_dir / "transcripts.jsonl", transcripts)
    _write_jsonl(out_dir / "compliance_labels.jsonl", (asdict(label) for label in labels))


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=BREACH_SEED)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    if args.out_dir.resolve() == Path("data/raw").resolve():
        parser.error("data/raw holds the seed 42 transcripts; write these somewhere else")
    transcripts, labels = generate(args.seed)
    write_outputs(args.out_dir, transcripts, labels)
    breaches = sum(label.rule is not None for label in labels)
    # Counts only: transcript text is never printed.
    print(
        f"seed {args.seed}: wrote {len(transcripts)} calls ({breaches} with a breach) "
        f"and their labels to {args.out_dir}"
    )


if __name__ == "__main__":
    main()
