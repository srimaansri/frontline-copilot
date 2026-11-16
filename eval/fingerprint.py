"""A fingerprint of everything that decides how the copilot behaves.

A saved evaluation describes the copilot as it was when the run was made. If
the agent's code, its prompts, its settings or the evaluation set change after
that, the saved numbers describe a different system. The CI gate used to check
only the evaluation set and a prompt version that someone has to remember to
bump, so it went on accepting a run from before the router existed.

Every evaluation run now records this fingerprint, and the gate compares it
with the one computed from the repository. If they differ, the published
numbers are stale and a new run is needed.

A Python file is hashed by its syntax tree, so a comment or a change of
formatting does not make a run stale. A change to any string does, because the
prompts are strings. Other files are hashed as text.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

# What an answer depends on, and what decides how it is scored. The modules are
# named one by one: the ones the agent imports to answer a question. A module that
# cannot change an answer (the compliance checker, the chunker, whose effect is in
# the search index and not in this repository) is left out, so that adding to it
# does not make an evaluation look stale. A new module on the answering path has to
# be added here by hand, and ``tests/test_fingerprint.py`` fails until it is.
ANSWER_PATH_MODULES: tuple[str, ...] = (
    "agent",
    "claims",
    "config",
    "guardrails",
    "llm",
    "luhn",
    "prompts",
    "readability",
    "redaction",
    "retriever",
    "router",
    "schemas",
    "steps",
    "text",
    "tools",
)
BEHAVIOUR_GLOBS: tuple[str, ...] = (
    *(f"src/copilot/{name}.py" for name in ANSWER_PATH_MODULES),
    "config/settings.yaml",
    "eval/eval_set.jsonl",
    "eval/scorers.py",
)


def file_digest(path: Path) -> str:
    """A hash of what one file means: its syntax tree for Python, its text otherwise."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if path.suffix == ".py":
        text = ast.dump(ast.parse(text), annotate_fields=False, include_attributes=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def behaviour_fingerprint(root: Path = Path()) -> dict[str, object]:
    """The fingerprint of the repository at ``root``: one hash, and the hash of each file."""
    files = sorted(
        {path for pattern in BEHAVIOUR_GLOBS for path in root.glob(pattern) if path.is_file()}
    )
    digests = {path.relative_to(root).as_posix(): file_digest(path) for path in files}
    combined = hashlib.sha256()
    for name, digest in digests.items():
        combined.update(f"{name}={digest}\n".encode())
    return {"sha256": combined.hexdigest(), "files": digests}


def changed_files(saved: dict[str, str], current: dict[str, str]) -> list[str]:
    """The files of ``current`` that ``saved`` does not hold with the same hash.

    Only the files that count now are compared. A run saved when the fingerprint
    covered more files is not made stale by the ones that have since been left out.
    """
    return sorted(name for name, digest in current.items() if saved.get(name) != digest)
