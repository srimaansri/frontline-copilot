"""Core behaviour of the chunker, counted in words so the tests need no tokenizer.

These are the checks the pipeline relies on. Wider edge-case coverage lives in
``test_chunking.py``.
"""

import sys
import types

import pytest

from copilot.chunking import (
    Chunk,
    chunk_article,
    make_chunk_id,
    split_sections,
    tiktoken_counter,
)

TITLE = "Set up voicemail"


def words(text: str) -> int:
    return len(text.split())


def sentence(tag: str, count: int) -> str:
    """A sentence of exactly ``count`` words whose words name the sentence."""
    return " ".join(f"{tag}{n}" for n in range(count - 1)) + f" {tag}end."


ARTICLE = (
    f"# {TITLE}\n\n"
    f"{sentence('intro', 10)}\n\n"
    f"## What you need\n\n{sentence('need', 20)} {sentence('more', 20)}\n\n"
    f"## Steps\n\n1. {sentence('one', 12)}\n2. {sentence('two', 12)}\n\n"
    f"## Need more help?\n\n{sentence('help', 15)}\n"
)


def chunk(body: str = ARTICLE, size: int = 60, overlap: int = 15) -> list[Chunk]:
    return chunk_article(
        TITLE, body, chunk_size_tokens=size, overlap_tokens=overlap, count_tokens=words
    )


# --- sections -----------------------------------------------------------------------


def test_sections_follow_headings_and_drop_the_title() -> None:
    sections = split_sections(ARTICLE)

    assert [s.heading for s in sections] == ["", "What you need", "Steps", "Need more help?"]
    assert all(TITLE not in s.text for s in sections)
    assert sections[1].text.startswith("## What you need")


def test_body_without_headings_is_one_section() -> None:
    assert [s.heading for s in split_sections("Just a paragraph.\n\nAnother.")] == [""]


def test_empty_body_has_no_sections_or_chunks() -> None:
    assert split_sections("  \n\n ") == []
    assert chunk(body="") == []


def test_a_later_top_level_heading_starts_a_section() -> None:
    sections = split_sections("# Title\n\nIntro.\n\n# Second part\n\nMore.")

    assert [s.heading for s in sections] == ["", "Second part"]


# --- size, prefix, order ----------------------------------------------------------------


def test_small_article_is_a_single_chunk_with_all_sections() -> None:
    chunks = chunk(size=500, overlap=50)

    assert len(chunks) == 1
    assert chunks[0].text.startswith(f"{TITLE}\n")
    assert "## Steps" in chunks[0].text
    assert "## Need more help?" in chunks[0].text


@pytest.mark.parametrize(("size", "overlap"), [(60, 15), (40, 10), (25, 5), (12, 0)])
def test_every_chunk_is_within_the_size_limit(size: int, overlap: int) -> None:
    chunks = chunk(size=size, overlap=overlap)

    assert len(chunks) > 1
    assert all(c.n_tokens <= size for c in chunks)
    assert all(c.n_tokens == words(c.text) for c in chunks)


def test_every_chunk_starts_with_title_and_its_heading() -> None:
    for c in chunk():
        first_line = c.text.splitlines()[0]
        assert first_line == (f"{TITLE} - {c.heading}" if c.heading else TITLE)


def test_chunk_indexes_are_sequential() -> None:
    assert [c.chunk_index for c in chunk()] == list(range(len(chunk())))


def test_chunking_is_deterministic() -> None:
    assert chunk() == chunk()


def test_no_content_is_lost() -> None:
    article_words = set(ARTICLE.replace(f"# {TITLE}", "").split())
    chunk_words = {word for c in chunk(size=25, overlap=5) for word in c.text.split()}

    assert article_words <= chunk_words


# --- sections stay whole, large ones are split ---------------------------------------------


def test_a_section_that_fits_is_not_split() -> None:
    chunks = chunk(size=60, overlap=0)
    steps = [c for c in chunks if "## Steps" in c.text]

    assert len(steps) == 1
    assert "oneend." in steps[0].text
    assert "twoend." in steps[0].text


def test_an_oversized_paragraph_is_split_between_sentences() -> None:
    body = f"## Long\n\n{sentence('a', 20)} {sentence('b', 20)} {sentence('c', 20)}"

    chunks = chunk(body=body, size=30, overlap=0)

    assert len(chunks) == 3
    for c in chunks:
        # Each chunk holds one complete sentence, never part of one.
        assert c.text.rstrip().endswith("end.")
        assert sum(word.endswith("end.") for word in c.text.split()) == 1


def test_an_oversized_sentence_is_split_between_words() -> None:
    chunks = chunk(body=f"## Long\n\n{sentence('w', 80)}", size=20, overlap=0)

    assert len(chunks) > 3
    assert all(c.n_tokens <= 20 for c in chunks)
    assert {f"w{n}" for n in range(79)} <= {word for c in chunks for word in c.text.split()}


def test_a_single_huge_word_is_cut_without_looping_forever() -> None:
    def characters(text: str) -> int:
        return len(text)

    chunks = chunk_article(
        "T", "x" * 200, chunk_size_tokens=50, overlap_tokens=0, count_tokens=characters
    )

    assert all(c.n_tokens <= 50 for c in chunks)
    assert sum(c.text.count("x") for c in chunks) == 200


def test_overlap_that_does_not_fit_beside_the_next_piece_is_dropped() -> None:
    def characters(text: str) -> int:
        return len(text)

    # Pieces of 25 characters; a 30-character overlap would hold one of them, but
    # 2 (prefix) + 27 (overlap) + 25 (next piece) is over the limit of 50.
    chunks = chunk_article(
        "T", "x" * 200, chunk_size_tokens=50, overlap_tokens=30, count_tokens=characters
    )

    assert all(c.n_tokens <= 50 for c in chunks)
    assert sum(c.text.count("x") for c in chunks) == 200


# --- overlap -------------------------------------------------------------------------------


def test_new_chunk_repeats_the_end_of_the_previous_one() -> None:
    body = f"## Long\n\n{sentence('a', 12)} {sentence('b', 12)} {sentence('c', 12)}"

    first, second = chunk(body=body, size=32, overlap=14)[:2]

    assert "bend." in first.text
    # Sentence b (12 words) fits in the 14-word overlap, so it opens the next chunk.
    # The first line, "Set up voicemail - Long", is five words.
    assert second.text.split()[5] == "b0"
    assert "cend." in second.text


def test_overlap_never_exceeds_its_limit() -> None:
    body = f"## Long\n\n{sentence('a', 12)} {sentence('b', 12)} {sentence('c', 12)}"

    first, second = chunk(body=body, size=32, overlap=5)[:2]

    # No whole sentence fits in 5 words, so nothing is repeated.
    assert not set(first.text.split()[5:]) & set(second.text.split()[5:])


def test_zero_overlap_repeats_nothing() -> None:
    chunks = chunk(size=40, overlap=0)
    seen: set[str] = set()
    for c in chunks:
        body_words = {w for w in c.text.split() if w.endswith("end.")}
        assert not seen & body_words
        seen |= body_words


# --- arguments and ids ------------------------------------------------------------------------


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (10, 10), (10, 11), (10, -1)])
def test_invalid_sizes_are_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError, match="overlap_tokens < chunk_size_tokens"):
        chunk(size=size, overlap=overlap)


def test_chunk_ids_are_stable_and_distinct() -> None:
    assert make_chunk_id("abc", "A", 0) == make_chunk_id("abc", "A", 0)
    assert len(make_chunk_id("abc", "A", 0)) == 16
    assert len({make_chunk_id("abc", "A", 0), make_chunk_id("abc", "B", 0),
                make_chunk_id("abc", "A", 1), make_chunk_id("abd", "A", 0)}) == 4  # fmt: skip


def test_tiktoken_counter_counts_with_the_named_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []

    class FakeEncoding:
        def encode(self, text: str) -> list[int]:
            return list(range(len(text.split())))

    def get_encoding(name: str) -> FakeEncoding:
        requested.append(name)
        return FakeEncoding()

    fake_module = types.ModuleType("tiktoken")
    fake_module.get_encoding = get_encoding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tiktoken", fake_module)

    count = tiktoken_counter()

    assert count("three short words") == 3
    assert requested == ["cl100k_base"]
