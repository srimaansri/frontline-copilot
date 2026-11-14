"""Data shapes passed between the copilot's parts and returned to callers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class CopilotAnswer(BaseModel):
    """What ``run_copilot`` returns. The app, the evaluation and the tests all read this."""

    model_config = ConfigDict(frozen=True)

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    escalated: bool = False
    guardrail_flags: list[str] = Field(default_factory=list)
