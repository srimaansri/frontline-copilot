"""Heading-aware chunking of Markdown help articles.

How an article becomes chunks:

1. The body is cut into sections at its headings. The top-level title line is
   dropped, because the title is supplied separately.
2. Whole sections are packed into a chunk until the next one would not fit.
   A section is only broken up when it is too large on its own; it is then
   split at paragraphs, then lines, then sentences, then words.
3. Each chunk starts with the line ``{title} - {heading}``, the heading being that of
   the first section in the chunk, so a chunk still says what it is about when
   it is read on its own.
4. A new chunk repeats the last sentences of the previous one, up to
   ``overlap_tokens``, so a fact that straddles a boundary is not lost.

Token counts come from a function the caller passes in. That keeps this module
free of any tokenizer download and makes it testable offline.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

TokenCounter = Callable[[str], int]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# Coarse to fine. Each pattern captures the separator so it can be kept.
_SPLITTERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\n{2,})"),
    re.compile(r"(\n)"),
    re.compile(r"((?<=[.!?])[ \t]+)"),
    re.compile(r"([ \t]+)"),
)
_SENTENCE_LEVEL = 3  # how many splitters to apply when cutting text into sentences


@dataclass(frozen=True)
class Section:
    """A heading and everything under it. ``text`` includes the heading line."""

    heading: str
    text: str


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of an article."""

    chunk_index: int
    heading: str
    text: str
    n_tokens: int


def split_sections(markdown: str) -> list[Section]:
    """Cut a Markdown body into sections at its headings.

    A leading ``# Title`` line is dropped. Text before the first heading becomes
    a section with an empty heading.
    """
    sections: list[Section] = []
    heading = ""
    lines: list[str] = []
    seen_content = False

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            sections.append(Section(heading, text + "\n\n"))

    for line in markdown.strip().splitlines():
        match = _HEADING_RE.match(line)
        if match is None:
            lines.append(line)
            seen_content = seen_content or bool(line.strip())
            continue
        if len(match.group(1)) == 1 and not seen_content and not sections:
            # The article's own title: supplied separately, so not repeated.
            seen_content = True
            continue
        flush()
        heading = match.group(2)
        lines = [line]
        seen_content = True
    flush()
    return sections


def _split_keeping_separators(text: str, pattern: re.Pattern[str]) -> list[str]:
    parts = pattern.split(text)
    pieces: list[str] = []
    for index in range(0, len(parts), 2):
        piece = parts[index] + (parts[index + 1] if index + 1 < len(parts) else "")
        if piece:
            pieces.append(piece)
    return pieces


def _atoms(text: str, fits: Callable[[str], bool], level: int = 0) -> list[str]:
    """Break ``text`` into the largest pieces that each satisfy ``fits``."""
    if fits(text) or len(text) <= 1:
        return [text]
    if level == len(_SPLITTERS):
        # A single "word" that is still too large: cut it in half and try again.
        middle = len(text) // 2
        return _atoms(text[:middle], fits, level) + _atoms(text[middle:], fits, level)
    pieces: list[str] = []
    for piece in _split_keeping_separators(text, _SPLITTERS[level]):
        pieces.extend(_atoms(piece, fits, level + 1))
    return pieces


def _sentences(text: str) -> list[str]:
    pieces = [text]
    for pattern in _SPLITTERS[:_SENTENCE_LEVEL]:
        pieces = [part for piece in pieces for part in _split_keeping_separators(piece, pattern)]
    return pieces


def _overlap_tail(text: str, overlap_tokens: int, count_tokens: TokenCounter) -> str:
    """The trailing whole sentences of ``text`` that fit in ``overlap_tokens``."""
    if overlap_tokens <= 0:
        return ""
    taken: list[str] = []
    for sentence in reversed(_sentences(text)):
        if count_tokens("".join([sentence, *taken])) > overlap_tokens:
            break
        taken.insert(0, sentence)
    tail = "".join(taken)
    if tail.strip() and not tail[-1].isspace():
        tail += "\n\n"
    return tail if tail.strip() else ""


def _prefix(title: str, heading: str) -> str:
    return f"{title} - {heading}\n" if heading else f"{title}\n"


def chunk_article(
    title: str,
    body: str,
    *,
    chunk_size_tokens: int,
    overlap_tokens: int,
    count_tokens: TokenCounter,
) -> list[Chunk]:
    """Split one article into chunks of at most ``chunk_size_tokens`` tokens.

    Args:
        title: The article title, used in every chunk's first line.
        body: The article as Markdown.
        chunk_size_tokens: Upper bound on a chunk's size, prefix included.
        overlap_tokens: How much of the previous chunk a new chunk may repeat.
        count_tokens: Returns the number of tokens in a string.

    Returns:
        The chunks in reading order. An empty body gives an empty list.

    Raises:
        ValueError: If the sizes are not positive or the overlap is not smaller
            than the chunk size.
    """
    if chunk_size_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= chunk_size_tokens:
        msg = (
            f"need 0 <= overlap_tokens < chunk_size_tokens, got overlap={overlap_tokens}, "
            f"size={chunk_size_tokens}"
        )
        raise ValueError(msg)

    def render(heading: str, tail: str, atoms: list[str]) -> str:
        return (_prefix(title, heading) + tail + "".join(atoms)).strip()

    def fits(heading: str, tail: str, atoms: list[str]) -> bool:
        return count_tokens(render(heading, tail, atoms)) <= chunk_size_tokens

    pending: list[tuple[str, str]] = []
    for section in split_sections(body):
        heading = section.heading
        pending.extend(
            (heading, atom)
            for atom in _atoms(section.text, lambda piece, h=heading: fits(h, "", [piece]))  # type: ignore[misc]
            if atom.strip()
        )

    chunks: list[Chunk] = []
    open_heading = ""
    open_tail = ""
    open_atoms: list[str] = []

    def close() -> None:
        text = render(open_heading, open_tail, open_atoms)
        chunks.append(Chunk(len(chunks), open_heading, text, count_tokens(text)))

    for heading, atom in pending:
        if open_atoms and fits(open_heading, open_tail, [*open_atoms, atom]):
            open_atoms.append(atom)
            continue
        next_tail = ""
        if open_atoms:
            close()
            next_tail = _overlap_tail("".join(open_atoms), overlap_tokens, count_tokens)
        # The overlap is dropped when it would not fit beside the first new piece.
        open_tail = next_tail if fits(heading, next_tail, [atom]) else ""
        open_heading = heading
        open_atoms = [atom]
    if open_atoms:
        close()
    return chunks


def make_chunk_id(article_id: str, chunk_config: str, chunk_index: int) -> str:
    """Stable primary key for a chunk: the same inputs always give the same id."""
    key = f"{article_id}|{chunk_config}|{chunk_index}".encode()
    # An identifier, not a security measure.
    return hashlib.sha1(key, usedforsecurity=False).hexdigest()[:16]


def tiktoken_counter(encoding_name: str = "cl100k_base") -> TokenCounter:
    """Return a token counter backed by ``tiktoken``.

    The count is an approximation for any model that is not an OpenAI model, which
    is all this project needs to size chunks. The encoding file is downloaded on
    first use and cached by ``tiktoken``.
    """
    import tiktoken

    encoding = tiktoken.get_encoding(encoding_name)

    def count(text: str) -> int:
        return len(encoding.encode(text))

    return count
