"""Read redacted transcripts for display. Only the redacted table is ever read.

The calls list also reads ``gold.call_insights``, which the pipeline fills with
what the rule check found in each call. That table holds rule names and turn
numbers, and no text from a call.
"""

from __future__ import annotations

import json
from typing import Any

from copilot.compliance import RULES
from copilot.config import Settings
from copilot.tools import TRANSCRIPT_ID_RE, SqlParam, SqlRunner, ToolError

# The ordinary calls and the calls with a seeded breach are 582 together.
MAX_LISTED = 1000
# The value of the ``finding`` filter that means "any rule at all".
ANY_FINDING = "any"


def list_transcripts(sql: SqlRunner, settings: Settings) -> list[dict[str, str]]:
    """Id, topic and outcome of every redacted transcript, in id order."""
    table = settings.table("silver", "transcripts_redacted")
    rows = sql(
        "SELECT transcript_id, category, resolution "  # noqa: S608
        f"FROM {table} ORDER BY transcript_id LIMIT {MAX_LISTED}",
        {},
    )
    return [{key: str(value) for key, value in row.items()} for row in rows]


def list_calls(
    sql: SqlRunner, settings: Settings, finding: str | None = None
) -> list[dict[str, Any]]:
    """Every redacted call with the rules the rule check fired on it, in id order.

    Each call has ``transcript_id``, ``category``, ``resolution`` and
    ``findings``: the names of the rules that fired, an empty list when none
    did, and ``None`` when the pipeline has not checked the call. ``None`` is
    not "nothing found", and the interface says so.

    Args:
        sql: Runs the statement.
        settings: Names the catalog.
        finding: ``None`` for every call, ``"any"`` for the calls with at least
            one finding, or the name of a rule for the calls it fired on.

    Raises:
        ToolError: If ``finding`` is neither ``"any"`` nor the name of a rule.
            Nothing is looked up.
    """
    transcripts = settings.table("silver", "transcripts_redacted")
    insights = settings.table("gold", "call_insights")
    parameters: dict[str, SqlParam] = {}
    where = ""
    if finding is not None:
        finding = finding.strip().lower()
        if finding == ANY_FINDING:
            where = "WHERE i.n_findings > 0 "
        elif finding in RULES:
            # The rule's name is a bound value. Only fixed words are put in the statement.
            where = "WHERE array_contains(i.rules, :rule) "
            parameters["rule"] = ("STRING", finding)
        else:
            known = ", ".join((ANY_FINDING, *RULES))
            raise ToolError(f"The finding to filter on must be one of: {known}.")
    rows = sql(
        "SELECT t.transcript_id, t.category, t.resolution, to_json(i.rules) AS rules_json "  # noqa: S608
        f"FROM {transcripts} AS t LEFT JOIN {insights} AS i "
        "ON i.transcript_id = t.transcript_id "
        f"{where}ORDER BY t.transcript_id LIMIT {MAX_LISTED}",
        parameters,
    )
    return [
        {
            "transcript_id": str(row["transcript_id"]),
            "category": str(row["category"]),
            "resolution": str(row["resolution"]),
            "findings": _rule_names(row.get("rules_json")),
        }
        for row in rows
    ]


def _rule_names(rules_json: object) -> list[str] | None:
    """The rules of one row, or ``None`` for a call with no row in the insights table."""
    if rules_json is None:
        return None
    return [str(rule) for rule in json.loads(str(rules_json))]


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
