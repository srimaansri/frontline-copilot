"""The chat model, and how to read its replies."""

from __future__ import annotations

from typing import Any, Protocol

from copilot.config import Settings


class ChatModel(Protocol):
    """The two methods of a LangChain chat model that the copilot uses."""

    def invoke(self, messages: Any) -> Any:
        """Send messages and return the model's reply message.

        Messages are ``(role, text)`` pairs or LangChain message objects.
        """
        ...

    def bind_tools(self, tools: Any) -> Any:
        """Return a model that may answer with a call to one of ``tools``."""
        ...


def build_chat_model(settings: Settings) -> ChatModel:
    """Create the chat model for the configured serving endpoint.

    Authentication is resolved by the Databricks SDK, so this works with a CLI
    profile on a laptop and with the app's service principal on Databricks.
    """
    from databricks_langchain import ChatDatabricks

    model: ChatModel = ChatDatabricks(
        endpoint=settings.llm_endpoint,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    return model


def message_text(message: Any) -> str:
    """Return the answer text of a chat reply, leaving out any reasoning.

    Most replies carry plain text. Some open-weight models return a list of
    blocks in which reasoning is kept apart from the answer; only blocks of type
    ``text`` are the answer.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts).strip()
    return ""
