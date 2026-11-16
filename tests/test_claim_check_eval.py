"""The measurement of the check on figures, on a small hand-made corpus."""

import random

from copilot.claims import extract_claims
from eval.claim_check_eval import changed_text, measure, mutants

ARTICLE = (
    "The Late Payment Fee is $5. It is added when a bill is more than 10 days past its due "
    "date. Call 611 or 1-800-555-0199. See northline.example/outage."
)
CORPUS = {
    "sources": {"a": ARTICLE, "q": "How much is the late fee?"},
    "rows": [
        {
            "id": "E001",
            "answer": "The late fee is $5, added after 10 days. Call 611 or 1-800-555-0199 [1].",
            "evidence": ["a", "q"],
        },
        {
            "id": "E002",
            "answer": "The fee is $5. Two late bills would be $10 [1].",
            "evidence": ["a", "q"],
        },
        {"id": "E003", "answer": "Hello! How can I help?", "evidence": ["q"]},
    ],
}


def test_every_kind_of_figure_can_be_changed_to_a_different_one() -> None:
    rng = random.Random(1)
    text = "It is $5.00 after 10 days, 5% off. Dial 611 or 1-800-555-0199. See northline.example/outage."

    for claim in extract_claims(text):
        changed = changed_text(claim, rng)
        assert changed is not None
        assert changed != claim.text, claim
    # Cents stay cents, so the changed answer still reads like the original.
    money = extract_claims("It is $5.00.")[0]
    assert changed_text(money, random.Random(2)).count(".") == 1  # type: ignore[union-attr]


def test_a_changed_figure_is_caught_unless_the_new_value_is_also_in_the_evidence() -> None:
    made = mutants(CORPUS["rows"][0]["answer"], [ARTICLE], random.Random(3))  # type: ignore[index]

    assert {mutant["kind"] for mutant in made} == {"money", "quantity", "code", "phone"}
    assert all(mutant["caught"] for mutant in made)
    # "$5" changed to "$10" would not be caught if the evidence also said "$10".
    widened = [ARTICLE + " The Reconnection Fee is $10."]
    uncaught = [
        mutant
        for seed in range(40)
        for mutant in mutants("The late fee is $5 [1].", widened, random.Random(seed))
        if not mutant["caught"]
    ]
    assert uncaught
    assert {mutant["to"] for mutant in uncaught} == {"$10"}


def test_the_measurement_counts_reports_on_real_answers_and_catches_on_changed_ones() -> None:
    result = measure(CORPUS)

    assert result["answers"] == 3
    assert result["answers_with_a_figure"] == 2
    # E001 states four figures, E002 states two of which "$10" is the model's own sum.
    assert result["figures_in_real_answers"] == 6
    assert result["reported_figures"] == [{"id": "E002", "kind": "money", "figure": "$10"}]
    assert result["reported_in_real_answers"]["count"] == 1
    assert result["real_answers_with_a_report"]["count"] == 1
    caught = result["changed_figures_caught"]
    assert caught["of"] > 0
    assert caught["count"] == caught["of"] - len(result["missed"])
    assert set(result["caught_by_kind"]) == {"money", "quantity", "code", "phone"}


def test_the_measurement_is_the_same_every_time() -> None:
    assert measure(CORPUS) == measure(CORPUS)
