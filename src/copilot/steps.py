"""A plain-language account of what the copilot did to produce one answer.

The interface shows this next to each answer: what was removed from the
question, how the request was routed, which tools ran and what the output
checks found. It is derived from the answer itself (its tools, citations and
guardrail flags), so it says nothing the copilot did not record.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from copilot.schemas import CopilotAnswer

Stage = Literal["redaction", "input_check", "tool", "output_check"]
Status = Literal["ok", "notice", "warning", "blocked"]

# How each kind of personal data is named to a reader.
PERSONAL_DETAILS: dict[str, str] = {
    "PERSON": "a name",
    "PHONE_NUMBER": "a phone number",
    "EMAIL_ADDRESS": "an email address",
    "ADDRESS": "an address",
    "DATE_OF_BIRTH": "a date of birth",
    "ACCOUNT_NUMBER": "an account number",
    "IMEI": "a device IMEI",
    "ICCID": "a SIM number",
    "SSN_LAST4": "Social Security digits",
    "CREDIT_CARD": "a card number",
    "CPNI_AMOUNT": "a bill amount",
    "CPNI_USAGE": "a usage figure",
}
# Tool name -> (what it did, what that means).
TOOL_STEPS: dict[str, tuple[str, str]] = {
    "search_kb": ("Searched the help articles", ""),
    "get_plan_details": (
        "Looked up the plan catalogue",
        "Prices and features come from the catalogue table, not from memory.",
    ),
    "summarize_call": ("Summarized the call", "Read from the redacted transcript only."),
    "escalate_to_human": (
        "Opened a hand-off",
        "A ticket was written for a human specialist, with the reason redacted.",
    ),
}


# The reference a hand-off ticket is given, as it appears in the answer.
TICKET_REFERENCE_RE = re.compile(r"ESC-[0-9A-F]{8}")


class Step(BaseModel):
    """One thing the copilot did, in the order it did it."""

    model_config = ConfigDict(frozen=True)

    stage: Stage
    title: str
    detail: str
    status: Status
    tool: str | None = None
    # The ticket reference, on the hand-off step only, so the interface can
    # show who now has the request.
    reference: str | None = None


def _listed(items: list[str]) -> str:
    """Join items as "a, b and c"."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _details(flags: list[str], prefix: str) -> list[str]:
    """Readable names of the personal details carried by flags such as ``prefix:PERSON``."""
    kinds = [flag.split(":", 1)[1] for flag in flags if flag.startswith(prefix + ":")]
    return [PERSONAL_DETAILS.get(kind, kind.lower().replace("_", " ")) for kind in kinds]


def describe_steps(answer: CopilotAnswer) -> list[Step]:
    """Turn an answer's tools, citations and guardrail flags into ordered steps."""
    flags = answer.guardrail_flags
    names = {flag.split(":", 1)[0] for flag in flags}
    steps: list[Step] = []

    found = _details(flags, "pii_in_question")
    if found:
        verb = "was" if len(found) == 1 else "were"
        text = _listed(found)
        steps.append(
            Step(
                stage="redaction",
                title="Personal details removed",
                detail=f"{text[0].upper()}{text[1:]} {verb} replaced before the question "
                "was processed or logged.",
                status="notice",
            )
        )
    else:
        steps.append(
            Step(
                stage="redaction",
                title="No personal details found",
                detail="The question was checked before anything was logged.",
                status="ok",
            )
        )

    if "injection_suspected" in names:
        steps.append(
            Step(
                stage="input_check",
                title="Override attempt blocked",
                detail="The request tried to change the copilot's instructions. "
                "No model was called.",
                status="blocked",
            )
        )
    elif "account_action_requested" in names:
        steps.append(
            Step(
                stage="input_check",
                title="Account request: handed to a person",
                detail="The copilot cannot change or look up a customer's account.",
                status="warning",
            )
        )
    else:
        steps.append(
            Step(
                stage="input_check",
                title="Request allowed",
                detail="Not an account change and not an attempt to override the instructions.",
                status="ok",
            )
        )

    if "history_turn_dropped" in names:
        steps.append(
            Step(
                stage="input_check",
                title="An earlier message was left out",
                detail="It tried to change the copilot's instructions, so it was not "
                "passed on with this question.",
                status="notice",
            )
        )

    failed_tools = {flag.split(":", 1)[1] for flag in flags if flag.startswith("tool_error:")}
    for tool in answer.tools_used:
        title, detail = TOOL_STEPS.get(tool, (f"Used {tool}", ""))
        status: Status = "ok"
        if tool in failed_tools:
            detail, status = "The lookup failed, and the copilot said so.", "warning"
        elif tool == "search_kb":
            cited = len(answer.citations)
            if "no_context" in names:
                detail, status = "No article matched.", "notice"
            elif cited:
                detail = f"{cited} source{'' if cited == 1 else 's'} cited."
            else:
                detail = "Articles were found. The answer cites none of them."
        reference = None
        if tool == "escalate_to_human":
            found_reference = TICKET_REFERENCE_RE.search(answer.answer)
            reference = found_reference.group(0) if found_reference else None
        steps.append(
            Step(
                stage="tool",
                title=title,
                detail=detail,
                status=status,
                tool=tool,
                reference=reference,
            )
        )

    if "tool_limit_reached" in names:
        steps.append(
            Step(
                stage="output_check",
                title="Stopped after the lookup limit",
                detail="The copilot answered with what it had found so far.",
                status="notice",
            )
        )
    if "empty_answer" in names:
        steps.append(
            Step(
                stage="output_check",
                title="No answer was produced",
                detail="A plain fallback was shown in its place.",
                status="warning",
            )
        )
    if "answer_simplified" in names:
        steps.append(
            Step(
                stage="output_check",
                title="Rewritten in plainer words",
                detail="The first draft was above the reading target.",
                status="notice",
            )
        )
    if "invalid_citation_removed" in names:
        steps.append(
            Step(
                stage="output_check",
                title="A citation was removed",
                detail="It pointed to a source that was not retrieved.",
                status="warning",
            )
        )
    elif answer.citations:
        steps.append(
            Step(
                stage="output_check",
                title="Citations checked",
                detail="Every citation points to a retrieved source.",
                status="ok",
            )
        )
    kept_out = _details(flags, "pii_removed_from_answer")
    if kept_out:
        steps.append(
            Step(
                stage="output_check",
                title="Personal details kept out of the answer",
                detail=f"The draft contained {_listed(kept_out)} that was in none of its "
                "sources. It was replaced.",
                status="warning",
            )
        )
    else:
        steps.append(
            Step(
                stage="output_check",
                title="No personal details in the answer",
                detail="Checked against the sources the answer was written from.",
                status="ok",
            )
        )
    return steps
