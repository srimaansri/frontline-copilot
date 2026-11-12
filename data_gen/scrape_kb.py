"""Scrape public help articles into ``data/raw/kb_articles.jsonl``.

Usage:
    python -m data_gen.scrape_kb                           # URLs from data_gen/seed_urls.txt
    python -m data_gen.scrape_kb --index-url https://example.com/help/

The scraper is deliberately polite:

* it checks ``robots.txt`` for every URL and skips what is disallowed;
* it waits ``--delay`` seconds (default 2) between network requests;
* it stops after ``--max-pages`` pages (default 150);
* it caches raw HTML under ``data/raw/kb_html/``, so a re-run makes no request
  for a page it already has.

Scraped text is someone else's copyright. Everything this script writes is under
``data/raw/``, which is not committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

DEFAULT_SEED_FILE = Path("data_gen/seed_urls.txt")
DEFAULT_OUT = Path("data/raw/kb_articles.jsonl")
DEFAULT_CACHE_DIR = Path("data/raw/kb_html")
DEFAULT_DELAY_SECONDS = 2.0
DEFAULT_MAX_PAGES = 150
# Says what the client is without naming a person. Pass --user-agent to add a contact.
DEFAULT_USER_AGENT = "frontline-copilot-kb-scraper/0.1 (educational demo; obeys robots.txt)"

# Section -> keywords. A title hit counts three times as much as a body hit.
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Billing": ("bill", "payment", "pay ", "autopay", "refund", "charge", "invoice", "fee"),
    "Plans": ("plan", "unlimited", "add a line", "upgrade", "pricing", "data usage", "hotspot"),
    "Devices": ("phone", "device", "iphone", "android", "sim", "imei", "tablet", "watch"),
    "Account": ("account", "password", "log in", "sign in", "profile", "pin", "transfer"),
    "Troubleshooting": (
        "troubleshoot", "not working", "fix", "error", "no service", "reset", "signal", "can't",
    ),
}  # fmt: skip
_BODY_CHARS_FOR_SECTION = 600


@dataclass(frozen=True)
class Article:
    """One knowledge-base article."""

    article_id: str
    url: str
    title: str
    section: str
    body_text: str
    scraped_at: str
    last_modified: str | None
    synthetic: bool = False


def article_id_for(url: str) -> str:
    """Stable 12-character id for a URL."""
    # An identifier, not a security measure.
    return hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def read_seed_urls(path: Path) -> list[str]:
    """Read URLs from a seed file, skipping blank lines, comments and duplicates."""
    if not path.exists():
        return []
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith("#") and candidate not in urls:
            urls.append(candidate)
    return urls


def assign_section(title: str, body: str) -> str:
    """Pick a section by keyword counts. No model is involved."""
    title_lower = title.lower()
    body_lower = body[:_BODY_CHARS_FOR_SECTION].lower()
    best_section, best_score = "Other", 0
    for section, keywords in SECTION_KEYWORDS.items():
        score = sum(3 * title_lower.count(k) + body_lower.count(k) for k in keywords)
        if score > best_score:
            best_section, best_score = section, score
    return best_section


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def links_under_prefix(html: str, page_url: str, prefix_url: str) -> list[str]:
    """Return links on a page that stay on the same host and under ``prefix_url``'s path."""
    collector = _LinkCollector()
    collector.feed(html)
    prefix = urlsplit(prefix_url)
    found: list[str] = []
    for href in collector.links:
        absolute = urldefrag(urljoin(page_url, href)).url
        parts = urlsplit(absolute)
        if (
            parts.scheme in {"http", "https"}
            and parts.netloc == prefix.netloc
            and parts.path.startswith(prefix.path)
            and absolute not in found
        ):
            found.append(absolute)
    return found


def extract_article(html: str, url: str, scraped_at: str) -> Article | None:
    """Turn a page into an ``Article``, or None if no main text was found.

    The body is Markdown so headings survive for the heading-aware chunker.
    """
    body = trafilatura.extract(
        html, url=url, output_format="markdown", include_comments=False, include_tables=True
    )
    if not body or not body.strip():
        return None
    metadata = trafilatura.extract_metadata(html, default_url=url)
    title = (metadata.title if metadata and metadata.title else "").strip()
    if not title:
        first_heading = re.search(r"^#+\s*(.+)$", body, flags=re.MULTILINE)
        title = first_heading.group(1).strip() if first_heading else url
    return Article(
        article_id=article_id_for(url),
        url=url,
        title=title,
        section=assign_section(title, body),
        body_text=body.strip(),
        scraped_at=scraped_at,
        last_modified=metadata.date if metadata else None,
    )


class PoliteFetcher:
    """Fetches pages with a robots.txt check, a delay between requests and a disk cache."""

    def __init__(
        self,
        client: httpx.Client,
        cache_dir: Path,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Wrap ``client``. ``sleep`` is injectable so tests do not wait."""
        self._client = client
        self._cache_dir = cache_dir
        self._user_agent = user_agent
        self._delay_seconds = delay_seconds
        self._sleep = sleep
        self._robots: dict[str, RobotFileParser] = {}
        self._made_request = False
        self.requests_made = 0

    def _get(self, url: str) -> httpx.Response:
        if self._made_request:
            self._sleep(self._delay_seconds)
        self._made_request = True
        self.requests_made += 1
        return self._client.get(url, headers={"User-Agent": self._user_agent})

    def allowed(self, url: str) -> bool:
        """Return True if robots.txt permits fetching ``url``."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        parser = self._robots.get(origin)
        if parser is None:
            parser = RobotFileParser()
            response = self._get(f"{origin}/robots.txt")
            if response.status_code in {401, 403}:
                parser.disallow_all = True
            elif response.status_code >= 400:
                parser.allow_all = True
            else:
                parser.parse(response.text.splitlines())
            self._robots[origin] = parser
        return parser.can_fetch(self._user_agent, url)

    def fetch(self, url: str) -> str | None:
        """Return the page HTML from cache or network, or None if it may not be fetched."""
        cache_file = self._cache_dir / f"{article_id_for(url)}.html"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
        if not self.allowed(url):
            return None
        response = self._get(url)
        if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
            return None
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(response.text, encoding="utf-8")
        return response.text


def scrape(
    fetcher: PoliteFetcher,
    seed_urls: Iterable[str],
    *,
    index_url: str | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[Article]:
    """Fetch and extract up to ``max_pages`` articles.

    With ``index_url``, links found on that page under the same path prefix are
    added to the queue after the seed URLs.
    """
    queue: list[str] = list(dict.fromkeys(seed_urls))
    if index_url:
        index_html = fetcher.fetch(index_url)
        if index_html:
            queue.extend(
                link
                for link in links_under_prefix(index_html, index_url, index_url)
                if link not in queue and link != index_url
            )
    articles: list[Article] = []
    for url in queue[:max_pages]:
        html = fetcher.fetch(url)
        if html is None:
            continue
        article = extract_article(html, url, now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        if article is not None:
            articles.append(article)
    return articles


def write_articles(out_path: Path, articles: Iterable[Article]) -> int:
    """Write articles as JSON Lines and return how many were written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for article in articles:
            handle.write(json.dumps(asdict(article), ensure_ascii=False) + "\n")
            count += 1
    return count


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed-file", type=Path, default=DEFAULT_SEED_FILE)
    parser.add_argument("--index-url", default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    args = parser.parse_args(argv)

    seeds = read_seed_urls(args.seed_file)
    if not seeds and not args.index_url:
        print(f"no URLs in {args.seed_file} and no --index-url: nothing to scrape")
        raise SystemExit(1)
    with httpx.Client(follow_redirects=True, timeout=20.0) as client:
        fetcher = PoliteFetcher(
            client, args.cache_dir, user_agent=args.user_agent, delay_seconds=args.delay
        )
        articles = scrape(fetcher, seeds, index_url=args.index_url, max_pages=args.max_pages)
    count = write_articles(args.out, articles)
    print(f"wrote {count} articles to {args.out} ({fetcher.requests_made} network requests)")
    if count < 40:
        print("fewer than 40 articles: PLAN.md §5.1 says to use the synthetic KB instead")


if __name__ == "__main__":
    main()
