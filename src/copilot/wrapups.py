"""Read a saved after-call wrap-up back from ``ops.call_wrapups``.

``Tools.save_wrap_up`` is the only thing that writes that table, and it stores
each text field after the output check, so a row holds redacted text only. This
module reads the newest row of one call, so that opening a call again shows the
record an agent already saved, not an empty draft.

The table does not say who saved a record: it has no column for that, and the
application has no notion of a signed-in agent. ``StoredWrapUp`` therefore
carries when a record was saved and not by whom.
"""

from __future__ import annotations

import json

from copilot.config import Settings
from copilot.schemas import FollowUp, SavedWrapUp
from copilot.tools import SqlRunner, valid_transcript_id


class StoredWrapUp(SavedWrapUp):
    """A wrap-up as it was read back from the table, with when it was saved."""

    # UTC, to the second, such as "2026-11-16T14:02:11Z".
    saved_at: str


def latest_wrap_up(sql: SqlRunner, settings: Settings, transcript_id: str) -> StoredWrapUp | None:
    """The wrap-up most recently saved for one call, or ``None`` if none was.

    A call saved twice has two rows, and the later one is the record.

    Raises:
        ToolError: If the id is malformed. Nothing is looked up.
    """
    transcript_id = valid_transcript_id(transcript_id)
    table = settings.table("ops", "call_wrapups")
    rows = sql(
        # The time is written as text here, so that it does not depend on how the
        # warehouse serializes a timestamp. It was stored as UTC.
        "SELECT wrapup_id, date_format(saved_at, 'yyyy-MM-dd HH:mm:ss') AS saved_at, "  # noqa: S608
        "disposition, category, to_json(notes) AS notes_json, "
        "to_json(promises) AS promises_json, follow_up_owner, follow_up, sentiment "
        f"FROM {table} WHERE transcript_id = :transcript_id "
        "ORDER BY saved_at DESC, wrapup_id DESC LIMIT 1",
        {"transcript_id": ("STRING", transcript_id)},
    )
    if not rows:
        return None
    row = rows[0]
    follow_up = None
    if row.get("follow_up_owner") and row.get("follow_up"):
        follow_up = FollowUp(owner=row["follow_up_owner"], action=str(row["follow_up"]))
    return StoredWrapUp(
        wrapup_id=str(row["wrapup_id"]),
        transcript_id=transcript_id,
        disposition=row["disposition"],
        category=row["category"],
        notes=_lines(row.get("notes_json")),
        promises=_lines(row.get("promises_json")),
        follow_up=follow_up,
        sentiment=row["sentiment"],
        # It was read from the table, so it was written.
        recorded=True,
        saved_at=_utc(str(row["saved_at"])),
    )


def _lines(lines_json: object) -> list[str]:
    """A stored list of lines. A null column is an empty list."""
    if lines_json is None:
        return []
    return [str(line) for line in json.loads(str(lines_json))]


def _utc(stored: str) -> str:
    """``2026-11-16 14:02:11`` as ``2026-11-16T14:02:11Z``."""
    return stored.strip().replace(" ", "T") + "Z"
