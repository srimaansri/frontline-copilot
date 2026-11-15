"""Streamlit interface for the Frontline Copilot.

Run locally:  streamlit run app/app.py
On Databricks Apps the command comes from app.yaml at the repository root.

This file only draws the page. Everything it shows comes from ``copilot.agent``
and ``copilot.tools``, the same code the evaluation and the MCP server call.
Colours come from ``.streamlit/config.toml``.
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
COPILOT_AVATAR = ":material/smart_toy:"
AGENT_AVATAR = ":material/headset_mic:"
CUSTOMER_AVATAR = ":material/person:"

# Tool name -> (label, icon). Shown as a badge under each answer.
TOOLS: dict[str, tuple[str, str]] = {
    "search_kb": ("Help articles", ":material/menu_book:"),
    "get_plan_details": ("Plan catalogue", ":material/sell:"),
    "summarize_call": ("Call summary", ":material/call:"),
    "escalate_to_human": ("Hand-off to a person", ":material/support_agent:"),
}
# Guardrail flag -> (label, icon, colour). A flag may carry a detail after a colon.
CHECKS: dict[str, tuple[str, str, str]] = {
    "pii_in_question": ("Personal details removed", ":material/shield:", "green"),
    "pii_removed_from_answer": ("Kept out of the answer", ":material/shield:", "green"),
    "account_action_requested": ("Account request", ":material/lock:", "orange"),
    "injection_suspected": ("Blocked an override attempt", ":material/block:", "red"),
    "answer_simplified": ("Rewritten in plainer words", ":material/auto_fix_high:", "violet"),
    "invalid_citation_removed": ("A wrong citation was removed", ":material/link_off:", "orange"),
    "no_citation": ("No source cited", ":material/help:", "gray"),
    "no_context": ("Nothing found in the articles", ":material/search_off:", "gray"),
    "tool_error": ("A lookup failed", ":material/error:", "red"),
    "tool_limit_reached": ("Stopped after the lookup limit", ":material/timer_off:", "orange"),
    "empty_answer": ("No answer produced", ":material/error:", "red"),
}
# (question, icon, what it shows)
EXAMPLES: tuple[tuple[str, str, str], ...] = (
    (
        "How much is the late payment fee, and can it be waived?",
        ":material/menu_book:",
        "An answer from the help articles, with its source",
    ),
    (
        "Which plans cost $25 a month or less?",
        ":material/sell:",
        "A lookup in the plan catalogue",
    ),
    ("Summarize call T0002.", ":material/call:", "A summary of a redacted call"),
    (
        "Refund the $5 late fee on this customer's account.",
        ":material/support_agent:",
        "A request that needs a person",
    ),
)
MOODS = {
    "positive": ("Customer left satisfied", ":material/sentiment_satisfied:", "green"),
    "neutral": ("Customer left neutral", ":material/sentiment_neutral:", "gray"),
    "negative": ("Customer left unhappy", ":material/sentiment_dissatisfied:", "red"),
}
# Large type and strong contrast: the people this tool serves, and many of the
# people who would use it, read more easily that way.
STYLE = """
<style>
html, body, [data-testid="stAppViewContainer"] { font-size: 19px; }
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li { font-size: 1.1rem; line-height: 1.6; }
[data-testid="stChatMessage"] { border-radius: 14px; }
.stButton button { font-size: 1.02rem; padding: 0.7rem 1rem; border-radius: 12px;
  text-align: left; justify-content: flex-start; }
/* Example questions are full sentences: let them wrap and start at the left. */
[class*="st-key-example-"] button > div { justify-content: flex-start; width: 100%; }
[class*="st-key-example-"] .stMarkdownEllipsis,
[class*="st-key-example-"] .stMarkdownEllipsis p {
  white-space: normal; overflow: visible; text-overflow: clip; text-align: left; }
.fc-header { display: flex; align-items: center; gap: 16px; margin: 0 0 6px; }
.fc-mark { width: 60px; height: 60px; border-radius: 16px; background: #0b6e8f;
  display: grid; place-items: center; flex: none; }
.fc-title { font-size: 2.1rem; font-weight: 700; line-height: 1.15; color: #16202b; }
.fc-sub { font-size: 1.05rem; color: #4a5a68; }
.fc-pill { display: inline-block; font-size: 0.8rem; font-weight: 600; color: #0b6e8f;
  background: #e2f1f6; border-radius: 999px; padding: 2px 10px; margin-left: 10px;
  vertical-align: middle; }
.fc-hint { color: #4a5a68; font-size: 0.92rem; margin: -6px 0 10px 4px; }
</style>
"""
# A small robot face: the copilot's mark in the page header.
MARK = (
    '<svg width="38" height="38" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<line x1="12" y1="2.5" x2="12" y2="6" stroke="#fff" stroke-width="1.8" '
    'stroke-linecap="round"/>'
    '<circle cx="12" cy="2.5" r="1.4" fill="#fff"/>'
    '<rect x="4" y="6" width="16" height="13" rx="4" fill="#fff"/>'
    '<circle cx="9" cy="12" r="1.8" fill="#0b6e8f"/>'
    '<circle cx="15" cy="12" r="1.8" fill="#0b6e8f"/>'
    '<rect x="9" y="15.2" width="6" height="1.6" rx="0.8" fill="#0b6e8f"/>'
    '<rect x="1.5" y="10" width="2" height="5" rx="1" fill="#fff"/>'
    '<rect x="20.5" y="10" width="2" height="5" rx="1" fill="#fff"/></svg>'
)


@st.cache_resource(show_spinner="Starting the copilot...")
def get_copilot() -> tuple[Copilot, Settings, bool]:
    """Build the copilot once per server process. Also says whether tracing is on."""
    load_dotenv()
    settings = load_settings()
    tracing = False
    if settings.mlflow_experiment:
        try:
            mlflow.set_tracking_uri("databricks")
            # Locally this is a workspace path. On Databricks Apps the experiment is
            # an app resource and arrives as its numeric id.
            if settings.mlflow_experiment.isdigit():
                mlflow.set_experiment(experiment_id=settings.mlflow_experiment)
            else:
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


def show_badges(answer: CopilotAnswer, seconds: float) -> None:
    """One row of badges: what was used, what the guardrails did, and how long it took."""
    with st.container(horizontal=True, gap="small"):
        for tool in answer.tools_used:
            label, icon = TOOLS.get(tool, (tool, ":material/build:"))
            st.badge(label, icon=icon, color="blue")
        shown: set[str] = set()
        for flag in answer.guardrail_flags:
            name = flag.split(":", 1)[0]
            if name in shown:
                continue
            shown.add(name)
            label, icon, color = CHECKS.get(name, (name, ":material/flag:", "gray"))
            st.badge(label, icon=icon, color=color)  # type: ignore[arg-type]
        st.badge(f"{seconds:.1f} seconds", icon=":material/timer:", color="gray")


def show_answer(result: dict[str, Any], tracing: bool, key: str) -> None:
    """Draw an answer with its sources, what was used, and the feedback buttons."""
    answer: CopilotAnswer = result["answer"]
    st.markdown(answer.answer)
    if answer.escalated:
        st.warning("This needs a person. A hand-off was opened.", icon=":material/support_agent:")
    if any(flag.startswith("pii_in_question") for flag in answer.guardrail_flags):
        st.success(
            "Personal details in your question were removed before it was processed or logged.",
            icon=":material/shield:",
        )
    if answer.citations:
        with st.expander(f"Sources ({len(answer.citations)})", icon=":material/menu_book:"):
            for citation in answer.citations:
                st.markdown(f"**[{citation.number}]** [{citation.title}]({citation.url})")
    show_badges(answer, result["seconds"])
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


def show_examples() -> None:
    """Four starting points, one for each thing the copilot does."""
    st.markdown("#### Try one of these, or type your own question below")
    columns = st.columns(2, gap="medium")
    for index, (question, icon, hint) in enumerate(EXAMPLES):
        with columns[index % 2]:
            if st.button(question, key=f"example-{index}", icon=icon, width="stretch"):
                st.session_state.pending = question
                st.rerun()
            st.markdown(f'<div class="fc-hint">{hint}</div>', unsafe_allow_html=True)


def chat_tab(copilot: Copilot, tracing: bool) -> None:
    """The question-and-answer page."""
    if "turns" not in st.session_state:
        st.session_state.turns = []
    turns: list[dict[str, Any]] = st.session_state.turns
    if not turns:
        show_examples()
    for index, turn in enumerate(turns):
        with st.chat_message("user", avatar=AGENT_AVATAR):
            st.markdown(turn["question"])
        with st.chat_message("assistant", avatar=COPILOT_AVATAR):
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
    with st.chat_message("user", avatar=AGENT_AVATAR):
        st.markdown(question)
    with st.chat_message("assistant", avatar=COPILOT_AVATAR), st.spinner("Looking it up..."):
        try:
            result = ask(copilot, question, history)
        except Exception as error:
            st.error(
                f"The copilot could not answer just now ({type(error).__name__}). Try again.",
                icon=":material/error:",
            )
            return
    turns.append({"question": question, "result": result})
    st.rerun()


def summary_tab(copilot: Copilot, settings: Settings) -> None:
    """Pick a call, see its summary next to the redacted transcript."""
    tools = copilot.tools
    try:
        listed = list_transcripts(tools.sql, settings)
    except Exception as error:
        st.error(
            f"The list of calls could not be loaded ({type(error).__name__}).",
            icon=":material/error:",
        )
        return
    labels = {
        row["transcript_id"]: f"{row['transcript_id']}  ({row['category']}, {row['resolution']})"
        for row in listed
    }
    picker, action = st.columns([2, 1], vertical_alignment="bottom")
    with picker:
        chosen = st.selectbox("Call", list(labels), format_func=lambda item: labels[item])
    with action:
        pressed = st.button(
            "Summarize", icon=":material/summarize:", type="primary", width="stretch"
        )
    if not chosen or not pressed:
        st.info(
            "Pick a call and press Summarize. The summary appears next to the transcript "
            "as it is stored, with personal details already replaced.",
            icon=":material/info:",
        )
        return
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Summary", anchor=False)
        with st.spinner("Summarizing..."):
            try:
                summary = tools.summarize_call(chosen)
            except ToolError as error:
                st.error(str(error), icon=":material/error:")
                return
        with st.container(border=True):
            mood, mood_icon, mood_color = MOODS[summary.sentiment]
            with st.container(horizontal=True, gap="small"):
                st.badge(summary.intent, icon=":material/flag:", color="blue")
                st.badge(mood, icon=mood_icon, color=mood_color)  # type: ignore[arg-type]
            for bullet in summary.summary_bullets:
                st.markdown(f"- {bullet}")
            st.markdown(f"**Next step:** {summary.next_step}")
        if summary.related_articles:
            st.markdown("**Related help articles**")
            for article in summary.related_articles:
                st.markdown(f"- [{article.title}]({article.url})")
    with right:
        st.subheader("Transcript, as stored", anchor=False)
        st.caption(
            "Personal details were replaced with placeholders such as <PHONE_NUMBER_1> "
            "before this was saved."
        )
        with st.container(height=560, border=True):
            for turn in get_transcript(tools.sql, settings, chosen):
                is_agent = turn["speaker"].lower() == "agent"
                with st.chat_message(
                    "assistant" if is_agent else "user",
                    avatar=AGENT_AVATAR if is_agent else CUSTOMER_AVATAR,
                ):
                    st.markdown(turn["text"])


def sidebar(settings: Settings, tracing: bool) -> None:
    """What the copilot can do, and what is running."""
    with st.sidebar:
        st.subheader("What it can do", anchor=False)
        for label, icon in TOOLS.values():
            st.markdown(f"{icon} {label}")
        st.caption("It cannot see or change a customer account.")
        st.divider()
        st.subheader("What is running", anchor=False)
        st.markdown(f":material/memory: `{settings.llm_endpoint}`")
        st.markdown(f":material/description: Prompt {PROMPT_VERSION}")
        st.markdown(
            f":material/search: Setting {settings.chunk_config}, "
            f"{'hybrid' if settings.query_type == 'hybrid' else 'vector'} search, "
            f"top {settings.top_k}"
        )
        st.markdown(
            ":material/timeline: Answers are traced"
            if tracing
            else ":material/timeline: Tracing is off"
        )
        st.divider()
        if st.button("Start a new conversation", icon=":material/refresh:", width="stretch"):
            st.session_state.turns = []
            st.rerun()
        st.caption(DISCLAIMER)


def header() -> None:
    """The page title, with the copilot's mark."""
    st.markdown(
        f'<div class="fc-header"><div class="fc-mark">{MARK}</div><div>'
        '<div class="fc-title">Frontline Copilot'
        '<span class="fc-pill">Demo, synthetic data</span></div>'
        '<div class="fc-sub">Answers for Northline support agents, with sources. '
        "Plain words, ready to read out.</div></div></div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    """Draw the page."""
    st.set_page_config(
        page_title="Frontline Copilot", page_icon=":material/smart_toy:", layout="wide"
    )
    st.markdown(STYLE, unsafe_allow_html=True)
    header()
    copilot, settings, tracing = get_copilot()
    sidebar(settings, tracing)
    ask_tab, calls_tab = st.tabs(
        [":material/chat: Ask a question", ":material/call: Summarize a call"]
    )
    with ask_tab:
        chat_tab(copilot, tracing)
    with calls_tab:
        summary_tab(copilot, settings)


main()
