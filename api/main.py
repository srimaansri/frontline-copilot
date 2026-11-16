"""REST API for the Frontline Copilot, and the server for its web interface.

Run locally:  uvicorn api.main:app --port 8000
On Databricks Apps the command comes from app.yaml at the repository root.

This is a thin layer. Every endpoint calls the same ``copilot.agent`` and
``copilot.tools`` code that the evaluation and the MCP server call. The Calls
view's summary calls the summary tool directly, not through the agent graph;
the tool applies the output check for personal data itself. The built web interface in
``web/dist`` is served at ``/``, and the API lives under ``/api``.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import mlflow
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from mlflow.entities import AssessmentSource, AssessmentSourceType, SpanType
from pydantic import BaseModel, Field

from copilot.agent import Copilot
from copilot.config import Settings, load_settings
from copilot.guardrails import redact_question
from copilot.prompts import PROMPT_VERSION
from copilot.schemas import CallSummary, Citation, CopilotAnswer
from copilot.steps import Step, describe_steps
from copilot.tools import ToolError
from copilot.transcripts import get_transcript, list_transcripts

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
DISCLAIMER = (
    "Unofficial demo. Not affiliated with or endorsed by any carrier. "
    "Northline Wireless is fictional and all data is synthetic."
)
ASK_FAILED = "The copilot could not answer just now. Please try again."
TOOLS: tuple[tuple[str, str], ...] = (
    ("search_kb", "Help articles"),
    ("get_plan_details", "Plan catalogue"),
    ("summarize_call", "Call summary"),
    ("escalate_to_human", "Hand-off to a person"),
)
# (question, the tool it shows, what it shows)
EXAMPLES: tuple[tuple[str, str, str], ...] = (
    (
        "How much is the late payment fee, and can it be waived?",
        "search_kb",
        "An answer from the help articles, with its source",
    ),
    ("Which plans cost $25 a month or less?", "get_plan_details", "A lookup in the plan catalogue"),
    ("Summarize call T0002.", "summarize_call", "A summary of a redacted call"),
    (
        "Refund the $5 late fee on this customer's account.",
        "escalate_to_human",
        "A request that needs a person",
    ),
)


class Turn(BaseModel):
    """One earlier message in the conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    """A question, with the conversation so far."""

    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=40)


class AskResponse(BaseModel):
    """The answer and everything the interface shows about it."""

    answer: str
    question_as_processed: str
    citations: list[Citation]
    tools_used: list[str]
    escalated: bool
    guardrail_flags: list[str]
    seconds: float
    trace_id: str | None
    steps: list[Step]


class FeedbackRequest(BaseModel):
    """A thumbs up or down on one answer."""

    trace_id: str = Field(min_length=1, max_length=200)
    helpful: bool


def start_tracing(settings: Settings) -> bool:
    """Point MLflow at the workspace experiment. Returns whether tracing is on.

    The API still answers without a tracking server; it only loses traces.
    """
    if not settings.mlflow_experiment:
        mlflow.tracing.disable()
        return False
    try:
        mlflow.set_tracking_uri("databricks")
        # Locally this is a workspace path. On Databricks Apps the experiment is
        # an app resource and arrives as its numeric id.
        if settings.mlflow_experiment.isdigit():
            mlflow.set_experiment(experiment_id=settings.mlflow_experiment)
        else:
            mlflow.set_experiment(settings.mlflow_experiment)
    except Exception:
        logger.warning("MLflow is not reachable; answers will not be traced")
        mlflow.tracing.disable()
        return False
    return True


class Runtime:
    """The copilot and its settings, built on the first request that needs them."""

    def __init__(self, copilot: Copilot | None = None, tracing: bool | None = None) -> None:
        """Use ``copilot`` and ``tracing`` if given; otherwise build them when first needed."""
        self._copilot = copilot
        self._tracing = tracing

    @property
    def copilot(self) -> Copilot:
        """The copilot. Building it also decides whether tracing is on."""
        if self._copilot is None:
            load_dotenv()
            settings = load_settings()
            if self._tracing is None:
                self._tracing = start_tracing(settings)
            self._copilot = Copilot(settings)
        return self._copilot

    @property
    def tracing(self) -> bool:
        """Whether answers are traced to MLflow."""
        if self._tracing is None:
            self._tracing = start_tracing(self.copilot.settings)
        return self._tracing


def create_app(
    copilot: Copilot | None = None,
    *,
    tracing: bool | None = None,
    static_dir: Path | None = STATIC_DIR,
) -> FastAPI:
    """Build the application.

    Args:
        copilot: The copilot to serve. Built from settings on first use if omitted.
        tracing: Whether answers are traced. Worked out from settings if omitted.
        static_dir: The built web interface. Not served if the folder does not exist.
    """
    runtime = Runtime(copilot, tracing)
    app = FastAPI(title="Frontline Copilot API", version="1.0.0", docs_url="/api/docs")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        settings = runtime.copilot.settings
        return {
            "app_name": "Frontline Copilot",
            "carrier": "Northline Wireless",
            "model": settings.llm_endpoint,
            "prompt_version": PROMPT_VERSION,
            "search": {
                "chunk_config": settings.chunk_config,
                "query_type": settings.query_type,
                "top_k": settings.top_k,
            },
            "tracing": runtime.tracing,
            "tools": [{"name": name, "label": label} for name, label in TOOLS],
            "examples": [
                {"question": question, "tool": tool, "hint": hint}
                for question, tool, hint in EXAMPLES
            ],
            "disclaimer": DISCLAIMER,
        }

    @app.post("/api/ask")
    def ask(body: AskRequest) -> AskResponse:
        copilot_now = runtime.copilot
        tracing_now = runtime.tracing
        started = time.perf_counter()
        try:
            answer = copilot_now.run(
                body.question,
                [turn.model_dump() for turn in body.history],
                trace_tags={"source": "web"},
            )
        except Exception as error:
            # The reason may quote the question, so only its type is logged or returned.
            logger.exception("The copilot failed to answer (%s)", type(error).__name__)
            raise HTTPException(status_code=502, detail=ASK_FAILED) from error
        seconds = time.perf_counter() - started
        trace_id = mlflow.get_last_active_trace_id(thread_local=True) if tracing_now else None
        return _ask_response(copilot_now, body, answer, seconds, trace_id)

    @app.post("/api/ask/stream")
    def ask_stream(body: AskRequest) -> StreamingResponse:
        """The same answer as ``/api/ask``, with each stage reported as it starts.

        The reply is a stream of server-sent events: ``stage`` events while the
        copilot works, then one ``answer`` event with the body ``/api/ask``
        returns, or one ``error`` event. A stage event holds a stage name and
        fixed words, never the question or any text a tool returned.

        The answer is worked out on one thread, so that its trace is whole, and
        the events cross to the response through a queue.
        """
        copilot_now = runtime.copilot
        tracing_now = runtime.tracing
        events: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

        def work() -> None:
            started = time.perf_counter()
            try:
                answer = copilot_now.run(
                    body.question,
                    [turn.model_dump() for turn in body.history],
                    trace_tags={"source": "web"},
                    on_stage=lambda event: events.put(("stage", event)),
                )
                seconds = time.perf_counter() - started
                trace_id = (
                    mlflow.get_last_active_trace_id(thread_local=True) if tracing_now else None
                )
                response = _ask_response(copilot_now, body, answer, seconds, trace_id)
                events.put(("answer", response.model_dump()))
            except Exception as error:
                # The reason may quote the question, so only its type is logged or sent.
                logger.exception("The copilot failed to answer (%s)", type(error).__name__)
                events.put(("error", {"detail": ASK_FAILED}))
            finally:
                events.put(None)

        threading.Thread(target=work, name="copilot-answer", daemon=True).start()

        def stream() -> Iterator[str]:
            while (item := events.get()) is not None:
                name, data = item
                yield f"event: {name}\ndata: {json.dumps(data)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            # A proxy that buffers the reply would hold every stage back until the end.
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/calls")
    def calls() -> list[dict[str, str]]:
        copilot_now = runtime.copilot
        return list_transcripts(copilot_now.tools.sql, copilot_now.settings)

    @app.get("/api/calls/{transcript_id}")
    def call(transcript_id: str) -> dict[str, Any]:
        copilot_now = runtime.copilot
        try:
            turns = get_transcript(copilot_now.tools.sql, copilot_now.settings, transcript_id)
        except ToolError as error:
            raise _tool_error(error) from error
        return {"transcript_id": transcript_id.strip().upper(), "turns": turns}

    @app.post("/api/calls/{transcript_id}/summary")
    def summary(transcript_id: str) -> CallSummary:
        tools = runtime.copilot.tools
        try:
            if not runtime.tracing:
                return tools.summarize_call(transcript_id)
            # Traced like an answer, so a summary made from the Calls view can be found
            # and rated. A transcript id is not personal data, and the summary has
            # passed the tool's own output check.
            with mlflow.start_span(name="summarize_call", span_type=SpanType.TOOL) as span:
                span.set_inputs({"transcript_id": transcript_id.strip().upper()[:20]})
                mlflow.update_current_trace(tags={"source": "web", "view": "calls"})
                result = tools.summarize_call(transcript_id)
                span.set_outputs(result.model_dump())
            return result
        except ToolError as error:
            raise _tool_error(error) from error

    @app.post("/api/feedback")
    def feedback(body: FeedbackRequest) -> dict[str, bool]:
        if not runtime.tracing:
            raise HTTPException(status_code=503, detail="Feedback is off because tracing is off.")
        mlflow.log_feedback(
            trace_id=body.trace_id,
            name="agent_feedback",
            value=body.helpful,
            source=AssessmentSource(source_type=AssessmentSourceType.HUMAN, source_id="web-user"),
        )
        return {"saved": True}

    if static_dir is not None and static_dir.is_dir():
        # Mounted last, so it only receives what no API route matched.
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


def _ask_response(
    copilot: Copilot, body: AskRequest, answer: CopilotAnswer, seconds: float, trace_id: str | None
) -> AskResponse:
    """What the interface is sent for one answer."""
    fields = answer.model_dump()
    # The copilot reports the question as it processed it. One that does not is asked
    # here, so the interface never shows the question as it was typed.
    processed = fields.pop("question_as_processed", "")
    return AskResponse(
        **fields,
        question_as_processed=processed or redact_question(body.question, copilot.redactor).text,
        seconds=round(seconds, 2),
        trace_id=trace_id,
        steps=describe_steps(answer),
    )


def _tool_error(error: ToolError) -> HTTPException:
    """A missing transcript is 404. Anything else a tool rejects is the caller's mistake."""
    status = 404 if str(error).startswith("No transcript") else 400
    return HTTPException(status_code=status, detail=str(error))


app = create_app()
