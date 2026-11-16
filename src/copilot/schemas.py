"""Data shapes passed between the copilot's parts and returned to callers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Urgency = Literal["low", "normal", "high"]
Sentiment = Literal["positive", "neutral", "negative"]
# How a call ended. The same three values the transcript generator records as
# ``resolution``; a test keeps the two lists equal.
Disposition = Literal["resolved", "escalated", "unresolved"]
# What a call was about. The transcript generator's categories; a test keeps the
# two lists equal.
CallCategory = Literal[
    "billing",
    "troubleshooting",
    "device_setup",
    "plan_change",
    "add_line",
    "international",
    "lost_stolen",
    "cancel_port",
    "accessibility",
    "scam",
]
# Who has to take the next step after a call: the customer, the agent who took
# the call, or another team.
FollowUpOwner = Literal["customer", "agent", "team"]


class KBHit(BaseModel):
    """One knowledge-base chunk returned by retrieval."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    url: str
    title: str
    text: str
    section: str | None = None
    heading: str | None = None
    score: float | None = None


class Citation(BaseModel):
    """A source the answer points to. ``number`` is the ``[n]`` used in the text."""

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    url: str


class Plan(BaseModel):
    """One row of the catalogue: a plan, an add-on or a fee."""

    model_config = ConfigDict(frozen=True)

    plan_id: str
    kind: str
    name: str
    # Price in USD for one ``billing_period``.
    monthly_price_usd: float
    billing_period: str
    # None means unlimited for a plan, and not applicable for add-ons and fees.
    data_gb: float | None = None
    talk_text: str | None = None
    hotspot_gb: float | None = None
    international: str | None = None
    notes: str | None = None


class CallSummary(BaseModel):
    """A structured summary of one redacted transcript."""

    model_config = ConfigDict(frozen=True)

    transcript_id: str
    summary_bullets: list[str] = Field(min_length=1, max_length=6)
    intent: str
    sentiment: Sentiment
    next_step: str
    related_articles: list[Citation] = Field(default_factory=list)


class FollowUp(BaseModel):
    """What is left to do after a call, and who has to do it."""

    model_config = ConfigDict(frozen=True)

    owner: FollowUpOwner
    action: str = Field(min_length=1)


class CallWrapUp(BaseModel):
    """The after-call record of one redacted transcript.

    From ``wrap_up_call`` it is the copilot's draft: the disposition and the
    category are worked out from the conversation alone. Nothing is stored until
    the agent has checked it and ``save_wrap_up`` is called with what they approved.
    """

    model_config = ConfigDict(frozen=True)

    transcript_id: str
    disposition: Disposition
    category: CallCategory
    notes: list[str] = Field(min_length=1, max_length=6)
    # What the agent told the customer would happen after the call.
    promises: list[str] = Field(default_factory=list, max_length=6)
    # None when nothing is left to do.
    follow_up: FollowUp | None = None
    sentiment: Sentiment
    related_articles: list[Citation] = Field(default_factory=list)


class SavedWrapUp(BaseModel):
    """A wrap-up as it was stored: every text field is the redacted one.

    ``recorded`` is false when the row could not be written, or when writing is
    turned off. The agent is told, and what they typed is still on their screen.
    """

    model_config = ConfigDict(frozen=True)

    wrapup_id: str
    transcript_id: str
    disposition: Disposition
    category: CallCategory
    notes: list[str]
    promises: list[str]
    follow_up: FollowUp | None
    sentiment: Sentiment
    recorded: bool


class EscalationTicket(BaseModel):
    """A hand-off to a human specialist.

    ``reason`` is stored and returned redacted. ``recorded`` is false when the
    ticket could not be written to the escalations table; the agent still gets
    a reference and a script, and the answer says the hand-off must be made by hand.
    """

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    category: str
    urgency: Urgency
    reason: str
    agent_script: str
    recorded: bool


class Usage(BaseModel):
    """What one answer cost in model work.

    Tokens are the counts the serving endpoint reports. A call whose reply
    carries no count adds to ``model_calls`` and to nothing else, so the token
    totals are a lower bound when ``calls_without_counts`` is not zero.
    """

    model_config = ConfigDict(frozen=True)

    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    calls_without_counts: int = 0

    @property
    def total_tokens(self) -> int:
        """Input and output tokens together."""
        return self.input_tokens + self.output_tokens

    def plus(self, reply: object) -> Usage:
        """This usage with one more model call, read from a chat model's reply."""
        counts = getattr(reply, "usage_metadata", None) or {}
        try:
            read = int(counts["input_tokens"]), int(counts["output_tokens"])
        except (KeyError, TypeError, ValueError):
            return self.model_copy(
                update={
                    "model_calls": self.model_calls + 1,
                    "calls_without_counts": self.calls_without_counts + 1,
                }
            )
        return self.model_copy(
            update={
                "model_calls": self.model_calls + 1,
                "input_tokens": self.input_tokens + read[0],
                "output_tokens": self.output_tokens + read[1],
            }
        )


class HandOffDraft(BaseModel):
    """A hand-off the copilot proposes. Nothing is written until a person approves it.

    ``reason`` is redacted. ``team`` is who would pick the ticket up, for showing.
    """

    model_config = ConfigDict(frozen=True)

    category: str
    urgency: Urgency = "normal"
    reason: str
    team: str


class CopilotAnswer(BaseModel):
    """What ``run_copilot`` returns. The app, the evaluation and the tests all read this."""

    model_config = ConfigDict(frozen=True)

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    escalated: bool = False
    guardrail_flags: list[str] = Field(default_factory=list)
    # The question as the copilot processed it: redacted, with placeholder numbers that
    # agree with the rest of the conversation.
    question_as_processed: str = ""
    # A hand-off waiting for the agent's approval. When this is set, ``escalated``
    # means the copilot decided a person is needed, and no ticket exists yet.
    handoff_draft: HandOffDraft | None = None
    # Model calls and tokens spent on this answer: the router, the model that
    # answers, and a rewrite if there was one.
    usage: Usage = Field(default_factory=Usage)
    # The text the answer was checked against: sources, tool results and the
    # conversation. Kept for evaluation only, so it is left out when the answer is
    # written to a trace or sent to the interface.
    evidence: list[str] = Field(default_factory=list, exclude=True, repr=False)
