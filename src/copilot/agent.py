"""The copilot's entry point: ``run_copilot``.

The copilot is a small LangGraph graph::

    START -> input_guard -+-> escalate ----------------+
                          +-> refuse ------------------+-> output_guard -> END
                          +-> agent <-> tools ---------+

Order of work, and why:

1. Redact the question. This happens *outside* any MLflow span, because a span
   records its inputs as soon as it opens.
2. Open the trace with the redacted question only.
3. ``input_guard`` routes a request to act on one customer's account straight to
   a hand-off, and an attempt to override the instructions to a fixed refusal.
   Neither costs a model call.
4. Otherwise the model chooses tools, for at most ``max_tool_iterations`` rounds.
5. ``output_guard`` checks reading level, citations and personal data.

Spans are opened by hand and not by autologging, so exactly what is recorded on
a trace is decided here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Annotated, Any, Literal, TypedDict

import mlflow
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from mlflow.entities import SpanType

from copilot.config import Settings, get_settings
from copilot.guardrails import (
    CANNOT_DO,
    FLAG_NO_CITATION,
    REFUSAL_ANSWER,
    check_input,
    check_output,
    redact_conversation,
)
from copilot.llm import ChatModel, build_chat_model, message_text
from copilot.prompts import (
    AGENT_SYSTEM_PROMPT,
    FINAL_ANSWER_NOTE,
    PROMPT_VERSION,
    SIMPLIFY_PROMPT,
)
from copilot.redaction import Redactor, get_redactor
from copilot.retriever import Retriever
from copilot.schemas import Citation, CopilotAnswer, KBHit, Urgency
from copilot.tools import ESCALATION_TEAMS, ToolError, Tools

logger = logging.getLogger(__name__)

FLAG_NO_CONTEXT = "no_context"
FLAG_TOOL_ERROR = "tool_error"
FLAG_EMPTY_ANSWER = "empty_answer"
FLAG_TOOL_LIMIT = "tool_limit_reached"

TOOL_SEARCH_KB = "search_kb"
TOOL_PLAN_DETAILS = "get_plan_details"
TOOL_SUMMARIZE_CALL = "summarize_call"
TOOL_ESCALATE = "escalate_to_human"

EMPTY_ANSWER = (
    "I could not put an answer together for this. Please pass the question to a human specialist."
)
NO_ARTICLE_FOUND = "No help article matched this search."
NO_PLAN_FOUND = "No row in the plan catalogue matched."

# Tool definitions in the OpenAI function format. The schemas are kept flat on
# purpose: the serving endpoint accepts no `anyOf` or `pattern`, which is what a
# schema generated from optional Python types would contain.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": TOOL_SEARCH_KB,
            "description": (
                "Search Northline's help articles. Returns numbered sources to cite. Use for "
                "how something works, steps, policies and fees."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    # No section filter is offered. In a live run the model guessed
                    # "Account" for a voicemail question; that section has articles, so
                    # the search returned them and never looked where the answer was.
                    "query": {"type": "string", "description": "What to look for, in plain words."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_PLAN_DETAILS,
            "description": (
                "Look up plans, add-ons and fees in the catalogue: price, data, hotspot and "
                "international features. Leave every argument out to list the whole catalogue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {
                        "type": "string",
                        "description": "Optional. All or part of a plan, add-on or fee name.",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Optional. Only monthly plans at or under this price.",
                    },
                    "needs_international": {
                        "type": "boolean",
                        "description": "Optional. True for plans with international features.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_SUMMARIZE_CALL,
            "description": "Summarize one support call from its transcript id, such as T0007.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transcript_id": {
                        "type": "string",
                        "description": "The id exactly as the agent gave it.",
                    }
                },
                "required": ["transcript_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_ESCALATE,
            "description": (
                "Hand the customer to a human specialist. Only for a request to change, cancel, "
                "refund or look up something on one customer's account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "One sentence on what is needed. No personal details.",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "One of: billing, plan_change, account_access, device, "
                            "cancellation, other."
                        ),
                    },
                    "urgency": {"type": "string", "description": "One of: low, normal, high."},
                },
                "required": ["reason"],
            },
        },
    },
]

Route = Literal["agent", "escalate", "refuse"]


class CopilotState(TypedDict):
    """What the graph carries from node to node."""

    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    route: Route
    category: str
    flags: list[str]
    retrieved: list[KBHit]
    # Text the answer was written from: retrieved chunks and tool results.
    sources: list[str]
    tools_used: list[str]
    escalated: bool
    iterations: int
    draft: str
    cited: list[int]
    # Everything a figure in the answer may come from: the sources and the conversation.
    evidence: list[str]


def format_sources(hits: Sequence[KBHit], first_number: int) -> str:
    """Render hits as numbered sources, numbered on from ``first_number``."""
    blocks = [
        f'<source number="{number}" title="{hit.title}">\n{hit.text.strip()}\n</source>'
        for number, hit in enumerate(hits, start=first_number)
    ]
    return "<context>\n" + "\n\n".join(blocks) + "\n</context>"


def _as_number(value: Any) -> float | None:
    """A price argument as a number. Models send 25, 25.0 or "25"."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Copilot:
    """Answers a support agent's question, using tools and checking what it says."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        retriever: Retriever | None = None,
        chat_model: ChatModel | None = None,
        redactor: Redactor | None = None,
        tools: Tools | None = None,
    ) -> None:
        """Build a copilot. Parts that are not passed in are created on first use."""
        self.settings = settings or get_settings()
        self._retriever = retriever
        self._chat_model = chat_model
        self._redactor = redactor
        self._tools = tools
        self._graph: Any = None

    # --- parts, built on first use ---------------------------------------------------------

    def _get_redactor(self) -> Redactor:
        if self._redactor is None:
            self._redactor = get_redactor(product_names=tuple(self.settings.product_names))
        return self._redactor

    def _get_model(self) -> ChatModel:
        if self._chat_model is None:
            self._chat_model = build_chat_model(self.settings)
        return self._chat_model

    @property
    def redactor(self) -> Redactor:
        """The redactor this copilot applies to questions, for callers that show its result."""
        return self._get_redactor()

    @property
    def tools(self) -> Tools:
        """The tools this copilot uses, for callers that need one directly, such as the app."""
        return self._get_tools()

    def _get_tools(self) -> Tools:
        if self._tools is None:
            self._tools = Tools(
                self.settings,
                retriever=self._retriever,
                llm=self._chat_model,
                redactor=self._get_redactor(),
            )
        return self._tools

    # --- entry point -------------------------------------------------------------------------

    def run(
        self,
        question: str,
        history: Sequence[Mapping[str, str]] | None = None,
        *,
        trace_tags: Mapping[str, str] | None = None,
    ) -> CopilotAnswer:
        """Answer one question.

        Args:
            question: What the support agent typed. May contain personal data.
            history: Earlier turns as ``{"role": ..., "content": ...}``, oldest first.
            trace_tags: Extra tags for the trace, such as an evaluation row id.
                The caller must not put personal data in them.

        Returns:
            The answer, its citations, the tools used and any guardrail flags.
        """
        safe = redact_conversation(question, history or [], self._get_redactor())
        # Nothing above this line is traced. Only redacted text goes below it.
        return self._answer(safe.question, list(safe.history), list(safe.flags), trace_tags or {})

    def _answer(
        self,
        question: str,
        history: list[tuple[str, str]],
        flags: list[str],
        trace_tags: Mapping[str, str],
    ) -> CopilotAnswer:
        settings = self.settings
        if self._graph is None:
            self._graph = self._build_graph()
        messages: list[AnyMessage] = [SystemMessage(AGENT_SYSTEM_PROMPT)]
        for role, text in history:
            messages.append(AIMessage(text) if role == "assistant" else HumanMessage(text))
        messages.append(HumanMessage(question))
        start: CopilotState = {
            "messages": messages,
            "question": question,
            "route": "agent",
            "category": "other",
            "flags": flags,
            "retrieved": [],
            "sources": [],
            "tools_used": [],
            "escalated": False,
            "iterations": 0,
            "draft": "",
            "cited": [],
            "evidence": [],
        }
        with mlflow.start_span(name="run_copilot", span_type=SpanType.AGENT) as root:
            root.set_inputs({"question": question, "history_turns": len(history)})
            mlflow.update_current_trace(
                tags={
                    **trace_tags,
                    "prompt_version": PROMPT_VERSION,
                    "chunk_config": settings.chunk_config,
                    "query_type": settings.query_type,
                    "llm_endpoint": settings.llm_endpoint,
                }
            )
            final: CopilotState = self._graph.invoke(
                start, config={"recursion_limit": 2 * settings.max_tool_iterations + 10}
            )
            retrieved = final["retrieved"]
            answer = CopilotAnswer(
                answer=final["draft"],
                citations=[
                    Citation(
                        number=number,
                        title=retrieved[number - 1].title,
                        url=retrieved[number - 1].url,
                    )
                    for number in final["cited"]
                ],
                tools_used=final["tools_used"],
                escalated=final["escalated"],
                guardrail_flags=final["flags"],
                question_as_processed=question,
                evidence=final["evidence"],
            )
            root.set_outputs(answer.model_dump())
        return answer

    # --- the graph -----------------------------------------------------------------------------

    def _build_graph(self) -> Any:
        graph = StateGraph(CopilotState)
        graph.add_node("input_guard", self._input_guard)
        graph.add_node("escalate", self._escalate)
        graph.add_node("refuse", self._refuse)
        graph.add_node("agent", self._agent)
        graph.add_node("tools", self._run_tools)
        graph.add_node("output_guard", self._output_guard)
        graph.add_edge(START, "input_guard")
        graph.add_conditional_edges(
            "input_guard",
            lambda state: state["route"],
            {"agent": "agent", "escalate": "escalate", "refuse": "refuse"},
        )
        graph.add_edge("escalate", "output_guard")
        graph.add_edge("refuse", "output_guard")
        graph.add_conditional_edges(
            "agent", self._after_agent, {"tools": "tools", "output_guard": "output_guard"}
        )
        graph.add_edge("tools", "agent")
        graph.add_edge("output_guard", END)
        return graph.compile()

    def _input_guard(self, state: CopilotState) -> dict[str, Any]:
        check = check_input(state["question"])
        return {
            "route": check.route,
            "category": check.category,
            "flags": [*state["flags"], *check.flags],
        }

    def _escalate(self, state: CopilotState) -> dict[str, Any]:
        """Open a hand-off without asking the model. The request itself is the reason."""
        category = state["category"]
        # "usage" is a kind of request the guard tells apart; the team that handles it
        # is the one that handles account access.
        team_category = category if category in ESCALATION_TEAMS else "account_access"
        if category == "other":
            team_category = "other"
        with mlflow.start_span(name=f"tool_{TOOL_ESCALATE}", span_type=SpanType.TOOL) as span:
            span.set_inputs({"category": team_category, "urgency": "normal"})
            ticket = self._get_tools().escalate_to_human(state["question"], team_category)
            span.set_outputs(ticket.model_dump())
        team = ESCALATION_TEAMS[ticket.category]
        cannot = CANNOT_DO.get(category, CANNOT_DO["other"])
        draft = (
            f"{cannot} This needs a human specialist: {team} has to handle it.\n\n"
            f'What to tell the customer: "{ticket.agent_script}"'
        )
        return {
            "draft": draft,
            "escalated": True,
            "tools_used": [TOOL_ESCALATE],
            "sources": [draft],
        }

    def _refuse(self, state: CopilotState) -> dict[str, Any]:
        return {"draft": REFUSAL_ANSWER, "sources": [REFUSAL_ANSWER]}

    def _agent(self, state: CopilotState) -> dict[str, Any]:
        """One model turn. On the turn after the last allowed tool round, no tools are offered."""
        iterations = state["iterations"] + 1
        out_of_rounds = iterations > self.settings.max_tool_iterations
        messages = list(state["messages"])
        flags = state["flags"]
        if out_of_rounds:
            messages.append(HumanMessage(FINAL_ANSWER_NOTE))
            flags = [*flags, FLAG_TOOL_LIMIT]
            model: Any = self._get_model()
        else:
            model = self._get_model().bind_tools(TOOL_SPECS)
        with mlflow.start_span(name="generate_answer", span_type=SpanType.CHAT_MODEL) as span:
            span.set_inputs(
                {
                    "messages": [
                        {"role": message.type, "content": message_text(message)}
                        for message in messages
                    ],
                    "tools_offered": not out_of_rounds,
                }
            )
            reply = model.invoke(messages)
            calls = [] if out_of_rounds else list(getattr(reply, "tool_calls", None) or [])
            span.set_outputs(
                {"content": message_text(reply), "tool_calls": [call["name"] for call in calls]}
            )
        if not isinstance(reply, AIMessage):
            reply = AIMessage(message_text(reply))
        return {"messages": [reply], "iterations": iterations, "flags": flags}

    def _after_agent(self, state: CopilotState) -> str:
        last = state["messages"][-1]
        wants_tools = bool(getattr(last, "tool_calls", None))
        within_rounds = state["iterations"] <= self.settings.max_tool_iterations
        return "tools" if wants_tools and within_rounds else "output_guard"

    def _run_tools(self, state: CopilotState) -> dict[str, Any]:
        """Run every tool the model asked for and hand the results back to it."""
        retrieved = list(state["retrieved"])
        sources = list(state["sources"])
        tools_used = list(state["tools_used"])
        flags = list(state["flags"])
        escalated = state["escalated"]
        results: list[ToolMessage] = []
        for call in getattr(state["messages"][-1], "tool_calls", None) or []:
            name = str(call["name"])
            arguments = call.get("args") or {}
            with mlflow.start_span(name=f"tool_{name}", span_type=SpanType.TOOL) as span:
                span.set_inputs(dict(arguments))
                try:
                    text, did_escalate = self._call_tool(name, arguments, retrieved)
                except ToolError as error:
                    text, did_escalate = f"Tool error: {error}", False
                    flags.append(f"{FLAG_TOOL_ERROR}:{name}")
                except Exception as error:
                    # A tool that cannot be reached must not end the answer: the model is
                    # told, and tells the agent, that the lookup failed. Only the kind of
                    # error is logged, because its message can quote the question.
                    logger.warning("Tool %s failed (%s)", name, type(error).__name__)
                    text, did_escalate = "Tool error: the lookup could not be completed.", False
                    flags.append(f"{FLAG_TOOL_ERROR}:{name}")
                span.set_outputs(text)
            if name not in tools_used:
                tools_used.append(name)
            escalated = escalated or did_escalate
            sources.append(text)
            results.append(ToolMessage(content=text, tool_call_id=str(call.get("id")), name=name))
        return {
            "messages": results,
            "retrieved": retrieved,
            "sources": sources,
            "tools_used": tools_used,
            "flags": flags,
            "escalated": escalated,
        }

    def _call_tool(
        self, name: str, arguments: Mapping[str, Any], retrieved: list[KBHit]
    ) -> tuple[str, bool]:
        """Run one tool. Returns its result as text, and whether it opened a hand-off.

        ``retrieved`` is extended in place with new search hits, so that source
        numbers stay the same across several searches in one answer.
        """
        tools = self._get_tools()
        if name == TOOL_SEARCH_KB:
            # Any section the model sends anyway is ignored: all sections are searched.
            hits = tools.search_kb(str(arguments.get("query") or ""))
            known = {hit.chunk_id for hit in retrieved}
            fresh = [hit for hit in hits if hit.chunk_id not in known]
            first_number = len(retrieved) + 1
            retrieved.extend(fresh)
            if not hits:
                return NO_ARTICLE_FOUND, False
            if not fresh:
                return "These sources were already returned above. Use them.", False
            return format_sources(fresh, first_number), False
        if name == TOOL_PLAN_DETAILS:
            needs_international = arguments.get("needs_international")
            plans = tools.get_plan_details(
                str(arguments.get("plan_name") or "") or None,
                _as_number(arguments.get("max_price")),
                needs_international if isinstance(needs_international, bool) else None,
            )
            if not plans:
                return NO_PLAN_FOUND, False
            return "\n".join(plan.model_dump_json(exclude_none=True) for plan in plans), False
        if name == TOOL_SUMMARIZE_CALL:
            summary = tools.summarize_call(str(arguments.get("transcript_id") or ""))
            return summary.model_dump_json(), False
        if name == TOOL_ESCALATE:
            requested = arguments.get("urgency")
            urgency: Urgency = "normal"
            if requested == "low":
                urgency = "low"
            elif requested == "high":
                urgency = "high"
            ticket = tools.escalate_to_human(
                str(arguments.get("reason") or "The agent asked for a hand-off."),
                str(arguments.get("category") or "other"),
                urgency,
            )
            return json.dumps(ticket.model_dump()), True
        raise ToolError(f"There is no tool called {name[:40]!r}")

    def _output_guard(self, state: CopilotState) -> dict[str, Any]:
        flags = list(state["flags"])
        from_model = state["route"] == "agent"
        draft = message_text(state["messages"][-1]) if from_model else state["draft"]
        if not draft.strip():
            draft = EMPTY_ANSWER
            flags.append(FLAG_EMPTY_ANSWER)
            from_model = False
        retrieved = state["retrieved"]
        sources = [*(hit.text for hit in retrieved), *state["sources"]]
        # A figure may also come from the conversation: the question, or an earlier turn.
        # The system prompt is left out, so its own numbers do not count as evidence.
        conversation = [
            message_text(message)
            for message in state["messages"][:-1]
            if message.type in {"human", "ai"}
        ]
        evidence = [*sources, *conversation]
        checked = check_output(
            draft,
            source_count=len(retrieved),
            redactor=self._get_redactor(),
            sources=sources,
            target_grade=self.settings.reading_grade_target,
            simplify=self._simplify if from_model else None,
            # A fixed reply (a hand-off, a refusal) is not the model's, so it is not checked.
            evidence=evidence if from_model else None,
        )
        searched = TOOL_SEARCH_KB in state["tools_used"]
        for flag in checked.flags:
            # "Nothing was cited" only means something when there were sources to cite.
            if flag == FLAG_NO_CITATION and not retrieved:
                continue
            flags.append(flag)
        if searched and not retrieved:
            flags.append(FLAG_NO_CONTEXT)
        return {
            "draft": checked.text,
            "cited": list(checked.cited),
            "flags": flags,
            "evidence": evidence,
        }

    def _simplify(self, text: str) -> str:
        with mlflow.start_span(name="simplify_answer", span_type=SpanType.CHAT_MODEL) as span:
            span.set_inputs({"answer": text})
            reply = self._get_model().invoke([SystemMessage(SIMPLIFY_PROMPT), HumanMessage(text)])
            rewritten = message_text(reply)
            span.set_outputs(rewritten)
        return rewritten


@lru_cache(maxsize=1)
def get_copilot() -> Copilot:
    """Return the process-wide copilot, built from the default settings."""
    return Copilot()


def run_copilot(question: str, history: Sequence[Mapping[str, str]] | None = None) -> CopilotAnswer:
    """Answer a support agent's question. The app, the evaluation and the tests call this."""
    return get_copilot().run(question, history)
