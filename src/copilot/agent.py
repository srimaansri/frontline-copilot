"""The copilot's entry point: ``run_copilot``.

At this milestone the copilot is a plain retrieve-then-answer chain. The
signature and ``CopilotAnswer`` stay the same when the body becomes a tool-using
agent, so the app and the evaluation do not change.

Order of work, and why:

1. Redact the question. This happens *outside* any MLflow span, because a span
   records its inputs as soon as it opens.
2. Open the trace with the redacted question only.
3. Retrieve, ask the model, and validate the citations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache

import mlflow
from mlflow.entities import SpanType

from copilot.config import Settings, get_settings
from copilot.guardrails import check_citations, redact_question
from copilot.llm import ChatModel, build_chat_model, message_text
from copilot.prompts import NO_CONTEXT_ANSWER, PROMPT_VERSION, SYSTEM_PROMPT, build_user_message
from copilot.redaction import Redactor, get_redactor
from copilot.retriever import Retriever
from copilot.schemas import Citation, CopilotAnswer, KBHit

FLAG_NO_CONTEXT = "no_context"
TOOL_SEARCH_KB = "search_kb"


class Copilot:
    """Answers knowledge-base questions with citations."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        retriever: Retriever | None = None,
        chat_model: ChatModel | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        """Build a copilot. Parts that are not passed in are created on first use."""
        self.settings = settings or get_settings()
        self._retriever = retriever or Retriever(self.settings)
        self._chat_model = chat_model
        self._redactor = redactor

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
            The answer, its citations and any guardrail flags.
        """
        if self._redactor is None:
            self._redactor = get_redactor(product_names=tuple(self.settings.product_names))
        redacted = redact_question(question, self._redactor)
        safe_history = [
            (turn["role"], self._redactor.redact(turn["content"]).text) for turn in history or []
        ]
        # Nothing above this line is traced. Only redacted text goes below it.
        return self._answer(redacted.text, safe_history, list(redacted.flags), trace_tags or {})

    def _answer(
        self,
        question: str,
        history: list[tuple[str, str]],
        flags: list[str],
        trace_tags: Mapping[str, str],
    ) -> CopilotAnswer:
        settings = self.settings
        with mlflow.start_span(name="run_copilot", span_type=SpanType.CHAIN) as root:
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
            hits = self._retriever.search(question)
            if hits:
                raw = self._generate(question, history, hits)
                checked = check_citations(raw, len(hits))
                text = checked.text
                cited = checked.cited
                flags = [*flags, *checked.flags]
            else:
                text, cited = NO_CONTEXT_ANSWER, ()
                flags = [*flags, FLAG_NO_CONTEXT]
            answer = CopilotAnswer(
                answer=text,
                citations=[
                    Citation(number=number, title=hits[number - 1].title, url=hits[number - 1].url)
                    for number in cited
                ],
                tools_used=[TOOL_SEARCH_KB],
                escalated=False,
                guardrail_flags=flags,
            )
            root.set_outputs(answer.model_dump())
        return answer

    def _generate(self, question: str, history: list[tuple[str, str]], hits: list[KBHit]) -> str:
        if self._chat_model is None:
            self._chat_model = build_chat_model(self.settings)
        messages = [
            ("system", SYSTEM_PROMPT),
            *history,
            ("user", build_user_message(question, hits)),
        ]
        with mlflow.start_span(name="generate_answer", span_type=SpanType.CHAT_MODEL) as span:
            span.set_inputs({"messages": [{"role": r, "content": c} for r, c in messages]})
            text = message_text(self._chat_model.invoke(messages))
            span.set_outputs(text)
        return text


@lru_cache(maxsize=1)
def get_copilot() -> Copilot:
    """Return the process-wide copilot, built from the default settings."""
    return Copilot()


def run_copilot(question: str, history: Sequence[Mapping[str, str]] | None = None) -> CopilotAnswer:
    """Answer a support agent's question. The app, the evaluation and the tests call this."""
    return get_copilot().run(question, history)
