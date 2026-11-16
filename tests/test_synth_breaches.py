"""The breach generator: its labels, its determinism, and that seed 42 is untouched.

Nothing here prints or asserts on a line of the held-out wording file. The
checks on it are about shape only.
"""

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from random import Random
from typing import Any

import pytest

from copilot.compliance import (
    RULE_CARD_READ_BACK,
    RULE_DISCLOSURE,
    RULE_FULL_SSN,
    RULE_PROMISE,
    RULE_SKIPPED,
    RULES,
)
from data_gen import synth_breaches, synth_transcripts
from data_gen.breach_wording import (
    DEV_WORDING,
    HELD_OUT_WORDING,
    PAIR_POOLS,
    load_wording,
    problems_in,
)
from data_gen.breach_wording import main as check_wording_file
from data_gen.synth_breaches import BREACH_SEED, CallLabel, generate, write_outputs
from data_gen.transcript_templates import ISSUES, VERIFICATION, VERIFY_LEAD_IN

# SHA-256 of the files ``python -m data_gen.synth_transcripts --seed 42`` wrote
# before the breach generator existed. Every published redaction and evaluation
# number rests on these bytes.
SEED_42_TRANSCRIPTS = "dd044ca9847155f8eec593ec75f74aab42ecc65a8cd326f50ec7c3fcc7306aa9"
SEED_42_LABELS = "3244167250109ef23944dcdb49ce8103f76dc428e72b0d8886a06abb058bee20"

HARD_NEGATIVES = {
    "catalogue_before_verification",
    "card_not_repeated",
    "billing_team_decides",
    "last_four_only",
    "general_no_verification",
}


@pytest.fixture(scope="module")
def generated() -> tuple[list[dict[str, Any]], list[CallLabel]]:
    return generate()


@pytest.fixture(scope="module")
def by_id(generated: tuple[list[dict[str, Any]], list[CallLabel]]) -> dict[str, dict[str, Any]]:
    return {transcript["transcript_id"]: transcript for transcript in generated[0]}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- seed 42 -------------------------------------------------------------------------


def test_seed_42_output_is_byte_identical_to_the_published_files(tmp_path: Path) -> None:
    # Generating the breach calls first shows they do not disturb the other generator.
    generate()

    synth_transcripts.main(["--seed", "42", "--out-dir", str(tmp_path)])

    assert _sha256(tmp_path / "transcripts.jsonl") == SEED_42_TRANSCRIPTS
    assert _sha256(tmp_path / "pii_labels.jsonl") == SEED_42_LABELS


def test_the_generator_refuses_to_write_over_the_seed_42_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        synth_breaches.main(["--out-dir", "data/raw"])

    assert not (tmp_path / "data").exists()


# --- ids, determinism, files -----------------------------------------------------------


def test_generation_is_deterministic(
    generated: tuple[list[dict[str, Any]], list[CallLabel]],
) -> None:
    assert generate() == generated
    assert generate(BREACH_SEED + 1)[0] != generated[0]


def test_ids_run_on_from_t0201_with_the_development_half_first(
    generated: tuple[list[dict[str, Any]], list[CallLabel]],
) -> None:
    transcripts, labels = generated
    ids = [transcript["transcript_id"] for transcript in transcripts]

    assert ids == [f"T{number:04d}" for number in range(201, 201 + len(ids))]
    assert [label.transcript_id for label in labels] == ids
    splits = [label.split for label in labels]
    assert splits == sorted(splits)
    assert set(splits) == {"dev", "held_out"}


def test_records_have_the_shape_of_the_seed_42_records(
    generated: tuple[list[dict[str, Any]], list[CallLabel]],
) -> None:
    original = synth_transcripts.generate(42, count=1)[0][0]

    for transcript in generated[0]:
        assert list(transcript) == list(original)
        assert transcript["channel"] in {"call", "chat"}
        for turn in transcript["turns"]:
            assert set(turn) == {"speaker", "text"}
            assert "{" not in turn["text"]
            assert "}" not in turn["text"]


def test_write_outputs_and_the_command_line(
    tmp_path: Path,
    generated: tuple[list[dict[str, Any]], list[CallLabel]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    transcripts, labels = generated

    synth_breaches.main(["--out-dir", str(tmp_path)])

    lines = (tmp_path / "compliance_labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(labels)
    assert json.loads(lines[0]) == vars(labels[0])
    written = (tmp_path / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in written] == transcripts
    out = capsys.readouterr().out
    assert f"wrote {len(transcripts)} calls" in out
    # Counts only: nothing a customer or agent says is printed.
    assert not any(turn["text"] in out for turn in transcripts[0]["turns"])

    other = tmp_path / "again"
    write_outputs(other, transcripts, labels)
    assert _sha256(other / "transcripts.jsonl") == _sha256(tmp_path / "transcripts.jsonl")


# --- labels -------------------------------------------------------------------------------


def test_a_breach_names_one_rule_and_an_agent_turn_and_nothing_else_is_labelled(
    generated: tuple[list[dict[str, Any]], list[CallLabel]], by_id: dict[str, dict[str, Any]]
) -> None:
    for label in generated[1]:
        turns = by_id[label.transcript_id]["turns"]
        if label.rule is None:
            assert label.turn_index is None
            assert label.variant == "clean" or label.variant in HARD_NEGATIVES
        else:
            assert label.rule in RULES
            assert label.turn_index is not None
            assert turns[label.turn_index]["speaker"] == "agent"


def test_each_half_has_every_rule_every_near_miss_and_clean_calls(
    generated: tuple[list[dict[str, Any]], list[CallLabel]],
) -> None:
    for split in ("dev", "held_out"):
        labels = [label for label in generated[1] if label.split == split]
        per_rule = Counter(label.rule for label in labels if label.rule)

        assert set(per_rule) == set(RULES)
        assert min(per_rule.values()) >= 20
        assert {label.variant for label in labels} >= HARD_NEGATIVES | {"clean"}


def test_every_entry_of_a_wording_file_is_used_exactly_once(
    generated: tuple[list[dict[str, Any]], list[CallLabel]],
) -> None:
    for split, path in (("dev", DEV_WORDING), ("held_out", HELD_OUT_WORDING)):
        wording = load_wording(path)
        used = Counter(label.wording for label in generated[1] if label.split == split)
        del used[None]
        expected = {
            f"{pool}/{number}" for pool in PAIR_POOLS for number in range(len(wording.pairs[pool]))
        }

        assert set(used) == expected
        assert set(used.values()) == {1}


def _is_identity_question(text: str) -> bool:
    questions = {question for pairs in VERIFICATION.values() for question, _ in pairs}
    return text in questions or text in VERIFY_LEAD_IN


def test_a_skipped_call_has_no_identity_question_and_marks_the_first_account_turn(
    generated: tuple[list[dict[str, Any]], list[CallLabel]], by_id: dict[str, dict[str, Any]]
) -> None:
    skipped = [label for label in generated[1] if label.rule == RULE_SKIPPED]

    assert {label.scenario for label in skipped} >= set(synth_breaches.SCRIPTED_FIRST_ACCOUNT_TURN)
    for label in skipped:
        turns = by_id[label.transcript_id]["turns"]
        assert not any(_is_identity_question(turn["text"]) for turn in turns)
    # The scripted pay-by-phone call opens with the balance.
    pay = next(label for label in skipped if label.scenario == "billing/1")
    assert pay.turn_index is not None
    text = by_id[pay.transcript_id]["turns"][pay.turn_index]["text"]
    assert text.startswith("Your balance due is $")


def test_a_how_to_call_with_no_verification_is_not_a_breach(
    generated: tuple[list[dict[str, Any]], list[CallLabel]], by_id: dict[str, dict[str, Any]]
) -> None:
    general = [label for label in generated[1] if label.variant == "general_no_verification"]

    assert {label.scenario for label in general} >= synth_breaches.SCRIPTED_GENERAL
    assert not {label.scenario for label in general} & synth_breaches.SCRIPTED_UNCLEAR
    for label in general:
        assert label.rule is None
        turns = by_id[label.transcript_id]["turns"]
        assert not any(_is_identity_question(turn["text"]) for turn in turns)
        # The agent never says they are opening the account.
        opens_account = set(synth_breaches._NO_VERIFICATION_LINES[:2])
        assert not any(turn["text"] in opens_account for turn in turns)


def test_a_disclosure_comes_before_the_first_identity_question(
    generated: tuple[list[dict[str, Any]], list[CallLabel]], by_id: dict[str, dict[str, Any]]
) -> None:
    disclosures = [label for label in generated[1] if label.rule == RULE_DISCLOSURE]

    assert {label.variant for label in disclosures} == {"disclosure_inserted", "disclosure_moved"}
    for label in [*disclosures, *(x for x in generated[1] if x.variant == "clean")]:
        turns = by_id[label.transcript_id]["turns"]
        first_question = next(
            index for index, turn in enumerate(turns) if _is_identity_question(turn["text"])
        )
        if label.rule is None:
            assert first_question == 4
        else:
            assert label.turn_index is not None
            assert label.turn_index < first_question


def _card_number(turns: list[dict[str, str]]) -> str:
    opening = "My Visa. The number is "
    given = next(turn["text"] for turn in turns if turn["text"].startswith(opening))
    return given.removeprefix(opening).removesuffix(".")


def test_a_card_is_read_back_only_in_the_calls_labelled_so(
    generated: tuple[list[dict[str, Any]], list[CallLabel]], by_id: dict[str, dict[str, Any]]
) -> None:
    for label in generated[1]:
        if label.variant not in {"card_read_back", "card_not_repeated"}:
            continue
        turns = by_id[label.transcript_id]["turns"]
        card = _card_number(turns)
        said_by_agent = [
            index
            for index, turn in enumerate(turns)
            if turn["speaker"] == "agent" and card in turn["text"]
        ]
        if label.rule == RULE_CARD_READ_BACK:
            assert said_by_agent == [label.turn_index]
        else:
            assert said_by_agent == []


def test_a_promise_follows_the_customers_request_near_the_end(
    generated: tuple[list[dict[str, Any]], list[CallLabel]], by_id: dict[str, dict[str, Any]]
) -> None:
    promises = [label for label in generated[1] if label.rule == RULE_PROMISE]

    assert "billing/2" not in {label.scenario for label in promises}
    for label in promises:
        turns = by_id[label.transcript_id]["turns"]
        assert label.turn_index is not None
        assert turns[label.turn_index - 1]["speaker"] == "customer"
        assert len(turns) - label.turn_index <= 3


def test_a_full_number_request_sits_among_ordinary_identity_questions(
    generated: tuple[list[dict[str, Any]], list[CallLabel]], by_id: dict[str, dict[str, Any]]
) -> None:
    for label in generated[1]:
        if label.rule != RULE_FULL_SSN:
            continue
        turns = by_id[label.transcript_id]["turns"]
        assert label.turn_index is not None
        ordinary = [turn for turn in turns if _is_identity_question(turn["text"])]
        # The lead-in and two questions about something other than the Social.
        assert len(ordinary) == 3
        assert not any("ocial" in turn["text"] or "SSN" in turn["text"] for turn in ordinary)
        assert 4 < label.turn_index < 10


def test_the_scripted_account_table_points_at_agent_turns() -> None:
    known = {
        f"{category}/{number}"
        for category, issues in ISSUES.items()
        for number in range(len(issues))
    }
    tables = (
        set(synth_breaches.SCRIPTED_FIRST_ACCOUNT_TURN),
        set(synth_breaches.SCRIPTED_GENERAL),
        set(synth_breaches.SCRIPTED_UNCLEAR),
    )

    assert set().union(*tables) == known
    assert sum(len(table) for table in tables) == len(known)
    for key, turn in synth_breaches.SCRIPTED_FIRST_ACCOUNT_TURN.items():
        category, number = key.split("/")
        assert ISSUES[category][int(number)].body[turn][0] == "agent"


# --- the wording files --------------------------------------------------------------------


def test_both_committed_wording_files_pass_the_check(capsys: pytest.CaptureFixture[str]) -> None:
    for path in (DEV_WORDING, HELD_OUT_WORDING):
        check_wording_file([str(path)])

    assert capsys.readouterr().out.splitlines() == [
        "breach_wording_dev.json passes",
        "breach_wording_held_out.json passes",
    ]


@pytest.fixture
def dev_data() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(DEV_WORDING.read_text(encoding="utf-8"))
    return copy.deepcopy(data)


@pytest.mark.parametrize(
    ("pool", "field", "value", "problem"),
    [
        ("disclosure", "agent", "Your bill is {bil_amount}.", "unknown slot"),
        ("disclosure", "agent", "Let me pull that up for you.", "states no account detail"),
        ("disclosure", "agent", "I see you owe $84.12 and your number is 480-555-0132.", "literal"),
        ("promise", "agent", "I sent it to linda@example.com.", "literal"),
        ("promise", "customer", "", "must be a line of text"),
        ("promise", "agent", "x" * 400, "longer than"),
        ("promise", "agent", "I waived it {", "brace"),
        ("catalogue", "agent", "Your {plan_name} plan is {plan_price} a month.", "not public"),
        ("card_read_back", "agent", "Thank you, I have it.", "does not repeat"),
        ("card_safe", "agent", "So that's {credit_card}?", "repeats"),
    ],
)
def test_a_bad_line_is_reported_without_being_quoted(
    dev_data: dict[str, Any], pool: str, field: str, value: str, problem: str
) -> None:
    dev_data[pool][0][field] = value

    problems = problems_in(dev_data)

    assert len(problems) >= 1
    assert problem in problems[0]
    assert problems[0].startswith(f"{pool}[0]")
    assert not value or value not in "\n".join(problems)


def test_a_file_with_the_wrong_shape_is_reported(dev_data: dict[str, Any]) -> None:
    assert "exactly the keys" in problems_in({"promise": []})[0]
    assert "exactly the keys" in problems_in([])[0]

    dev_data["promise"] = dev_data["promise"][:3]
    dev_data["card_safe"].append(dev_data["card_safe"][0])
    dev_data["ssn_safe"][0] = {"agent": "Last four?"}
    problems = problems_in(dev_data)

    assert "promise: needs a list of at least 20 entries" in problems
    assert "card_safe: the same entry appears twice" in problems
    assert "ssn_safe[0]: must have exactly the keys agent and customer" in problems


@pytest.mark.parametrize(
    ("pool", "change", "problem"),
    [
        ("account_scenarios", {"category": "weather"}, "category"),
        ("account_scenarios", {"resolution": "done"}, "resolution"),
        ("account_scenarios", {"first_account_turn": 1}, "must point at an agent turn"),
        ("account_scenarios", {"first_account_turn": 40}, "not the index of a turn"),
        ("account_scenarios", {"body": []}, "4 to 10 turns"),
        ("general_scenarios", {"resolution": "escalated"}, "not escalated"),
        ("general_scenarios", {"first_account_turn": 0}, "exactly the keys"),
    ],
)
def test_a_bad_scenario_is_reported(
    dev_data: dict[str, Any], pool: str, change: dict[str, Any], problem: str
) -> None:
    dev_data[pool][0].update(change)

    assert problem in "\n".join(problems_in(dev_data))


def test_a_scenario_turn_is_checked(dev_data: dict[str, Any]) -> None:
    dev_data["account_scenarios"][0]["body"][0]["speaker"] = "customer"
    dev_data["account_scenarios"][1]["body"][1] = {"speaker": "robot", "text": "Beep."}
    dev_data["account_scenarios"][2]["body"][1] = {"text": "No speaker."}
    dev_data["general_scenarios"][0]["body"][0]["text"] = "Your bill is {bill_amount}."
    problems = "\n".join(problems_in(dev_data))

    assert "account_scenarios[0].body[0]: the agent speaks first" in problems
    assert "account_scenarios[1].body[1].speaker: must be agent or customer" in problems
    assert "account_scenarios[2].body[1]: must have exactly the keys speaker and text" in problems
    assert "general_scenarios[0].body[0]: the agent states an account detail" in problems


def test_a_file_that_fails_cannot_be_loaded_or_pass_the_command(
    tmp_path: Path, dev_data: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    dev_data["promise"][0]["agent"] = "I sent it to {nobody}."
    path = tmp_path / "wording.json"
    path.write_text(json.dumps(dev_data), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown slot nobody"):
        load_wording(path)
    with pytest.raises(SystemExit):
        check_wording_file([str(path)])
    assert "promise[0].agent: unknown slot nobody" in capsys.readouterr().out


def test_a_call_that_needs_wording_fails_without_it() -> None:
    wording = load_wording(DEV_WORDING)
    host = synth_breaches._hosts(wording)["billing/1"]
    plan = synth_breaches._Plan("card_read_back", RULE_CARD_READ_BACK, host)
    unknown = synth_breaches._Plan("something_else", None, host)
    rng = Random(1)

    with pytest.raises(ValueError, match="needs an entry"):
        synth_breaches._compose(plan, "call", rng)
    with pytest.raises(ValueError, match="unknown variant"):
        synth_breaches._compose(unknown, "call", rng)
