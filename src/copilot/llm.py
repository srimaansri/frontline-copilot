"""The chat model, and how to read its replies."""

from __future__ import annotations

import json
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
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    return model


def build_router_model(settings: Settings) -> ChatModel:
    """Create the small model that routes a request.

    It gets a short timeout and one retry: routing must not hold an answer up,
    and the rules are there to decide if it fails.
    """
    from databricks_langchain import ChatDatabricks

    model: ChatModel = ChatDatabricks(
        endpoint=settings.router_endpoint,
        temperature=0.0,
        # Room for a reasoning model to think before its one line of JSON.
        max_tokens=600,
        timeout=settings.router_timeout_seconds,
        max_retries=1,
    )
    return model


def _blocks_in_a_string(content: str) -> list[Any] | None:
    """Read a reply that arrives as one string holding a JSON list of blocks.

    A reasoning-only preview model (Qwen3.5 122B) is returned this way: its
    reasoning and its answer in one serialized list. Anything else, including
    an answer that merely starts with a bracket, is left alone.
    """
    stripped = content.strip()
    if not (stripped.startswith('[{"type"') and stripped.endswith("]")):
        return None
    try:
        blocks = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(blocks, list) and all(isinstance(block, dict) for block in blocks):
        return blocks
    return None


def message_text(message: Any) -> str:
    """Return the answer text of a chat reply, leaving out any reasoning.

    Most replies carry plain text. Some open-weight models return a list of
    blocks in which reasoning is kept apart from the answer; only blocks of type
    ``text`` are the answer.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        blocks = _blocks_in_a_string(content)
        if blocks is None:
            return content.strip()
        content = blocks
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts).strip()
    return ""
