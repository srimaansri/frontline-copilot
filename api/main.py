"""REST API for the Frontline Copilot, and the server for its web interface.

Run locally:  uvicorn api.main:app --port 8000
On Databricks Apps the command comes from app.yaml at the repository root.

This is a thin layer. Every endpoint calls the same ``copilot.agent`` and
``copilot.tools`` code that the evaluation and the MCP server call. The Calls
view's summary and its after-call wrap-up call their tools directly, not through
the agent graph; each tool applies the output check for personal data itself. A
wrap-up is drafted by one request and stored by another, which the agent sends
once they have checked it, and a third reads the stored record back when the
call is opened again. Call assist (``copilot.assist``) is asked for one
turn of a call at a time and holds no session. The rule check on a call
(``copilot.compliance``) is plain rules on the redacted turns, with no model
call: the calls list reads what the pipeline found, and the findings of one
call are worked out when it is opened. The built web interface in
``web/dist`` is served at ``/``, and the API lives under ``/api``.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal

import mlflow
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from mlflow.entities import AssessmentSource, AssessmentSourceType, SpanType
from pydantic import BaseModel, Field

from copilot.agent import Copilot
from copilot.assist import ASSIST_PROMPT_VERSION, MAX_TURN, AssistState, CallAssist
from copilot.call_insights import finding_fields, findings_of
from copilot.compliance import RULES
from copilot.config import Settings, load_settings
from copilot.guardrails import redact_question
from copilot.prompts import PROMPT_VERSION, WRAP_UP_PROMPT_VERSION
from copilot.schemas import (
    CallCategory,
    CallSummary,
    CallWrapUp,
    Citation,
    CopilotAnswer,
    Disposition,
    EscalationTicket,
    FollowUpOwner,
    HandOffDraft,
    SavedWrapUp,
    Sentiment,
    Usage,
)
from copilot.steps import Step, describe_steps
from copilot.tools import MAX_WRAP_UP_CHARS, ToolError, valid_transcript_id
from copilot.transcripts import get_transcript, list_calls
from copilot.wrapups import StoredWrapUp, latest_wrap_up

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
DISCLAIMER = (
    "Unofficial demo. Not affiliated with or endorsed by any carrier. "
    "Northline Wireless is fictional and all data is synthetic."
)
ASK_FAILED = "The copilot could not answer just now. Please try again."
# How a tool's message starts when the fault is on this side: the model wrote
# something unreadable, or the warehouse did not answer or is not set up.
SERVER_FAULTS = ("The model", "The data lookup", "SQL_WAREHOUSE_ID")
WRAP_UP_FAILED = "The wrap-up could not be drafted just now. Please try again."
SAVE_FAILED = "The wrap-up could not be saved just now. Please try again."
SAVED_WRAP_UP_FAILED = "The saved wrap-up could not be read just now. Please try again."
CALLS_FAILED = "The calls could not be read just now. Please try again."
SUMMARY_FAILED = "The summary could not be written just now. Please try again."
HAND_OFF_FAILED = "The hand-off could not be opened just now. Please try again."
FEEDBACK_FAILED = "The rating could not be saved just now. Please try again."
ASSIST_FAILED = "Call assist could not read this turn just now. Please try again."
FINDINGS_FAILED = "The rule check could not be run just now. Please try again."
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
    # A hand-off the copilot drafted. It is written only by POST /api/handoffs.
    handoff_draft: HandOffDraft | None = None
    # Model calls and tokens this answer took.
    usage: Usage = Field(default_factory=Usage)
    seconds: float
    trace_id: str | None
    steps: list[Step]


class HandOffRequest(BaseModel):
    """A hand-off the agent has checked, perhaps changed, and approved."""

    reason: str = Field(min_length=1, max_length=500)
    category: str = Field(default="other", max_length=40)
    urgency: Literal["low", "normal", "high"] = "normal"


class FollowUpBody(BaseModel):
    """The next step of a wrap-up and who takes it, as the agent left it."""

    owner: FollowUpOwner
    action: str = Field(min_length=1, max_length=MAX_WRAP_UP_CHARS)


class WrapUpSaveRequest(BaseModel):
    """An after-call wrap-up the agent has checked, perhaps changed, and approved.

    The call it belongs to is named in the address. The choices are checked here
    and every line has a longest length; the text is redacted by the tool.
    """

    disposition: Disposition
    category: CallCategory
    notes: list[Annotated[str, Field(max_length=MAX_WRAP_UP_CHARS)]] = Field(
        min_length=1, max_length=6
    )
    promises: list[Annotated[str, Field(max_length=MAX_WRAP_UP_CHARS)]] = Field(
        default_factory=list, max_length=6
    )
    follow_up: FollowUpBody | None = None
    sentiment: Sentiment


class RuleFinding(BaseModel):
    """One thing the rule check found in a call. No field holds text from the call."""

    # The rule's name, such as "card_read_back".
    rule: str
    # The turn it points at, counted from 0 in the call's turns.
    turn_index: int
    # The checker's own fixed sentence about that turn.
    reason: str


class CallFindings(BaseModel):
    """What the rule check found in one call, and which rules it ran.

    An empty ``findings`` means no rule fired. It does not mean the call is
    clean: the rules miss some breaches.
    """

    transcript_id: str
    findings: list[RuleFinding]
    rules_checked: list[str]


class AssistResponse(AssistState):
    """What the assist panel shows at one turn of a call, and how long it took to work out."""

    seconds: float


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

    def __init__(
        self,
        copilot: Copilot | None = None,
        tracing: bool | None = None,
        assist: CallAssist | None = None,
    ) -> None:
        """Use what is given; build the rest when it is first needed."""
        self._copilot = copilot
        self._tracing = tracing
        self._assist = assist

    @property
    def assist(self) -> CallAssist:
        """Call assist, on the copilot's own retriever, model, redactor and SQL runner.

        It is one object for the life of the server because it remembers the
        searches and next steps it has already paid for. It holds no session.
        """
        if self._assist is None:
            self._assist = CallAssist(self.copilot.tools)
        return self._assist

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
    assist: CallAssist | None = None,
) -> FastAPI:
    """Build the application.

    Args:
        copilot: The copilot to serve. Built from settings on first use if omitted.
        tracing: Whether answers are traced. Worked out from settings if omitted.
        static_dir: The built web interface. Not served if the folder does not exist.
        assist: Call assist. Built on the copilot's tools on first use if omitted.
    """
    runtime = Runtime(copilot, tracing, assist)
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
            _log_failure(error)
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
                    # The time lets a recording be replayed at its real pace.
                    on_stage=lambda event: events.put(
                        ("stage", {**event, "at": round(time.perf_counter() - started, 2)})
                    ),
                )
                seconds = time.perf_counter() - started
                trace_id = (
                    mlflow.get_last_active_trace_id(thread_local=True) if tracing_now else None
                )
                response = _ask_response(copilot_now, body, answer, seconds, trace_id)
                events.put(("answer", response.model_dump()))
            except Exception as error:
                _log_failure(error)
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
    def calls(
        finding: Annotated[str | None, Query(max_length=40)] = None,
    ) -> list[dict[str, Any]]:
        """Every call, each with the rules the rule check fired on it.

        ``findings`` is the list of rule names from ``gold.call_insights``, empty
        when no rule fired and null when the pipeline has not checked the call.
        ``?finding=any`` keeps the calls with a finding, and ``?finding=<rule>``
        the calls one rule fired on. The rule is a bound value in the statement.
        """
        copilot_now = runtime.copilot
        try:
            return list_calls(copilot_now.tools.sql, copilot_now.settings, finding)
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=CALLS_FAILED) from error

    @app.get("/api/calls/{transcript_id}")
    def call(transcript_id: str) -> dict[str, Any]:
        copilot_now = runtime.copilot
        try:
            turns = get_transcript(copilot_now.tools.sql, copilot_now.settings, transcript_id)
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=CALLS_FAILED) from error
        return {"transcript_id": transcript_id.strip().upper(), "turns": turns}

    @app.get("/api/calls/{transcript_id}/findings")
    def findings(transcript_id: str) -> CallFindings:
        """Run the rule check on one call, now, on its redacted turns.

        It is worked out here and not read from ``gold.call_insights``: the
        check is a few pattern matches, it needs no table the transcript
        endpoint does not already read, and the turn numbers it returns are
        those of the transcript as it is at this moment. No model is called and
        nothing is traced. A finding is a rule name, a turn number and fixed
        words, never text from the call.
        """
        copilot_now = runtime.copilot
        try:
            turns = get_transcript(copilot_now.tools.sql, copilot_now.settings, transcript_id)
            found = findings_of(turns)
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=FINDINGS_FAILED) from error
        return CallFindings(
            transcript_id=transcript_id.strip().upper(),
            findings=[RuleFinding(**finding_fields(finding)) for finding in found],
            rules_checked=list(RULES),
        )

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
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=SUMMARY_FAILED) from error

    @app.post("/api/calls/{transcript_id}/wrapup")
    def wrap_up(transcript_id: str) -> CallWrapUp:
        """Draft the after-call record of one call. Nothing is stored.

        The id is checked before anything else, so only a well-formed id is ever
        put on a trace. The draft that goes on the span has passed the tool's own
        output check, like a summary.
        """
        tools = runtime.copilot.tools
        try:
            call_id = valid_transcript_id(transcript_id)
            if not runtime.tracing:
                return tools.wrap_up_call(call_id)
            with mlflow.start_span(name="wrap_up_call", span_type=SpanType.TOOL) as span:
                span.set_inputs({"transcript_id": call_id})
                mlflow.update_current_trace(
                    tags={
                        "source": "web",
                        "view": "calls",
                        "wrap_up_prompt_version": WRAP_UP_PROMPT_VERSION,
                    }
                )
                result = tools.wrap_up_call(call_id)
                span.set_outputs(result.model_dump())
            return result
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=WRAP_UP_FAILED) from error

    @app.post("/api/calls/{transcript_id}/wrapup/save")
    def save_wrap_up(transcript_id: str, body: WrapUpSaveRequest) -> SavedWrapUp:
        """Store the wrap-up the agent approved. This is the only place one is written.

        The notes, the promises and the next step may have been typed by the
        agent, so they are never put on the trace as they arrived. The span's
        inputs are the call and the choices, which cannot hold free text, and its
        output is the wrap-up as it was stored, after the tool redacted it.
        """
        tools = runtime.copilot.tools
        try:
            call_id = valid_transcript_id(transcript_id)
            approved = CallWrapUp(transcript_id=call_id, **body.model_dump())
            if not runtime.tracing:
                return tools.save_wrap_up(approved)
            with mlflow.start_span(name="save_wrap_up", span_type=SpanType.TOOL) as span:
                span.set_inputs(
                    {
                        "transcript_id": call_id,
                        "disposition": body.disposition,
                        "category": body.category,
                        "sentiment": body.sentiment,
                        "follow_up_owner": body.follow_up.owner if body.follow_up else None,
                        "notes": len(body.notes),
                        "promises": len(body.promises),
                    }
                )
                mlflow.update_current_trace(tags={"source": "web", "view": "wrap_up"})
                saved = tools.save_wrap_up(approved)
                span.set_outputs(saved.model_dump())
            return saved
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=SAVE_FAILED) from error

    @app.get("/api/calls/{transcript_id}/wrapup/saved")
    def saved_wrap_up(transcript_id: str) -> StoredWrapUp | None:
        """The wrap-up most recently saved for one call, or null if none was.

        It is read from ``ops.call_wrapups`` as it was stored, so every line in
        it has already passed the output check: nothing is redacted again here
        and nothing is put on a trace. The record says when it was saved. It
        does not say by whom, because the table does not record that.
        """
        copilot_now = runtime.copilot
        try:
            return latest_wrap_up(copilot_now.tools.sql, copilot_now.settings, transcript_id)
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=SAVED_WRAP_UP_FAILED) from error

    @app.get("/api/calls/{transcript_id}/assist")
    def assist_at(
        transcript_id: str, turn: Annotated[int, Query(ge=0, le=MAX_TURN)]
    ) -> AssistResponse:
        """What call assist shows once a call has reached ``turn``, counted from 0.

        The page asks again as the replay moves on. Nothing about a replay is
        kept here: the answer for a turn is worked out from the call's first
        turn each time, and only finished searches and next steps are remembered,
        so asking twice costs nothing.

        The transcript comes from the redacted table, never from the request.
        The id is checked before anything else, so only a well-formed id and a
        number are put on a trace. What goes on the span as output has passed
        the output check: an article's own text, fixed words from the rules, and
        a next step with personal details replaced.
        """
        started = time.perf_counter()
        try:
            call_id = valid_transcript_id(transcript_id)
            if not runtime.tracing:
                state = runtime.assist.state(call_id, turn)
            else:
                with mlflow.start_span(name="call_assist", span_type=SpanType.TOOL) as span:
                    span.set_inputs({"transcript_id": call_id, "turn": turn})
                    mlflow.update_current_trace(
                        tags={
                            "source": "web",
                            "view": "call_assist",
                            "assist_prompt_version": ASSIST_PROMPT_VERSION,
                        }
                    )
                    state = runtime.assist.state(call_id, turn)
                    span.set_outputs(state.model_dump())
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=ASSIST_FAILED) from error
        return AssistResponse(**state.model_dump(), seconds=round(time.perf_counter() - started, 2))

    @app.post("/api/handoffs")
    def open_hand_off(body: HandOffRequest) -> EscalationTicket:
        """Write the hand-off the agent approved, and return its reference and script.

        This is the only place the web interface writes a ticket. The copilot
        itself only drafts one. The reason may have been edited by the agent, so
        it is redacted again by the tool before it is stored, and it is never put
        on the trace as it arrived: the span records the ticket, whose reason is
        the redacted one.
        """
        tools = runtime.copilot.tools
        try:
            if not runtime.tracing:
                return tools.escalate_to_human(body.reason, body.category, body.urgency)
            with mlflow.start_span(name="open_hand_off", span_type=SpanType.TOOL) as span:
                span.set_inputs({"category": body.category, "urgency": body.urgency})
                mlflow.update_current_trace(tags={"source": "web", "view": "hand_off"})
                ticket = tools.escalate_to_human(body.reason, body.category, body.urgency)
                span.set_outputs(ticket.model_dump())
            return ticket
        except ToolError as error:
            raise _tool_error(error) from error
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=HAND_OFF_FAILED) from error

    @app.post("/api/feedback")
    def feedback(body: FeedbackRequest) -> dict[str, bool]:
        if not runtime.tracing:
            raise HTTPException(status_code=503, detail="Feedback is off because tracing is off.")
        try:
            mlflow.log_feedback(
                trace_id=body.trace_id,
                name="agent_feedback",
                value=body.helpful,
                source=AssessmentSource(
                    source_type=AssessmentSourceType.HUMAN, source_id="web-user"
                ),
            )
        except Exception as error:
            _log_failure(error)
            raise HTTPException(status_code=502, detail=FEEDBACK_FAILED) from error
        return {"saved": True}

    if static_dir is not None and static_dir.is_dir():
        # Mounted last, so it only receives what no API route matched.
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


def _log_failure(error: BaseException) -> None:
    """Log that an answer failed: the kind of error and where it was raised. Nothing else.

    An error's message can quote the question, and so can the values a full
    traceback shows. ``logger.exception`` writes both, which is why it is not
    used here. The kind of error and the line that raised it are enough to find
    the cause, and neither can hold a customer's details.
    """
    frames = traceback.extract_tb(error.__traceback__)
    where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else "unknown"
    logger.error("The copilot failed to answer (%s at %s)", type(error).__name__, where)


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
    """A missing transcript is 404. A fault of the model or the warehouse is 502.

    Anything else a tool rejects is the caller's mistake. A tool's own messages
    are fixed words and an id, so they are safe to return.
    """
    message = str(error)
    if message.startswith("No transcript"):
        status = 404
    elif message.startswith(SERVER_FAULTS):
        status = 502
    else:
        status = 400
    return HTTPException(status_code=status, detail=message)


app = create_app()
