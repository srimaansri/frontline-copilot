"""Generate the synthetic knowledge base with the workspace's open-weight model.

Usage:
    python -m data_gen.synth_kb                # write any articles that are missing
    python -m data_gen.synth_kb --force        # rewrite every article
    python -m data_gen.synth_kb --limit 3      # a quick trial

A language model does not give the same text twice, so the output is committed
(``data/synthetic/kb_articles.jsonl``) and treated as the source. This script is
run on purpose, not as part of a pipeline. It is resumable: an article that is
already in the output file is kept unless ``--force`` is given.

The facts in each article come from ``kb_topics.py`` and the plan catalogue. The
model is told to state no price, fee, limit or phone number that is not in them.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

from copilot.text import to_plain_punctuation
from data_gen.kb_topics import CARRIER_FACTS, TOPICS, Topic
from data_gen.plans import PLANS
from data_gen.scrape_kb import Article, article_id_for, write_articles

DEFAULT_OUT = Path("data/synthetic/kb_articles.jsonl")
DEFAULT_META = Path("data/synthetic/kb_meta.json")
PROMPT_VERSION = "kb-v1"
BASE_URL = "https://help.northline.example/articles"
MIN_WORDS = 120
MAX_WORDS = 650
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = """\
You write help-center articles for Northline Wireless, a fictional wireless carrier. \
Many readers are older adults who are not comfortable with technology.

Style rules:
- Plain language at about a grade 6 to 8 reading level. Short sentences. Say "you".
- Explain any technical word the first time you use it.
- Use numbered steps for anything the reader does in order.
- Be specific and practical. No marketing language.

Fact rules:
- State every fact in the article brief.
- Do not state any price, fee, time limit, data amount or phone number that is not in the \
brief, the carrier facts or the plan list. If you are not given a number, do not make one up.
- General how-to steps for phones (where a setting is, how to restart) may come from your \
own knowledge.

Format rules:
- Markdown only. Start with one line "# <the exact title given>".
- Then a one or two sentence summary.
- Then 2 to 4 sections, each starting with "## ".
- 200 to 400 words in total.
- Finish with a short "## Need more help?" section that gives the support contact details.
- No tables, no links, no placeholders in brackets, no note to the editor.
"""


class ChatClient(Protocol):
    """Anything that can turn a system and a user message into text."""

    def complete(self, system: str, user: str) -> str:
        """Return the model's reply."""
        ...


def article_url(topic: Topic) -> str:
    """The fictional URL an article is cited by."""
    return f"{BASE_URL}/{topic.slug}"


def catalogue_text() -> str:
    """The plan catalogue as plain lines for the prompt."""
    lines: list[str] = []
    for row in PLANS:
        period = {"monthly": "a month", "daily": "a day", "one_time": "one time"}[
            row.billing_period
        ]
        details = [f"${row.monthly_price_usd:.0f} {period}"]
        if row.kind == "plan":
            details.append("unlimited data" if row.data_gb is None else f"{row.data_gb:g} GB data")
            details.append(f"{row.hotspot_gb or 0:g} GB hotspot")
            details.append(f"international: {row.international}")
        details.append(row.notes)
        lines.append(f"- {row.name} ({row.kind}): " + "; ".join(details))
    return "\n".join(lines)


def build_user_prompt(topic: Topic) -> str:
    """The request for one article: title, brief, carrier facts and the plan list."""
    carrier_facts = "\n".join(f"- {fact}" for fact in CARRIER_FACTS)
    return (
        f"Write the help article titled: {topic.title}\n"
        f"Help-center section: {topic.section}\n\n"
        f"Article brief (state every fact here):\n{topic.brief}\n\n"
        f"Carrier facts:\n{carrier_facts}\n\n"
        f"Plan list:\n{catalogue_text()}\n"
    )


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*\n(.*)\n```\s*$", re.DOTALL)
_H1_RE = re.compile(r"^#\s+.*$", re.MULTILINE)


def clean_body(raw: str, topic: Topic) -> str:
    """Strip a wrapping code fence and make the first heading the exact title."""
    text = to_plain_punctuation(raw).strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    heading = f"# {topic.title}"
    own_title = _H1_RE.match(text)
    rest = text[own_title.end() :] if own_title else f"\n\n{text}"
    # Models end lines with two spaces for a Markdown line break; they add nothing here.
    return "\n".join(line.rstrip() for line in (heading + rest).strip().splitlines())


def find_problems(body: str) -> list[str]:
    """Return reasons a generated article should be rejected. Empty means acceptable."""
    problems: list[str] = []
    words = len(body.split())
    if words < MIN_WORDS:
        problems.append(f"too short ({words} words)")
    if words > MAX_WORDS:
        problems.append(f"too long ({words} words)")
    if len(re.findall(r"^##\s+\S", body, flags=re.MULTILINE)) < 2:
        problems.append("fewer than two sections")
    if "```" in body:
        problems.append("contains a code fence")
    if re.search(r"\[[^\]]*\]", body):
        problems.append("contains a bracketed placeholder or link")
    if re.search(r"as an ai|language model|i cannot|i can't help", body, flags=re.IGNORECASE):
        problems.append("contains model boilerplate")
    if "611" not in body and "1-800-555-0199" not in body:
        problems.append("does not give a support contact")
    if not body.isascii():
        odd = sorted({char for char in body if not char.isascii()})
        problems.append(
            "contains non-ASCII characters: " + " ".join(f"U+{ord(c):04X}" for c in odd)
        )
    return problems


_AMOUNT_RE = re.compile(r"\$\s?(\d+(?:,\d{3})*)(?:\.(\d{2}))?")


def _amounts(text: str) -> set[str]:
    """Dollar amounts in ``text``, normalised so "$10.00" and "$10" are the same."""
    found: set[str] = set()
    for match in _AMOUNT_RE.finditer(text):
        whole = match.group(1).replace(",", "")
        cents = match.group(2)
        found.add(f"${whole}" if cents in (None, "00") else f"${whole}.{cents}")
    return found


def unsupported_amounts(body: str, topic: Topic) -> list[str]:
    """Dollar amounts in an article that neither its brief nor the catalogue contains.

    This is the check behind "never invent a price". It also rejects amounts the
    model worked out itself, such as a total for several days abroad.
    """
    allowed = {f"${row.monthly_price_usd:.0f}" for row in PLANS} | _amounts(topic.brief)
    return sorted(_amounts(body) - allowed)


def write_article(
    topic: Topic, client: ChatClient, *, now: Callable[[], datetime]
) -> tuple[Article | None, list[str]]:
    """Generate one article, retrying when the result is rejected."""
    problems: list[str] = []
    for _attempt in range(MAX_ATTEMPTS):
        try:
            raw = client.complete(SYSTEM_PROMPT, build_user_prompt(topic))
        except Exception as error:
            # Any client failure is retried, then reported by type.
            problems = [f"request failed: {type(error).__name__}"]
            continue
        body = clean_body(raw, topic)
        problems = find_problems(body)
        invented = unsupported_amounts(body, topic)
        if invented:
            problems.append("states amounts that are not in its brief: " + ", ".join(invented))
        if not problems:
            url = article_url(topic)
            return (
                Article(
                    article_id=article_id_for(url),
                    url=url,
                    title=topic.title,
                    section=topic.section,
                    body_text=body,
                    scraped_at=now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    last_modified=None,
                    synthetic=True,
                ),
                [],
            )
    return None, problems


def read_existing(path: Path) -> dict[str, Article]:
    """Load previously generated articles, keyed by ``article_id``."""
    if not path.exists():
        return {}
    articles: dict[str, Article] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            article = Article(**json.loads(line))
            articles[article.article_id] = article
    return articles


def generate(
    topics: Sequence[Topic],
    client: ChatClient,
    existing: Mapping[str, Article],
    *,
    workers: int = 3,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[list[Article], dict[str, list[str]]]:
    """Return every article in topic order, plus the problems of any that failed.

    Topics already in ``existing`` are reused as they are. An existing article
    whose topic is no longer listed is dropped.
    """
    todo = [topic for topic in topics if article_id_for(article_url(topic)) not in existing]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda topic: write_article(topic, client, now=now), todo))
    fresh: dict[str, Article] = {}
    failures: dict[str, list[str]] = {}
    for topic, (article, problems) in zip(todo, results, strict=True):
        if article is None:
            failures[topic.slug] = problems
        else:
            fresh[article.article_id] = article
    ordered: list[Article] = []
    for topic in topics:
        article_id = article_id_for(article_url(topic))
        found = existing.get(article_id) or fresh.get(article_id)
        if found is not None:
            ordered.append(found)
    return ordered, failures


class DatabricksChat:
    """Chat through a Databricks model serving endpoint."""

    def __init__(self, endpoint: str, *, max_tokens: int = 1500, temperature: float = 0.3) -> None:
        """Create a workspace client. Authentication is resolved by the Databricks SDK."""
        # Imported here so the tests, which use a fake client, do not need the SDK.
        from databricks.sdk import WorkspaceClient

        self._workspace = WorkspaceClient()
        self._endpoint = endpoint
        self._max_tokens = max_tokens
        self._temperature = temperature

    def complete(self, system: str, user: str) -> str:
        """Send one chat request and return the text of the reply."""
        from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

        response = self._workspace.serving_endpoints.query(
            name=self._endpoint,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=system),
                ChatMessage(role=ChatMessageRole.USER, content=user),
            ],
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        content = response.choices[0].message.content if response.choices else None
        if isinstance(content, str):
            return content
        # Some open-weight models return a list of blocks, with reasoning kept
        # apart from the answer. Only the answer text is wanted.
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return ""


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--force", action="store_true", help="rewrite every article")
    parser.add_argument("--limit", type=int, default=None, help="only the first N topics")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    from copilot.config import get_settings

    # Puts DATABRICKS_HOST and DATABRICKS_CONFIG_PROFILE where the SDK looks for them.
    load_dotenv()
    endpoint = get_settings().llm_endpoint
    topics = TOPICS[: args.limit] if args.limit else TOPICS
    existing = {} if args.force else read_existing(args.out)
    articles, failures = generate(topics, DatabricksChat(endpoint), existing, workers=args.workers)
    count = write_articles(args.out, articles)
    words = sorted(len(article.body_text.split()) for article in articles)
    meta = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_endpoint": endpoint,
        "prompt_version": PROMPT_VERSION,
        "articles": count,
        "topics_requested": len(topics),
        "failed_slugs": sorted(failures),
        "words_min_median_max": [words[0], words[len(words) // 2], words[-1]] if words else [],
        "databricks_sdk": version("databricks-sdk"),
    }
    args.meta.parent.mkdir(parents=True, exist_ok=True)
    args.meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {count} of {len(topics)} articles to {args.out}")
    for slug, problems in sorted(failures.items()):
        print(f"  failed: {slug}: {'; '.join(problems)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
