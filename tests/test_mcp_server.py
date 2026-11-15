"""The MCP server, with fake tools. No network and no transport: tools are called in process."""

import asyncio
import json
import types
from typing import Any

import pytest

import mcp_server.server as server_module
from copilot.config import Settings
from copilot.schemas import CallSummary, EscalationTicket, KBHit, Plan
from copilot.tools import ToolError
from mcp_server.server import build_server, main

PHONE = "480-555-0132"


class FakeRedactor:
    def redact(self, text: str) -> Any:
        return types.SimpleNamespace(text=text.replace(PHONE, "<PHONE_NUMBER_1>"))


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def search_kb(self, query: str, section: str | None = None, top_k: int = 5) -> list[KBHit]:
        self.calls.append(("search_kb", (query, section, top_k)))
        return [
            KBHit(
                chunk_id="c1",
                url="https://help.northline.example/articles/late-payment-fee",
                title="Late payment fee",
                text="The fee is $5.",
                score=0.8,
            )
        ]

    def get_plan_details(
        self, plan_name: str | None, max_price: float | None, needs_international: bool | None
    ) -> list[Plan]:
        self.calls.append(("get_plan_details", (plan_name, max_price, needs_international)))
        return [
            Plan(
                plan_id="P03",
                kind="plan",
                name="Northline Everyday 5",
                monthly_price_usd=25.0,
                billing_period="monthly",
            )
        ]

    def summarize_call(self, transcript_id: str) -> CallSummary:
        self.calls.append(("summarize_call", (transcript_id,)))
        if transcript_id != "T0002":
            raise ToolError(f"{transcript_id!r} is not a valid transcript id.")
        return CallSummary(
            transcript_id="T0002",
            summary_bullets=["The phone showed no service."],
            intent="fix no service",
            sentiment="positive",
            next_step="None, the issue was resolved.",
        )

    def escalate_to_human(self, reason: str, category: str, urgency: str) -> EscalationTicket:
        self.calls.append(("escalate_to_human", (reason, category, urgency)))
        return EscalationTicket(
            ticket_id="ESC-TEST0001",
            category=category,
            urgency=urgency,  # type: ignore[arg-type]
            reason=reason,
            agent_script="Passing you to the billing team.",
            recorded=True,
        )


@pytest.fixture
def fake_tools() -> FakeTools:
    return FakeTools()


def make_server(fake_tools: FakeTools) -> Any:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    return build_server(settings, tools=fake_tools, redactor=FakeRedactor())  # type: ignore[arg-type]


def call(server: Any, name: str, arguments: dict[str, Any]) -> str:
    """Call a tool in process and return everything it sent back, as text."""
    return json.dumps(asyncio.run(server.call_tool(name, arguments)), default=str)


def test_the_server_offers_the_four_tools_with_descriptions(fake_tools: FakeTools) -> None:
    listed = asyncio.run(make_server(fake_tools).list_tools())

    assert [tool.name for tool in listed] == [
        "search_kb",
        "get_plan_details",
        "summarize_call",
        "escalate_to_human",
    ]
    assert all(tool.description for tool in listed)
    search = listed[0]
    assert search.inputSchema["required"] == ["query"]
    assert "section" not in search.inputSchema["properties"]


def test_search_redacts_the_query_before_it_reaches_the_index(fake_tools: FakeTools) -> None:
    result = call(make_server(fake_tools), "search_kb", {"query": f"late fee for {PHONE}"})

    assert fake_tools.calls == [("search_kb", ("late fee for <PHONE_NUMBER_1>", None, 5))]
    assert "Late payment fee" in result
    assert "late-payment-fee" in result
    # Internal ids are not part of what another assistant needs.
    assert "chunk_id" not in result


def test_plan_lookup_treats_empty_defaults_as_no_filter(fake_tools: FakeTools) -> None:
    server = make_server(fake_tools)

    everything = call(server, "get_plan_details", {})
    call(
        server,
        "get_plan_details",
        {"plan_name": "Plus", "max_price": 40, "needs_international": True},
    )

    assert fake_tools.calls == [
        ("get_plan_details", (None, None, None)),
        ("get_plan_details", ("Plus", 40.0, True)),
    ]
    assert "Northline Everyday 5" in everything


def test_call_summary_returns_the_structured_summary(fake_tools: FakeTools) -> None:
    result = call(make_server(fake_tools), "summarize_call", {"transcript_id": "T0002"})

    assert "fix no service" in result
    assert "positive" in result


def test_a_tool_error_reaches_the_caller_as_an_error(fake_tools: FakeTools) -> None:
    with pytest.raises(Exception, match="not a valid transcript id"):
        call(make_server(fake_tools), "summarize_call", {"transcript_id": "T12"})


def test_escalation_passes_its_arguments_through(fake_tools: FakeTools) -> None:
    result = call(
        make_server(fake_tools),
        "escalate_to_human",
        {"reason": "Wants a refund", "category": "billing", "urgency": "high"},
    )

    assert fake_tools.calls == [("escalate_to_human", ("Wants a refund", "billing", "high"))]
    assert "ESC-TEST0001" in result


def test_tools_and_redactor_are_built_on_first_use(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []
    fake = FakeTools()

    def fake_get_redactor(**_: Any) -> FakeRedactor:
        built.append("redactor")
        return FakeRedactor()

    def fake_tools_class(settings: Settings, **_: Any) -> FakeTools:
        built.append("tools")
        return fake

    monkeypatch.setattr(server_module, "get_redactor", fake_get_redactor)
    monkeypatch.setattr(server_module, "Tools", fake_tools_class)
    monkeypatch.setattr(server_module, "get_settings", lambda: Settings(_env_file=None))  # type: ignore[call-arg]
    server = build_server()

    assert built == []
    call(server, "search_kb", {"query": "late fee"})
    call(server, "search_kb", {"query": "autopay"})

    assert sorted(built) == ["redactor", "tools"]
    assert len(fake.calls) == 2


def test_main_runs_the_chosen_transport_without_local_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: dict[str, Any] = {}

    class FakeServer:
        def run(self, transport: str) -> None:
            ran["transport"] = transport

    def fake_build(**kwargs: Any) -> FakeServer:
        ran.update(kwargs)
        return FakeServer()

    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    # main() loads the developer's .env. A test must not: it would change the settings
    # every later test sees.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(server_module, "build_server", fake_build)
    detached: list[bool] = []
    monkeypatch.setattr(
        server_module, "keep_stdin_for_the_transport", lambda: detached.append(True)
    )
    disabled: list[bool] = []
    monkeypatch.setattr("mlflow.tracing.disable", lambda: disabled.append(True))

    main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000"])  # noqa: S104

    assert ran == {"host": "0.0.0.0", "port": 9000, "transport": "streamable-http"}  # noqa: S104
    assert disabled == [True]
    # Only stdio uses standard input as its channel.
    assert detached == []

    main(["--transport", "stdio"])

    assert ran["transport"] == "stdio"
    assert detached == [True]


def test_the_stdio_transport_gets_its_own_copy_of_standard_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Programs the server starts, such as the Databricks CLI, must not read the MCP channel."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr("os.dup", lambda fd: calls.append(("dup", fd)) or 7)
    monkeypatch.setattr("os.open", lambda path, flags: calls.append(("open", path)) or 8)
    monkeypatch.setattr("os.dup2", lambda src, dst: calls.append(("dup2", src, dst)))
    monkeypatch.setattr("os.close", lambda fd: calls.append(("close", fd)))
    monkeypatch.setattr("os.fdopen", lambda fd, *args, **kwargs: f"stream-on-{fd}")
    monkeypatch.setattr("sys.stdin", None)

    server_module.keep_stdin_for_the_transport()

    assert calls == [("dup", 0), ("open", server_module.os.devnull), ("dup2", 8, 0), ("close", 8)]
    assert server_module.sys.stdin == "stream-on-7"
