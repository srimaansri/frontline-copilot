"""KB scraper: politeness rules and extraction, with no real network access."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from data_gen.scrape_kb import (
    PoliteFetcher,
    article_id_for,
    assign_section,
    extract_article,
    links_under_prefix,
    read_seed_urls,
    scrape,
    write_articles,
)

BASE = "https://help.example.com"
ARTICLE_HTML = """
<html><head><title>Set up voicemail</title></head><body>
<nav><a href="/help/">Help home</a></nav>
<article>
<h1>Set up voicemail</h1>
<p>Voicemail lets callers leave a message when you cannot answer your phone.
Setting it up takes about two minutes on most phones and only has to be done once.</p>
<h2>On an iPhone</h2>
<p>Open the Phone app, tap Voicemail, then tap Set Up Now. Create a password and
record a greeting for your callers to hear when you are away.</p>
</article></body></html>
"""
INDEX_HTML = """
<html><body>
<a href="/help/voicemail">Voicemail</a>
<a href="/help/billing/pay#top">Pay a bill</a>
<a href="/shop/phones">Shop</a>
<a href="https://other.example.org/help/x">Elsewhere</a>
<a href="mailto:help@example.com">Email</a>
</body></html>
"""
FIXED_NOW = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)


class FakeSite:
    """A tiny in-memory website that records what was requested."""

    def __init__(self, robots: str = "User-agent: *\nAllow: /\n", robots_status: int = 200) -> None:
        self.robots = robots
        self.robots_status = robots_status
        self.requested: list[str] = []
        self.user_agents: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requested.append(request.url.path)
        self.user_agents.add(request.headers["user-agent"])
        if request.url.path == "/robots.txt":
            return httpx.Response(self.robots_status, text=self.robots)
        if request.url.path == "/help/":
            return httpx.Response(200, text=INDEX_HTML, headers={"content-type": "text/html"})
        if request.url.path == "/help/missing":
            return httpx.Response(404, text="not found", headers={"content-type": "text/html"})
        if request.url.path == "/help/file.pdf":
            return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
        return httpx.Response(200, text=ARTICLE_HTML, headers={"content-type": "text/html"})


def _fetcher(site: FakeSite, cache_dir: Path, sleeps: list[float]) -> PoliteFetcher:
    client = httpx.Client(transport=httpx.MockTransport(site.handler))
    return PoliteFetcher(client, cache_dir, user_agent="test-agent/1.0", sleep=sleeps.append)


# --- pure helpers --------------------------------------------------------------------


def test_article_id_is_stable_and_short() -> None:
    assert article_id_for(f"{BASE}/help/voicemail") == article_id_for(f"{BASE}/help/voicemail")
    assert article_id_for(f"{BASE}/help/voicemail") != article_id_for(f"{BASE}/help/other")
    assert len(article_id_for(f"{BASE}/help/voicemail")) == 12


def test_seed_file_skips_comments_blanks_and_duplicates(tmp_path: Path) -> None:
    seed = tmp_path / "seed.txt"
    seed.write_text(f"# header\n\n{BASE}/a\n  {BASE}/b  \n{BASE}/a\n", encoding="utf-8")

    assert read_seed_urls(seed) == [f"{BASE}/a", f"{BASE}/b"]


def test_missing_seed_file_gives_no_urls(tmp_path: Path) -> None:
    assert read_seed_urls(tmp_path / "nope.txt") == []


@pytest.mark.parametrize(
    ("title", "body", "expected"),
    [
        ("How to pay your bill", "You can pay online.", "Billing"),
        ("Compare our plans", "Unlimited data and more.", "Plans"),
        ("Set up your new iPhone", "Insert the SIM card.", "Devices"),
        ("Reset your account password", "Sign in to your profile.", "Account"),
        ("Phone has no service", "Troubleshoot signal problems and fix errors.",
         "Troubleshooting"),
        ("About us", "We were founded a while ago.", "Other"),
    ],
)  # fmt: skip
def test_section_rules(title: str, body: str, expected: str) -> None:
    assert assign_section(title, body) == expected


def test_links_are_limited_to_the_same_host_and_path_prefix() -> None:
    links = links_under_prefix(INDEX_HTML, f"{BASE}/help/", f"{BASE}/help/")

    assert links == [f"{BASE}/help/voicemail", f"{BASE}/help/billing/pay"]


def test_extract_article_keeps_headings_as_markdown() -> None:
    article = extract_article(ARTICLE_HTML, f"{BASE}/help/voicemail", "2026-11-12T09:30:00Z")

    assert article is not None
    assert article.title == "Set up voicemail"
    assert article.section == "Devices"
    assert "## On an iPhone" in article.body_text
    assert "Help home" not in article.body_text
    assert article.synthetic is False
    assert article.article_id == article_id_for(f"{BASE}/help/voicemail")


def test_extract_article_returns_none_for_an_empty_page() -> None:
    assert extract_article("<html><body></body></html>", f"{BASE}/x", "t") is None


# --- politeness ------------------------------------------------------------------------


def test_robots_disallow_is_respected(tmp_path: Path) -> None:
    site = FakeSite(robots="User-agent: *\nDisallow: /help/\n")
    fetcher = _fetcher(site, tmp_path, [])

    assert fetcher.fetch(f"{BASE}/help/voicemail") is None
    assert site.requested == ["/robots.txt"]


def test_robots_forbidden_means_disallow_everything(tmp_path: Path) -> None:
    site = FakeSite(robots_status=403)

    assert _fetcher(site, tmp_path, []).fetch(f"{BASE}/help/voicemail") is None


def test_missing_robots_file_means_allowed(tmp_path: Path) -> None:
    site = FakeSite(robots_status=404)

    assert _fetcher(site, tmp_path, []).fetch(f"{BASE}/help/voicemail") is not None


def test_requests_are_spaced_and_identified(tmp_path: Path) -> None:
    site = FakeSite()
    sleeps: list[float] = []
    fetcher = _fetcher(site, tmp_path, sleeps)

    fetcher.fetch(f"{BASE}/help/a")
    fetcher.fetch(f"{BASE}/help/b")

    # robots.txt, a, b -> a wait before every request except the first.
    assert site.requested == ["/robots.txt", "/help/a", "/help/b"]
    assert sleeps == [2.0, 2.0]
    assert site.user_agents == {"test-agent/1.0"}
    assert fetcher.requests_made == 3


def test_cached_page_makes_no_request(tmp_path: Path) -> None:
    first_site = FakeSite()
    _fetcher(first_site, tmp_path, []).fetch(f"{BASE}/help/a")
    second_site = FakeSite()

    html = _fetcher(second_site, tmp_path, []).fetch(f"{BASE}/help/a")

    assert html is not None
    assert second_site.requested == []


def test_errors_and_non_html_are_skipped_and_not_cached(tmp_path: Path) -> None:
    site = FakeSite()
    fetcher = _fetcher(site, tmp_path, [])

    assert fetcher.fetch(f"{BASE}/help/missing") is None
    assert fetcher.fetch(f"{BASE}/help/file.pdf") is None
    assert list(tmp_path.iterdir()) == []


# --- end to end --------------------------------------------------------------------------


def test_scrape_from_seeds_and_index(tmp_path: Path) -> None:
    site = FakeSite()
    fetcher = _fetcher(site, tmp_path / "cache", [])

    articles = scrape(
        fetcher,
        [f"{BASE}/help/voicemail", f"{BASE}/help/missing"],
        index_url=f"{BASE}/help/",
        now=lambda: FIXED_NOW,
    )

    assert [a.url for a in articles] == [f"{BASE}/help/voicemail", f"{BASE}/help/billing/pay"]
    assert {a.scraped_at for a in articles} == {"2026-11-12T09:30:00Z"}


def test_scrape_stops_at_max_pages(tmp_path: Path) -> None:
    site = FakeSite()
    fetcher = _fetcher(site, tmp_path / "cache", [])

    articles = scrape(fetcher, [f"{BASE}/help/{n}" for n in range(10)], max_pages=3)

    assert len(articles) == 3
    assert site.requested == ["/robots.txt", "/help/0", "/help/1", "/help/2"]


def test_write_articles_round_trip(tmp_path: Path) -> None:
    article = extract_article(ARTICLE_HTML, f"{BASE}/help/voicemail", "2026-11-12T09:30:00Z")
    assert article is not None
    out = tmp_path / "out" / "kb.jsonl"

    assert write_articles(out, [article]) == 1
    assert out.read_text(encoding="utf-8").count("\n") == 1
    assert '"synthetic": false' in out.read_text(encoding="utf-8")
