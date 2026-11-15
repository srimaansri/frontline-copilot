"""Read redacted transcripts for display. Only the redacted table is ever read."""

from __future__ import annotations

import json

from copilot.config import Settings
from copilot.tools import TRANSCRIPT_ID_RE, SqlRunner, ToolError

MAX_LISTED = 500


def list_transcripts(sql: SqlRunner, settings: Settings) -> list[dict[str, str]]:
    """Id, topic and outcome of every redacted transcript, in id order."""
    table = settings.table("silver", "transcripts_redacted")
    rows = sql(
        "SELECT transcript_id, category, resolution "  # noqa: S608
        f"FROM {table} ORDER BY transcript_id LIMIT {MAX_LISTED}",
        {},
    )
    return [{key: str(value) for key, value in row.items()} for row in rows]


def get_transcript(sql: SqlRunner, settings: Settings, transcript_id: str) -> list[dict[str, str]]:
    """The turns of one redacted transcript, as ``{"speaker": ..., "text": ...}``."""
    transcript_id = transcript_id.strip().upper()
    if not TRANSCRIPT_ID_RE.fullmatch(transcript_id):
        raise ToolError("A transcript id is the letter T and four digits, such as T0007.")
    table = settings.table("silver", "transcripts_redacted")
    rows = sql(
        f"SELECT to_json(turns) AS turns_json FROM {table} "  # noqa: S608
        "WHERE transcript_id = :transcript_id LIMIT 1",
        {"transcript_id": ("STRING", transcript_id)},
    )
    if not rows:
        raise ToolError(f"No transcript was found with the id {transcript_id}")
    turns = json.loads(rows[0]["turns_json"])
    return [{"speaker": str(turn["speaker"]), "text": str(turn["text"])} for turn in turns]
