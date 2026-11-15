"""Streamlit interface for the Frontline Copilot.

Run locally:  streamlit run app/app.py
On Databricks Apps the command comes from app.yaml at the repository root.

This file only draws the page. Everything it shows comes from ``copilot.agent``
and ``copilot.tools``, the same code the evaluation and the MCP server call.
"""

from __future__ import annotations

import time
from typing import Any

import mlflow
import streamlit as st
from dotenv import load_dotenv
from mlflow.entities import AssessmentSource, AssessmentSourceType

from copilot.agent import Copilot
from copilot.config import Settings, load_settings
from copilot.prompts import PROMPT_VERSION
from copilot.schemas import CopilotAnswer
from copilot.tools import ToolError
from copilot.transcripts import get_transcript, list_transcripts

DISCLAIMER = (
    "Unofficial demo. Not affiliated with or endorsed by any carrier. "
    "Northline Wireless is fictional and all data is synthetic."
)
TOOL_LABELS = {
    "search_kb": "Help articles",
    "get_plan_details": "Plan catalogue",
    "summarize_call": "Call summary",
    "escalate_to_human": "Hand-off to a person",
}
EXAMPLES = (
    "How much is the late payment fee, and can it be waived?",
    "Which plans cost $25 a month or less?",
    "Summarize call T0002.",
    "Refund the $5 late fee on this customer's account.",
)
# Large type and strong contrast: the people this tool serves, and many of the
# people who would use it, read more easily that way.
STYLE = """
<style>
html, body, [data-testid="stAppViewContainer"] { font-size: 19px; }
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li { font-size: 1.1rem; line-height: 1.6; }
.stButton button { font-size: 1.05rem; padding: 0.5rem 1rem; }
.fc-note { color: #1f2933; background: #eef2f6; border-left: 5px solid #0b6e8f;
  padding: 0.5rem 0.8rem; border-radius: 4px; margin: 0.3rem 0; }
.fc-handoff { border-left-color: #a35a00; background: #fbeedb; }
</style>
"""


@st.cache_resource(show_spinner="Starting the copilot...")
def get_copilot() -> tuple[Copilot, Settings, bool]:
    """Build the copilot once per server process. Also says whether tracing is on."""
    load_dotenv()
    settings = load_settings()
    tracing = False
    if settings.mlflow_experiment:
        try:
            mlflow.set_tracking_uri("databricks")
            mlflow.set_experiment(settings.mlflow_experiment)
            tracing = True
        except Exception:
            # The app still answers without a tracking server; it only loses traces.
            mlflow.tracing.disable()
    else:
        mlflow.tracing.disable()
    return Copilot(settings), settings, tracing


def ask(copilot: Copilot, question: str, history: list[dict[str, str]]) -> dict[str, Any]:
    """Run one question and keep what the page shows about it."""
    started = time.perf_counter()
    answer = copilot.run(question, history, trace_tags={"source": "app"})
    return {
        "answer": answer,
        "seconds": time.perf_counter() - started,
        "trace_id": mlflow.get_last_active_trace_id(),
    }


def show_answer(result: dict[str, Any], tracing: bool, key: str) -> None:
    """Draw an answer with its sources, what was used, and the feedback buttons."""
    answer: CopilotAnswer = result["answer"]
    st.markdown(answer.answer)
    if answer.escalated:
        st.markdown(
            '<div class="fc-note fc-handoff">This needs a person. A hand-off was opened.</div>',
            unsafe_allow_html=True,
        )
    if any(flag.startswith("pii_in_question") for flag in answer.guardrail_flags):
        st.markdown(
            '<div class="fc-note">Personal details in your question were removed before it '
            "was processed or logged.</div>",
            unsafe_allow_html=True,
        )
    if answer.citations:
        with st.expander(f"Sources ({len(answer.citations)})"):
            for citation in answer.citations:
                st.markdown(f"**[{citation.number}]** [{citation.title}]({citation.url})")
    used = ", ".join(TOOL_LABELS.get(tool, tool) for tool in answer.tools_used) or "nothing"
    details = [f"Used: {used}", f"{result['seconds']:.1f} seconds"]
    if answer.guardrail_flags:
        details.append("Checks: " + ", ".join(answer.guardrail_flags))
    st.caption(" | ".join(details))
    if tracing and result.get("trace_id"):
        rating = st.feedback("thumbs", key=f"feedback-{key}")
        if rating is not None and not result.get("rated"):
            mlflow.log_feedback(
                trace_id=result["trace_id"],
                name="agent_feedback",
                value=bool(rating),
                source=AssessmentSource(
                    source_type=AssessmentSourceType.HUMAN, source_id="app-user"
                ),
            )
            result["rated"] = True
            st.caption("Thank you. Your rating was saved with this answer.")


def chat_tab(copilot: Copilot, tracing: bool) -> None:
    """The question-and-answer page."""
    if "turns" not in st.session_state:
        st.session_state.turns = []
    turns: list[dict[str, Any]] = st.session_state.turns
    if not turns:
        st.markdown("Ask a support question in plain words. For example:")
        for example in EXAMPLES:
            if st.button(example, key=f"example-{example}"):
                st.session_state.pending = example
                st.rerun()
    for index, turn in enumerate(turns):
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant"):
            show_answer(turn["result"], tracing, key=str(index))
    question = st.chat_input("Type the customer's question") or st.session_state.pop(
        "pending", None
    )
    if not question:
        return
    history = [
        message
        for turn in turns
        for message in (
            {"role": "user", "content": turn["question"]},
            {"role": "assistant", "content": turn["result"]["answer"].answer},
        )
    ]
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Looking it up..."):
        try:
            result = ask(copilot, question, history)
        except Exception as error:
            st.error(f"The copilot could not answer just now ({type(error).__name__}). Try again.")
            return
    turns.append({"question": question, "result": result})
    st.rerun()


def summary_tab(copilot: Copilot, settings: Settings) -> None:
    """Pick a call, see its summary next to the redacted transcript."""
    tools = copilot.tools
    try:
        listed = list_transcripts(tools.sql, settings)
    except Exception as error:
        st.error(f"The list of calls could not be loaded ({type(error).__name__}).")
        return
    labels = {
        row["transcript_id"]: f"{row['transcript_id']}  ({row['category']}, {row['resolution']})"
        for row in listed
    }
    chosen = st.selectbox("Call", list(labels), format_func=lambda item: labels[item])
    if not chosen or not st.button("Summarize this call"):
        return
    left, right = st.columns(2)
    with left:
        st.subheader("Summary")
        with st.spinner("Summarizing..."):
            try:
                summary = tools.summarize_call(chosen)
            except ToolError as error:
                st.error(str(error))
                return
        for bullet in summary.summary_bullets:
            st.markdown(f"- {bullet}")
        st.markdown(f"**What the customer wanted:** {summary.intent}")
        st.markdown(f"**Mood at the end:** {summary.sentiment}")
        st.markdown(f"**Next step:** {summary.next_step}")
        if summary.related_articles:
            st.markdown("**Related help articles**")
            for article in summary.related_articles:
                st.markdown(f"- [{article.title}]({article.url})")
    with right:
        st.subheader("Transcript, as stored")
        st.caption("Personal details were replaced with placeholders before this was saved.")
        for turn in get_transcript(tools.sql, settings, chosen):
            st.markdown(f"**{turn['speaker'].title()}:** {turn['text']}")


def sidebar(settings: Settings, tracing: bool) -> None:
    """What is running, in plain terms."""
    with st.sidebar:
        st.header("About this copilot")
        st.markdown(f"**Model:** `{settings.llm_endpoint}`")
        st.markdown(f"**Prompt version:** {PROMPT_VERSION}")
        st.markdown(
            f"**Search:** chunk setting {settings.chunk_config}, "
            f"{'hybrid' if settings.query_type == 'hybrid' else 'vector'} search, "
            f"top {settings.top_k}"
        )
        st.markdown(f"**Answers are traced:** {'yes' if tracing else 'no'}")
        st.divider()
        st.markdown(
            "It can search help articles, look up plans, summarize a call and hand a "
            "request to a person. It cannot see or change a customer account."
        )
        st.divider()
        st.caption(DISCLAIMER)


def main() -> None:
    """Draw the page."""
    st.set_page_config(page_title="Frontline Copilot", layout="wide")
    st.markdown(STYLE, unsafe_allow_html=True)
    st.title("Frontline Copilot")
    copilot, settings, tracing = get_copilot()
    sidebar(settings, tracing)
    ask_tab, calls_tab = st.tabs(["Ask a question", "Summarize a call"])
    with ask_tab:
        chat_tab(copilot, tracing)
    with calls_tab:
        summary_tab(copilot, settings)
    st.caption(DISCLAIMER)


main()
