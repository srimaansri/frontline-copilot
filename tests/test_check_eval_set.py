"""The checker for the extended evaluation set. Files only, no model calls."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from eval.check_eval_set import (
    EXTENDED_SET,
    MIN_COUNTS,
    catalogue_rows,
    check_row,
    check_set,
    collapse,
    load_articles,
    main,
    parse_lines,
    personal_details,
    question_key,
    quote_in_source,
    read_rows,
)

ARTICLES = {
    "set-up-voicemail": collapse("2. Press and hold the **1** key\n   until you hear a beep."),
    "number-lock": "It is a free feature that you control in the My Northline app.",
}
CATALOGUE = catalogue_rows()


def fact_row(**changes: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "E101",
        "category": "kb",
        "reviewed": False,
        "inputs": {"question": "how does cust start voicemail setup"},
        "expectations": {
            "expected_facts": ["Press and hold the 1 key"],
            "expected_source": "set-up-voicemail",
            "should_escalate": False,
            "expected_tool": "search_kb",
        },
        "stratum": "terse",
        "evidence": [{"source": "set-up-voicemail", "quote": "Press and hold the **1** key"}],
    }
    row.update(changes)
    return row


def rules_row(stratum: str, **expectations: Any) -> dict[str, Any]:
    return {
        "id": "E102",
        "category": "kb",
        "reviewed": False,
        "inputs": {"question": "Does Northline sell smartwatch plans?"},
        "expectations": {
            "should_escalate": False,
            "expected_tool": "search_kb",
            "guidelines": ["The response must say the help articles do not cover this"],
            **expectations,
        },
        "stratum": stratum,
        "evidence": [{"source": "none", "quote": "searched: smartwatch, wearable"}],
    }


def problems_of(row: dict[str, Any]) -> str:
    return " | ".join(check_row(row, ARTICLES, CATALOGUE))


def test_collapse_joins_lines_and_trims() -> None:
    assert collapse("  a\n\n  b\tc  ") == "a b c"


def test_catalogue_rows_read_like_the_csv_the_generator_writes() -> None:
    assert any(
        line.startswith("A04,addon,Hotspot Boost,10.00,monthly,,,10,,") for line in CATALOGUE
    )
    # A field that holds a comma is quoted, as the csv module writes it.
    assert any('"Covers loss, theft and damage.' in line for line in CATALOGUE)
    assert any(
        "P06,plan,Northline Unlimited Essentials,50.00,monthly,," in line for line in CATALOGUE
    )


def test_a_quote_matches_across_a_line_break_but_not_when_reworded() -> None:
    assert quote_in_source("set-up-voicemail", "key until  you hear", ARTICLES, CATALOGUE)
    assert not quote_in_source("set-up-voicemail", "Hold down the 1 key", ARTICLES, CATALOGUE)
    assert not quote_in_source("no-such-article", "Press and hold", ARTICLES, CATALOGUE)
    assert not quote_in_source("set-up-voicemail", "   ", ARTICLES, CATALOGUE)


def test_a_catalogue_quote_must_sit_inside_one_row() -> None:
    assert quote_in_source("plans", "Hotspot Boost,10.00,monthly", ARTICLES, CATALOGUE)
    assert not quote_in_source("plans", "Hotspot Boost,12.00,monthly", ARTICLES, CATALOGUE)
    # Each half is in the catalogue, but in different rows.
    assert not quote_in_source("plans", "Hotspot Boost,9.00,monthly", ARTICLES, CATALOGUE)


def test_personal_details_finds_phones_emails_and_card_digits() -> None:
    question = "Ana Diaz, 480-555-0111, ana.diaz@example.com, card ending 4471, has 2 lines"

    assert personal_details(question) == {"480-555-0111", "ana.diaz@example.com", "4471"}
    assert personal_details("How long is a PIN valid?") == set()


def test_parse_lines_reports_bad_json_and_blank_lines() -> None:
    rows, problems = parse_lines('{"id": "E101"}\n\nnot json\n[1]\n')

    assert rows == [{"id": "E101"}]
    assert [problem.split(":")[0] for problem in problems] == ["line 2", "line 3", "line 4"]


def test_read_rows_rejects_crlf_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "set.jsonl"
    path.write_bytes(b'{"id": "E101"}\r\n')

    rows, problems = read_rows(path)

    assert rows == [{"id": "E101"}]
    assert any("LF" in problem for problem in problems)


def test_a_well_formed_fact_row_has_no_problems() -> None:
    assert check_row(fact_row(), ARTICLES, CATALOGUE) == []


def test_a_quote_that_is_not_in_the_article_is_reported() -> None:
    row = fact_row(evidence=[{"source": "set-up-voicemail", "quote": "Press the 1 key twice"}])

    assert "not verbatim in 'set-up-voicemail'" in problems_of(row)


def test_every_fact_needs_its_own_evidence_entry() -> None:
    row = fact_row()
    row["expectations"]["expected_facts"].append("Choose a PIN")

    assert "2 expected facts but 1 evidence entries" in problems_of(row)


def test_more_than_four_facts_and_unknown_sources_are_reported() -> None:
    row = fact_row()
    row["expectations"]["expected_facts"] = ["a", "b", "c", "d", "e"]
    row["expectations"]["expected_source"] = "made-up-article"

    found = problems_of(row)

    assert "expected_facts must be 1 to 4" in found
    assert "expected_source 'made-up-article' is not an article slug" in found


def test_missing_and_unknown_keys_are_reported() -> None:
    row = fact_row(notes="x")
    del row["evidence"]

    assert problems_of(row) == "missing key 'evidence' | unknown key 'notes'"


def test_an_unanswerable_row_has_no_facts_and_names_what_was_searched() -> None:
    assert check_row(rules_row("unanswerable"), ARTICLES, CATALOGUE) == []

    with_fact = rules_row("unanswerable", expected_facts=["It costs $10"])
    assert "unanswerable rows have no expected_facts" in problems_of(with_fact)

    with_source = rules_row("unanswerable", expected_source="number-lock")
    assert "unanswerable rows have no expected_source" in problems_of(with_source)

    unsearched = rules_row("unanswerable")
    unsearched["evidence"] = []
    assert 'source "none"' in problems_of(unsearched)


def test_a_follow_up_row_needs_history_and_other_rows_must_not_have_it() -> None:
    history = [
        {"role": "user", "content": "How does voicemail setup start?"},
        {"role": "assistant", "content": "Press and hold the 1 key."},
    ]
    good = fact_row(stratum="follow_up", inputs={"history": history, "question": "And then?"})
    assert check_row(good, ARTICLES, CATALOGUE) == []

    assert "follow_up rows need inputs.history" in problems_of(fact_row(stratum="follow_up"))

    swapped = copy.deepcopy(good)
    swapped["inputs"]["history"].reverse()
    assert "history[0] must be a non-empty user turn" in problems_of(swapped)

    misplaced = fact_row(inputs={"history": history, "question": "And then?"})
    assert "only follow_up rows may have inputs.history" in problems_of(misplaced)


def test_a_hand_off_row_must_expect_escalation() -> None:
    row = rules_row("hand_off")
    row["evidence"] = []

    found = problems_of(row)

    assert "should_escalate must be true on hand_off rows" in found
    assert "hand_off rows expect the tool escalate_to_human" in found


def test_a_pii_row_must_not_repeat_the_personal_data_in_a_guideline() -> None:
    row = fact_row(
        stratum="pii_in_question",
        category="adversarial",
        inputs={"question": "Ana Diaz on 480-555-0111 asks how voicemail setup starts"},
    )
    row["expectations"]["guidelines"] = ["The response must not repeat any personal detail"]
    assert check_row(row, ARTICLES, CATALOGUE) == []

    row["expectations"]["guidelines"] = ["The response must not repeat 480-555-0111"]
    assert "a guideline repeats personal data" in problems_of(row)

    row["expectations"]["guidelines"] = ["The response must be short"]
    assert 'need a "must not repeat" guideline' in problems_of(row)


def test_a_multi_hop_row_needs_two_sources() -> None:
    one_source = fact_row(stratum="multi_hop")
    assert "at least two sources" in problems_of(one_source)

    two_sources = fact_row(stratum="multi_hop")
    two_sources["expectations"]["expected_facts"].append("Hotspot Boost is $10 a month")
    two_sources["evidence"].append({"source": "plans", "quote": "Hotspot Boost,10.00,monthly"})
    assert check_row(two_sources, ARTICLES, CATALOGUE) == []


def test_question_key_ignores_case_and_punctuation_and_includes_history() -> None:
    assert question_key({"inputs": {"question": "How long?"}}) == "how long"
    with_history = {
        "inputs": {"history": [{"role": "user", "content": "A refund."}], "question": "How long?"}
    }
    assert question_key(with_history) == "a refund how long"


def test_check_set_reports_id_clashes_repeated_questions_and_short_strata() -> None:
    base = [{"id": "E001", "inputs": {"question": "How does cust start voicemail setup?"}}]
    rows = [fact_row(), fact_row(), fact_row(id="E001")]

    found = " | ".join(check_set(rows, base, ARTICLES, CATALOGUE))

    assert "E101: id is used 2 times" in found
    assert "E001: id is already used in the base set" in found
    assert "E001: id must be E101 or higher" in found
    assert "E101: same question as E001 in the base set" in found
    assert "stratum terse: 3 rows, need at least 30" in found


def test_the_committed_set_passes_and_a_damaged_copy_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([]) == 0
    assert "OK" in capsys.readouterr().out

    rows, problems = read_rows(EXTENDED_SET)
    assert problems == []
    assert len(rows) >= sum(MIN_COUNTS.values())

    damaged = next(row for row in rows if row["evidence"] and row["stratum"] == "paraphrase")
    damaged["evidence"][0]["quote"] += " (reworded)"
    copy_path = tmp_path / "damaged.jsonl"
    copy_path.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode("utf-8"))

    assert main(["--path", str(copy_path)]) == 1
    assert f"{damaged['id']}: evidence[0] quote is not verbatim" in capsys.readouterr().err


def test_every_article_slug_in_the_articles_file_is_loaded() -> None:
    articles = load_articles()

    assert len(articles) == 87
    assert "set-up-voicemail" in articles
    assert all("\n" not in text for text in articles.values())
