"""Data shapes passed between the copilot's parts and returned to callers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Urgency = Literal["low", "normal", "high"]
Sentiment = Literal["positive", "neutral", "negative"]


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


class CopilotAnswer(BaseModel):
    """What ``run_copilot`` returns. The app, the evaluation and the tests all read this."""

    model_config = ConfigDict(frozen=True)

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    escalated: bool = False
    guardrail_flags: list[str] = Field(default_factory=list)
