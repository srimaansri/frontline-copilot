"""MCP server for the copilot's tools.

Usage:
    python -m mcp_server.server                        # stdio, for Claude Code or Claude Desktop
    python -m mcp_server.server --transport streamable-http --host 0.0.0.0 --port 8000

The server exposes the same four functions the copilot's own agent calls, from
``copilot.tools``. Free text that arrives from another assistant is redacted
before it is used, because it reaches a search index and, for a hand-off, a
table. Configuration comes from the environment and ``config/settings.yaml``,
as everywhere else in the project.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from copilot.config import Settings, get_settings
from copilot.redaction import Redactor, get_redactor
from copilot.tools import Tools

INSTRUCTIONS = (
    "Tools for frontline support at Northline Wireless, a fictional carrier. All data is "
    "synthetic. search_kb finds help articles, get_plan_details reads the plan catalogue, "
    "summarize_call summarizes one redacted support call, and escalate_to_human opens a "
    "hand-off to a human specialist. None of these can see or change a customer account."
)


def build_server(
    settings: Settings | None = None,
    *,
    tools: Tools | None = None,
    redactor: Redactor | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Create the server. ``tools`` and ``redactor`` are built on first use if left out."""
    settings = settings or get_settings()
    parts: dict[str, Any] = {"tools": tools, "redactor": redactor}

    def the_redactor() -> Redactor:
        if parts["redactor"] is None:
            parts["redactor"] = get_redactor(product_names=tuple(settings.product_names))
        redactor_now: Redactor = parts["redactor"]
        return redactor_now

    def the_tools() -> Tools:
        if parts["tools"] is None:
            parts["tools"] = Tools(settings, redactor=the_redactor())
        tools_now: Tools = parts["tools"]
        return tools_now

    def safe(text: str) -> str:
        return the_redactor().redact(text).text

    server = FastMCP("frontline-copilot", instructions=INSTRUCTIONS, host=host, port=port)

    @server.tool()
    def search_kb(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search Northline's help articles.

        Returns the best-matching passages with their article title and URL. Use it
        for how something works, steps, policies and fees.
        """
        hits = the_tools().search_kb(safe(query), top_k=top_k)
        return [
            hit.model_dump(include={"title", "url", "heading", "text", "score"}) for hit in hits
        ]

    @server.tool()
    def get_plan_details(
        plan_name: str = "", max_price: float = 0.0, needs_international: bool = False
    ) -> list[dict[str, Any]]:
        """Look up plans, add-ons and fees in the plan catalogue.

        plan_name matches any row whose name contains it. max_price above zero keeps
        monthly plans at or under that price. needs_international keeps plans with
        international features. With no arguments the whole catalogue is returned.
        """
        plans = the_tools().get_plan_details(
            plan_name or None,
            max_price if max_price > 0 else None,
            True if needs_international else None,
        )
        return [plan.model_dump(exclude_none=True) for plan in plans]

    @server.tool()
    def summarize_call(transcript_id: str) -> dict[str, Any]:
        """Summarize one support call from its transcript id, such as T0007.

        Reads the redacted transcript only. Personal details appear as placeholders.
        """
        return the_tools().summarize_call(transcript_id).model_dump()

    @server.tool()
    def escalate_to_human(
        reason: str,
        category: str = "other",
        urgency: Literal["low", "normal", "high"] = "normal",
    ) -> dict[str, Any]:
        """Open a hand-off to a human specialist.

        Use it for a request to change, cancel, refund or look up something on one
        customer's account. category is one of billing, plan_change, account_access,
        device, cancellation, other. The reason is redacted before it is stored.
        """
        return the_tools().escalate_to_human(reason, category, urgency).model_dump()

    return server


def keep_stdin_for_the_transport() -> None:
    """Give the stdio transport its own copy of standard input.

    Programs this process starts are left with an empty one. Over stdio, standard
    input is the MCP channel. The Databricks SDK signs in by running the Databricks
    CLI, and a program started that way inherits standard input. With the channel
    as its input, the CLI blocks, and so does the first tool call that needs to
    sign in.
    """
    transport = os.dup(0)
    empty = os.open(os.devnull, os.O_RDONLY)
    os.dup2(empty, 0)
    os.close(empty)
    sys.stdin = os.fdopen(transport, "r", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="MCP server for the Frontline Copilot tools.")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    # Puts DATABRICKS_HOST and DATABRICKS_CONFIG_PROFILE where the SDK looks.
    load_dotenv()
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        import mlflow

        # The tools open MLflow spans. Without a tracking server configured they would
        # be written to a local file next to wherever the server was started.
        mlflow.tracing.disable()
    if args.transport == "stdio":
        keep_stdin_for_the_transport()
    build_server(host=args.host, port=args.port).run(transport=args.transport)


if __name__ == "__main__":
    main()
