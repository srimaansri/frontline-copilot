"""What the rule check found in one call, in the shape ``gold.call_insights`` holds.

The pipeline calls ``insight_row`` once per redacted call and writes the result
as one row. The API calls ``findings_of`` on a single call when a supervisor
opens it. Both run ``copilot.compliance.check_call`` and add nothing to it.

One row per call, with the findings as an array, and not one row per finding:

* a call in which no rule fired still has a row, so "checked, nothing found" and
  "not checked yet" are different things in the table;
* the calls list joins it one to one, with no grouping;
* ``explode(findings)`` gives the long form to anyone who wants to count by rule.

Nothing here copies text from a call. A row holds the call id, counts, rule
names, turn numbers and the checker's own fixed sentences. This module imports
only the checker, so the pipeline's wheel can run it without the model stack.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from copilot.compliance import RULES, Finding, check_call


def findings_of(turns: Iterable[Mapping[str, Any]]) -> list[Finding]:
    """Run the rule check on one redacted call, as a table or the API hands it over.

    A turn read back from a table can hold a null where the checker expects
    text, and Spark hands a turn over as a row, not a dictionary. So each turn
    is read by key and brought to a plain ``speaker`` and ``text`` first.
    """
    plain = [
        {"speaker": str(turn["speaker"] or ""), "text": str(turn["text"] or "")} for turn in turns
    ]
    return check_call(plain)


def rules_fired(findings: Sequence[Finding]) -> list[str]:
    """The rules with at least one finding, each once, in the checker's own order."""
    fired = {finding.rule for finding in findings}
    return [rule for rule in RULES if rule in fired]


def finding_fields(finding: Finding) -> dict[str, Any]:
    """One finding as plain fields: the rule, the turn it points at, and why."""
    return {"rule": finding.rule, "turn_index": finding.turn_index, "reason": finding.reason}


def insight_row(transcript_id: str, turns: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The ``gold.call_insights`` row of one redacted call.

    Args:
        transcript_id: The call, such as T0207.
        turns: Its redacted turns, each with ``speaker`` and ``text``.

    Returns:
        ``transcript_id``, ``n_turns``, ``n_findings``, ``rules`` (the rules that
        fired, each once) and ``findings`` (rule, turn number and reason, earliest
        turn first). No value in it is text from the call.
    """
    findings = findings_of(turns)
    return {
        "transcript_id": transcript_id,
        "n_turns": len(turns),
        "n_findings": len(findings),
        "rules": rules_fired(findings),
        "findings": [finding_fields(finding) for finding in findings],
    }
