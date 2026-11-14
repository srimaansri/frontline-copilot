"""Upload the local data files to the Unity Catalog landing volume.

Usage:
    python -m data_gen.upload

Re-running it replaces each file with the current local copy, so it is safe to
run again after regenerating data.

Authentication is left to the Databricks SDK: a CLI profile named in
``DATABRICKS_CONFIG_PROFILE``, or whatever else the SDK finds.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from copilot.config import Settings, get_settings

# Local file -> name in the landing volume.
DATA_FILES: tuple[tuple[Path, str], ...] = (
    (Path("data/synthetic/kb_articles.jsonl"), "kb_articles.jsonl"),
    (Path("data/raw/transcripts.jsonl"), "transcripts.jsonl"),
    (Path("data/raw/pii_labels.jsonl"), "pii_labels.jsonl"),
    (Path("data/raw/plans.csv"), "plans.csv"),
)


class FilesApi(Protocol):
    """The one method of the SDK's Files API that is used here."""

    def upload(self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None) -> None:
        """Write ``contents`` to ``file_path`` in a volume."""
        ...


@dataclass(frozen=True)
class Uploaded:
    """One file that was sent."""

    local: Path
    remote: str
    size_bytes: int


def upload_files(
    files_api: FilesApi,
    settings: Settings,
    files: Sequence[tuple[Path, str]] = DATA_FILES,
    *,
    root: Path = Path(),
) -> list[Uploaded]:
    """Send every file to the landing volume, replacing what is there.

    Raises:
        FileNotFoundError: If any local file is missing. Nothing is uploaded in
            that case, so the volume never holds a partial set.
    """
    missing = [str(local) for local, _ in files if not (root / local).is_file()]
    if missing:
        msg = "missing local files, generate them first: " + ", ".join(missing)
        raise FileNotFoundError(msg)
    landing = settings.volume_path("raw", "landing")
    uploaded: list[Uploaded] = []
    for local, name in files:
        path = root / local
        remote = f"{landing}/{name}"
        with path.open("rb") as handle:
            files_api.upload(remote, handle, overwrite=True)
        uploaded.append(Uploaded(local, remote, path.stat().st_size))
    return uploaded


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    from databricks.sdk import WorkspaceClient
    from dotenv import load_dotenv

    # Puts DATABRICKS_HOST and DATABRICKS_CONFIG_PROFILE where the SDK looks for them.
    load_dotenv()
    for item in upload_files(WorkspaceClient().files, get_settings()):
        print(f"{item.local}  ->  {item.remote}  ({item.size_bytes:,} bytes)")


if __name__ == "__main__":
    main()
