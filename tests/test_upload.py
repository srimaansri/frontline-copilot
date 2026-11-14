"""Upload to the landing volume, tested against a fake Files API."""

from pathlib import Path
from typing import BinaryIO

import pytest

from copilot.config import Settings
from data_gen.upload import DATA_FILES, upload_files


class FakeFiles:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, bool | None]] = []

    def upload(self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None) -> None:
        self.calls.append((file_path, contents.read(), overwrite))


def _settings() -> Settings:
    return Settings(catalog="demo", _env_file=None)  # type: ignore[call-arg]


def test_files_go_to_the_landing_volume_and_replace_what_is_there(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_bytes(b"one\n")
    (tmp_path / "b.csv").write_bytes(b"two\n")
    fake = FakeFiles()

    uploaded = upload_files(
        fake, _settings(), [(Path("a.jsonl"), "a.jsonl"), (Path("b.csv"), "plans.csv")],
        root=tmp_path,
    )  # fmt: skip

    assert fake.calls == [
        ("/Volumes/demo/raw/landing/a.jsonl", b"one\n", True),
        ("/Volumes/demo/raw/landing/plans.csv", b"two\n", True),
    ]
    assert [(u.remote, u.size_bytes) for u in uploaded] == [
        ("/Volumes/demo/raw/landing/a.jsonl", 4),
        ("/Volumes/demo/raw/landing/plans.csv", 4),
    ]


def test_nothing_is_uploaded_when_a_file_is_missing(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_bytes(b"one\n")
    fake = FakeFiles()

    with pytest.raises(FileNotFoundError, match=r"missing local files.*b\.csv"):
        upload_files(
            fake, _settings(), [(Path("a.jsonl"), "a.jsonl"), (Path("b.csv"), "b.csv")],
            root=tmp_path,
        )  # fmt: skip

    assert fake.calls == []


def test_the_default_file_list_covers_all_four_inputs() -> None:
    assert [name for _, name in DATA_FILES] == [
        "kb_articles.jsonl",
        "transcripts.jsonl",
        "pii_labels.jsonl",
        "plans.csv",
    ]
    # The knowledge base in use is the committed synthetic one.
    assert DATA_FILES[0][0] == Path("data/synthetic/kb_articles.jsonl")
