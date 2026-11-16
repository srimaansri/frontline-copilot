"""The deterministic check that an answer's figures are in its evidence."""

import pytest

from copilot.claims import (
    Evidence,
    extract_claims,
    normal_number,
    same_claims,
    unsupported_claims,
)

ARTICLE = (
    "The Late Payment Fee is $5. It is added when a bill is more than 10 days past its due "
    "date. Call 611 from a Northline phone or 1-800-555-0199 from any phone. You can also "
    "check northline.example/outage. A voicemail PIN is 4 to 6 digits. Speeds may slow after "
    "35 GB. AutoPay takes 5% off."
)
PLAN_ROW = (
    '{"plan_id": "P3", "kind": "plan", "name": "Northline Everyday 5", '
    '"monthly_price_usd": 25.0, "billing_period": "monthly", "data_gb": 5.0, '
    '"hotspot_gb": 2, "international": "Not included"}'
)


def keys(text: str) -> list[tuple[str, str, str]]:
    return [claim.key for claim in extract_claims(text)]


# --- reading values out of text -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [("5", "5"), ("5.00", "5"), ("1,200", "1200"), ("12.50", "12.5"), ("0.5", "0.5")],
)
def test_numbers_are_compared_in_one_form(written: str, expected: str) -> None:
    assert normal_number(written) == expected


def test_each_kind_of_value_is_read() -> None:
    text = (
        "The fee is $5 after 10 days. Dial 611 or call 1-800-555-0199. "
        "See northline.example/outage. AutoPay takes 5% off. Data slows after 35 GB."
    )

    assert keys(text) == [
        ("money", "5", ""),
        ("quantity", "10", "day"),
        ("code", "611", ""),
        ("phone", "18005550199", ""),
        ("url", "northline.example/outage", ""),
        ("percent", "5", ""),
        ("quantity", "35", "gb"),
    ]


def test_money_is_read_with_commas_decimals_and_words() -> None:
    assert keys("It costs $1,200.50, or 25 dollars a month, or $ 15.") == [
        ("money", "1200.5", ""),
        ("money", "25", ""),
        ("money", "15", ""),
    ]


def test_a_range_is_two_claims_with_one_unit() -> None:
    for text in ("a 4-6 digit PIN", "a 4- to 6-digit PIN", "4 to 6 digits"):
        assert keys(text) == [("quantity", "4", "digit"), ("quantity", "6", "digit")], text


def test_digits_inside_an_address_or_a_phone_number_are_not_read_twice() -> None:
    assert keys("Call 1-800-555-0199.") == [("phone", "18005550199", "")]
    assert keys("Go to northline.example/plans/5gb.") == [
        ("url", "northline.example/plans/5gb", "")
    ]


def test_an_email_address_is_not_read_as_a_web_address() -> None:
    assert extract_claims("Write to help@northline.example or linda@mail.example.com.") == []


def test_list_numbers_citations_and_ids_are_not_claims() -> None:
    text = "1. Open the app [1].\n2. Tap Billing [2, 3].\nSee call T0007. Press and hold 1."

    assert extract_claims(text) == []


# --- looking values up in the evidence ----------------------------------------------------------


def test_an_answer_that_repeats_its_sources_has_nothing_unsupported() -> None:
    answer = (
        "The late-payment fee is **$5.00**. It is added after 10 days. Dial 611, or call "
        "1 (800) 555-0199 from any phone. Your PIN must be 4-6 digits. More at "
        "https://northline.example/outage."
    )

    assert unsupported_claims(answer, [ARTICLE]) == []


def test_a_changed_figure_is_reported_once() -> None:
    answer = "The late fee is $7. It is $7 every time. It is added after 10 days."

    missing = unsupported_claims(answer, [ARTICLE])

    assert [(claim.kind, claim.text) for claim in missing] == [("money", "$7")]


@pytest.mark.parametrize(
    ("answer", "kind"),
    [
        ("The fee is added after 15 days.", "quantity"),
        ("Data slows after 35 MB.", "quantity"),
        ("Call 1-800-555-0100.", "phone"),
        ("Dial 711 from your phone.", "code"),
        ("See northline.example/refunds.", "url"),
        ("AutoPay takes 10% off.", "percent"),
    ],
)
def test_each_kind_of_wrong_value_is_caught(answer: str, kind: str) -> None:
    missing = unsupported_claims(answer, [ARTICLE])

    assert [claim.kind for claim in missing] == [kind]


def test_a_number_must_match_in_kind_not_only_in_digits() -> None:
    # The article says "10 days" and "$5". It does not say "$10" or "5 days".
    missing = unsupported_claims("The fee is $10 and it is added after 5 days.", [ARTICLE])

    assert [claim.key for claim in missing] == [("money", "10", ""), ("quantity", "5", "day")]


def test_a_catalogue_row_supplies_the_dollar_sign_and_the_unit() -> None:
    answer = "Northline Everyday 5 is $25 a month with 5 GB of data and a 2 GB hotspot."

    assert unsupported_claims(answer, [PLAN_ROW]) == []
    assert [claim.text for claim in unsupported_claims("It is $30 with 10 GB.", [PLAN_ROW])] == [
        "$30",
        "10 GB",
    ]


def test_a_value_from_the_question_counts_as_given() -> None:
    answer = "Yes, the $12 charge can be reviewed."

    assert unsupported_claims(answer, [ARTICLE]) != []
    assert unsupported_claims(answer, [ARTICLE, "Can the $12 charge be reviewed?"]) == []


def test_with_no_evidence_every_value_is_unsupported() -> None:
    assert len(unsupported_claims("It is $5 after 10 days.", [])) == 2
    assert unsupported_claims("Hello! How can I help?", []) == []


def test_text_that_only_looks_like_a_row_is_ignored() -> None:
    evidence = Evidence(["{not json}", '["a list", 5]', '{"in_stock": true, "name": "x"}'])

    assert unsupported_claims("It is $5.", ["{not json}"]) != []
    assert not evidence.supports(extract_claims("It is $1.")[0])


# --- a rewrite must keep the figures ------------------------------------------------------------


def test_a_rewrite_that_keeps_every_figure_is_the_same() -> None:
    draft = "The late-payment fee is $5.00, applied after a period of 10 days."
    rewrite = "The late fee is $5. You get it after 10 days."

    assert same_claims(draft, rewrite)


@pytest.mark.parametrize(
    "rewrite",
    [
        "The late fee is $6. You get it after 10 days.",
        "The late fee is $5.",
        "The late fee is $5. You get it after 10 days. Call 611.",
    ],
)
def test_a_rewrite_that_changes_drops_or_adds_a_figure_is_not(rewrite: str) -> None:
    assert not same_claims("The late-payment fee is $5, applied after 10 days.", rewrite)
