"""Synthetic KB generator, tested with a fake model. No network access."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from data_gen.kb_topics import CARRIER_FACTS, SECTIONS, TOPICS, Topic
from data_gen.plans import PLANS
from data_gen.scrape_kb import article_id_for, write_articles
from data_gen.synth_kb import (
    DEFAULT_META,
    DEFAULT_OUT,
    MAX_ATTEMPTS,
    article_url,
    build_user_prompt,
    catalogue_text,
    clean_body,
    find_problems,
    generate,
    read_existing,
    unsupported_amounts,
    write_article,
)

FIXED_NOW = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
TOPIC = Topic("set-up-voicemail", "Set up voicemail", "Devices", "Press and hold the 1 key.")


def _good_body(title: str = "Set up voicemail") -> str:
    filler = " ".join(["Voicemail takes messages when you cannot answer the phone."] * 16)
    return (
        f"# {title}\n\nA short summary.\n\n## What you need\n\n{filler}\n\n"
        "## Steps\n\n1. Press and hold the 1 key.\n2. Choose a PIN.\n\n"
        "## Need more help?\n\nDial 611 from your Northline phone."
    )


class FakeChat:
    """Returns queued replies in order and records what it was asked."""

    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


# --- the topic list -----------------------------------------------------------------


def test_there_are_enough_topics_with_unique_slugs() -> None:
    slugs = [topic.slug for topic in TOPICS]

    assert len(TOPICS) >= 80
    assert len(slugs) == len(set(slugs))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) for slug in slugs)


def test_every_section_is_valid_and_used() -> None:
    assert {topic.section for topic in TOPICS} == set(SECTIONS)


def test_briefs_are_substantial() -> None:
    assert all(len(topic.brief.split()) >= 20 for topic in TOPICS)


def test_prices_in_briefs_exist_in_the_catalogue_or_are_known_policy() -> None:
    """A brief may only quote a dollar amount that the plan catalogue contains."""
    catalogue_prices = {f"${row.monthly_price_usd:.0f}" for row in PLANS}

    quoted = {price for topic in TOPICS for price in re.findall(r"\$\d+", topic.brief)}

    assert quoted <= catalogue_prices


# --- prompt building ------------------------------------------------------------------


def test_catalogue_lists_every_plan_with_its_price() -> None:
    text = catalogue_text()

    assert len(text.splitlines()) == len(PLANS)
    assert "Northline Unlimited Premium (plan): $65 a month; unlimited data; 30 GB hotspot" in text
    assert "International Day Pass (addon): $10 a day" in text
    assert "Activation Fee (fee): $35 one time" in text


def test_prompt_contains_title_brief_carrier_facts_and_catalogue() -> None:
    prompt = build_user_prompt(TOPIC)

    assert "Set up voicemail" in prompt
    assert TOPIC.brief in prompt
    assert all(fact in prompt for fact in CARRIER_FACTS)
    assert "Northline Talk (plan): $15 a month" in prompt


def test_article_url_uses_a_reserved_example_domain() -> None:
    assert article_url(TOPIC) == "https://help.northline.example/articles/set-up-voicemail"


# --- cleaning and validation --------------------------------------------------------------


def test_clean_body_replaces_the_models_title_with_the_exact_one() -> None:
    cleaned = clean_body("# Setting Up Your Voicemail!\n\nText.", TOPIC)

    assert cleaned.startswith("# Set up voicemail\n\nText.")


def test_clean_body_adds_a_missing_title() -> None:
    assert clean_body("Text only.", TOPIC) == "# Set up voicemail\n\nText only."


def test_clean_body_strips_a_wrapping_code_fence() -> None:
    cleaned = clean_body("```markdown\n# Set up voicemail\n\nText.\n```", TOPIC)

    assert cleaned == "# Set up voicemail\n\nText."


def test_clean_body_maps_typographic_punctuation_to_ascii() -> None:
    nb_hyphen, em_dash, right_quote, ellipsis = chr(0x2011), chr(0x2014), chr(0x2019), chr(0x2026)
    left_double, right_double, nbsp = chr(0x201C), chr(0x201D), chr(0x00A0)
    raw = (
        f"# T\n\nCall 1{nb_hyphen}800{nb_hyphen}555{nb_hyphen}0199 {em_dash} it{right_quote}s "
        f"free{ellipsis} {left_double}yes{right_double}{nbsp}ok   \nNext line."
    )

    cleaned = clean_body(raw, TOPIC)

    assert "1-800-555-0199" in cleaned
    assert cleaned.isascii()
    assert "it's free..." in cleaned
    # Trailing spaces at the end of a line are removed too.
    assert '"yes" ok\nNext line.' in cleaned


def test_leftover_non_ascii_is_reported_by_code_point() -> None:
    problems = find_problems(_good_body() + " caf" + chr(0x00E9))

    assert problems == ["contains non-ASCII characters: U+00E9"]


def test_amounts_from_the_brief_and_the_catalogue_are_supported() -> None:
    topic = Topic("x", "X", "Billing", "A deposit of $25 is needed.")
    body = "The deposit is $25. An Extra Line is $15.00 a month and activation is $35."

    assert unsupported_amounts(body, topic) == []


def test_invented_and_computed_amounts_are_reported() -> None:
    topic = Topic("x", "X", "Plans", "The pass is $10 a day.")
    body = "The pass is $10 a day, so two weeks costs $140. Premium support is $4.99."

    assert unsupported_amounts(body, topic) == ["$140", "$4.99"]


def test_write_article_rejects_an_invented_price() -> None:
    invented = _good_body() + " This service costs $7 a month."
    client = FakeChat([invented, _good_body()])

    article, problems = write_article(TOPIC, client, now=lambda: FIXED_NOW)

    assert article is not None
    assert problems == []
    assert "$7" not in article.body_text
    assert len(client.calls) == 2


def test_good_article_has_no_problems() -> None:
    assert find_problems(_good_body()) == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("# T\n\n## A\n\nshort\n\n## B\n\nDial 611.", "too short"),
        (_good_body() + " word" * 700, "too long"),
        (_good_body().replace("## Steps", "Steps"), None),
        (_good_body().replace("## What you need", "x").replace("## Steps", "y"),
         "fewer than two sections"),
        (_good_body() + "\n\n```\ncode\n```", "code fence"),
        (_good_body() + " See [the guide](x).", "bracketed"),
        (_good_body() + " As an AI, I cannot say.", "boilerplate"),
        (_good_body().replace("Dial 611 from your Northline phone.", "Call us."),
         "support contact"),
    ],
)  # fmt: skip
def test_problems_are_reported(body: str, expected: str | None) -> None:
    problems = find_problems(body)

    if expected is None:
        assert problems == []
    else:
        assert any(expected in problem for problem in problems)


# --- generation ----------------------------------------------------------------------------


def test_write_article_builds_a_synthetic_article() -> None:
    article, problems = write_article(TOPIC, FakeChat([_good_body()]), now=lambda: FIXED_NOW)

    assert problems == []
    assert article is not None
    assert article.synthetic is True
    assert article.section == "Devices"
    assert article.article_id == article_id_for(article_url(TOPIC))
    assert article.scraped_at == "2026-11-13T10:00:00Z"
    assert article.body_text.startswith("# Set up voicemail")


def test_write_article_retries_after_a_bad_reply_and_after_an_error() -> None:
    client = FakeChat(["too short", RuntimeError("boom"), _good_body()])

    article, problems = write_article(TOPIC, client, now=lambda: FIXED_NOW)

    assert article is not None
    assert problems == []
    assert len(client.calls) == 3


def test_write_article_gives_up_and_reports_why() -> None:
    client = FakeChat(["too short"])

    article, problems = write_article(TOPIC, client, now=lambda: FIXED_NOW)

    assert article is None
    assert any("too short" in problem for problem in problems)
    assert len(client.calls) == MAX_ATTEMPTS


def test_generate_keeps_topic_order_and_reports_failures() -> None:
    topics = [
        Topic("a-one", "One", "Billing", "x"),
        Topic("b-two", "Two", "Plans", "x"),
    ]

    class PerTopic:
        def complete(self, system: str, user: str) -> str:
            return _good_body("One") if "titled: One" in user else "bad"

    articles, failures = generate(topics, PerTopic(), {}, workers=2, now=lambda: FIXED_NOW)

    assert [article.title for article in articles] == ["One"]
    assert list(failures) == ["b-two"]


def test_generate_reuses_existing_articles_without_calling_the_model(tmp_path: Path) -> None:
    first, _ = generate([TOPIC], FakeChat([_good_body()]), {}, now=lambda: FIXED_NOW)
    out = tmp_path / "kb.jsonl"
    write_articles(out, first)
    client = FakeChat([_good_body()])

    second, failures = generate([TOPIC], client, read_existing(out), now=lambda: FIXED_NOW)

    assert second == first
    assert failures == {}
    assert client.calls == []


# --- the committed knowledge base ----------------------------------------------------------


def test_the_committed_knowledge_base_passes_the_generator_checks() -> None:
    """Guards hand corrections: an edited article must still pass what a generated one must."""
    by_slug = {
        article.url.rsplit("/", 1)[1]: article for article in read_existing(DEFAULT_OUT).values()
    }

    assert set(by_slug) == {topic.slug for topic in TOPICS}
    for topic in TOPICS:
        article = by_slug[topic.slug]
        assert article.title == topic.title, topic.slug
        assert article.section == topic.section, topic.slug
        assert article.synthetic is True
        assert find_problems(article.body_text) == [], topic.slug
        assert unsupported_amounts(article.body_text, topic) == [], topic.slug


def test_the_corrections_record_matches_the_metadata() -> None:
    record = DEFAULT_OUT.with_name("kb_corrections.jsonl")
    corrections = [
        json.loads(line) for line in record.read_text(encoding="utf-8").splitlines() if line
    ]
    meta = json.loads(DEFAULT_META.read_text(encoding="utf-8"))["corrections"]
    slugs = {topic.slug for topic in TOPICS}

    assert len(corrections) == meta["count"]
    assert len({item["slug"] for item in corrections}) == meta["articles_changed"]
    for item in corrections:
        assert set(item) == {
            "slug", "severity", "kind", "quote", "replacement", "reason", "reviewer",
        }  # fmt: skip
        assert item["slug"] in slugs
        assert item["severity"] in {"high", "medium", "low"}
        assert item["quote"]
        assert item["reason"]
        assert item["replacement"].isascii()


def test_read_existing_of_a_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_existing(tmp_path / "none.jsonl") == {}
