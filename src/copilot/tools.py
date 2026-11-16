"""The copilot's four tools, as plain typed methods on one object.

The agent, the MCP server and the tests all call these methods; the wrappers
that expose them to a model live with the agent. Every method takes text that
has already been redacted, and every SQL statement is parameterized: values
that come from a model are bound as parameters and never placed in SQL text.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, get_args

from pydantic import ValidationError

from copilot.config import Settings
from copilot.guardrails import redact_answer
from copilot.llm import ChatModel, build_chat_model, message_text
from copilot.prompts import SUMMARY_PROMPT
from copilot.redaction import Redactor, get_redactor
from copilot.retriever import Retriever
from copilot.schemas import (
    CallSummary,
    Citation,
    EscalationTicket,
    HandOffDraft,
    KBHit,
    Plan,
    Urgency,
)

logger = logging.getLogger(__name__)

TRANSCRIPT_ID_RE = re.compile(r"T\d{4}")
PLAN_COLUMNS: tuple[str, ...] = (
    "plan_id",
    "kind",
    "name",
    "monthly_price_usd",
    "billing_period",
    "data_gb",
    "talk_text",
    "hotspot_gb",
    "international",
    "notes",
)
MAX_PLAN_ROWS = 20
MAX_REASON_CHARS = 500

# Team that picks up each kind of hand-off. Anything else goes to "other".
ESCALATION_TEAMS: dict[str, str] = {
    "billing": "the billing team",
    "plan_change": "the account team",
    "account_access": "the account security team",
    "device": "the device support team",
    "cancellation": "the account team",
    "other": "a support specialist",
}

# A SQL parameter: its SQL type and its value as text. None is SQL NULL.
SqlParam = tuple[str, str | None]


class ToolError(ValueError):
    """A tool could not do what was asked. The message is safe to show to the agent."""


class SqlRunner(Protocol):
    """Runs one parameterized SQL statement and returns its rows."""

    def __call__(self, statement: str, parameters: Mapping[str, SqlParam]) -> list[dict[str, Any]]:
        """Return the result rows as dictionaries keyed by column name."""
        ...


def sdk_sql_runner(
    settings: Settings, *, sleep: Callable[[float], None] = time.sleep, max_polls: int = 30
) -> SqlRunner:
    """Build a ``SqlRunner`` on the Databricks SDK's statement execution API.

    Authentication is resolved by the SDK. A statement that is still running
    after the first wait (a warehouse that is starting, for example) is polled.
    """
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementParameterListItem

    if not settings.sql_warehouse_id:
        raise ToolError("SQL_WAREHOUSE_ID is not set, so the plan and transcript tools cannot run")
    warehouse_id = settings.sql_warehouse_id
    workspace = WorkspaceClient()

    def run(statement: str, parameters: Mapping[str, SqlParam]) -> list[dict[str, Any]]:
        response = workspace.statement_execution.execute_statement(
            statement=statement,
            warehouse_id=warehouse_id,
            parameters=[
                StatementParameterListItem(name=name, type=sql_type, value=value)
                for name, (sql_type, value) in parameters.items()
            ],
            wait_timeout="30s",
        )
        for _ in range(max_polls):
            if _state(response) not in {"PENDING", "RUNNING"}:
                break
            sleep(2.0)
            response = workspace.statement_execution.get_statement(response.statement_id or "")
        if _state(response) != "SUCCEEDED":
            raise ToolError(f"The data lookup did not finish (state {_state(response)})")
        schema = response.manifest.schema if response.manifest else None
        names = [column.name or "" for column in (schema.columns if schema else None) or []]
        data = response.result.data_array if response.result and response.result.data_array else []
        return [dict(zip(names, row, strict=True)) for row in data]

    return run


def _state(response: Any) -> str:
    state = response.status.state if response.status else None
    return str(getattr(state, "value", state))


def parse_json_object(text: str) -> dict[str, Any]:
    """Read the JSON object in a model reply, ignoring a code fence or stray words around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ToolError("The model did not return a JSON object")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise ToolError("The model returned JSON that could not be read") from error
    if not isinstance(value, dict):
        raise ToolError("The model did not return a JSON object")
    return value


def clean_plan_name(plan_name: str | None) -> str | None:
    """Drop filler words a model adds around a plan name, such as "the ... plan"."""
    if plan_name is None:
        return None
    name = re.sub(r"^\s*the\s+", "", plan_name.strip(), flags=re.IGNORECASE)
    name = re.sub(r"\s+plan\s*$", "", name, flags=re.IGNORECASE)
    return name or None


def new_ticket_id() -> str:
    """A short, unguessable reference for a hand-off."""
    return f"ESC-{uuid.uuid4().hex[:8].upper()}"


class Tools:
    """The four tools, bound to one configuration."""

    def __init__(
        self,
        settings: Settings,
        *,
        retriever: Retriever | None = None,
        sql: SqlRunner | None = None,
        llm: ChatModel | None = None,
        redactor: Redactor | None = None,
        ticket_id: Callable[[], str] = new_ticket_id,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Dependencies that are left out are built from ``settings`` on first use."""
        self.settings = settings
        self._retriever = retriever
        self._sql = sql
        self._llm = llm
        self._redactor = redactor
        self._ticket_id = ticket_id
        self._now = now

    # --- dependencies, built on first use ------------------------------------------------

    @property
    def retriever(self) -> Retriever:
        """The knowledge-base retriever."""
        if self._retriever is None:
            self._retriever = Retriever(self.settings)
        return self._retriever

    @property
    def sql(self) -> SqlRunner:
        """The SQL runner for the plan, transcript and escalation tables."""
        if self._sql is None:
            self._sql = sdk_sql_runner(self.settings)
        return self._sql

    @property
    def llm(self) -> ChatModel:
        """The chat model used to summarize a transcript."""
        if self._llm is None:
            self._llm = build_chat_model(self.settings)
        return self._llm

    @property
    def redactor(self) -> Redactor:
        """The redactor applied to free text before it is stored."""
        if self._redactor is None:
            self._redactor = get_redactor(product_names=tuple(self.settings.product_names))
        return self._redactor

    # --- the tools ------------------------------------------------------------------------

    def search_kb(self, query: str, section: str | None = None, top_k: int = 5) -> list[KBHit]:
        """Search the help articles. ``section`` narrows the search to one section.

        A model often guesses a section name that does not exist. If the
        narrowed search finds nothing, the search is repeated over all sections.
        """
        if not query.strip():
            raise ToolError("The search query is empty")
        top_k = max(1, min(top_k, 10))
        hits = self.retriever.search(query, top_k=top_k, section=section)
        if not hits and section:
            hits = self.retriever.search(query, top_k=top_k)
        return hits

    def get_plan_details(
        self,
        plan_name: str | None = None,
        max_price: float | None = None,
        needs_international: bool | None = None,
    ) -> list[Plan]:
        """Look up plans, add-ons and fees in the catalogue table.

        ``plan_name`` matches any catalogue row whose name contains it.
        ``max_price`` and ``needs_international`` apply to monthly plans only,
        because "plans under $25" should not return a $10 fee. With no
        arguments the whole catalogue is returned.
        """
        if max_price is not None and max_price < 0:
            raise ToolError("max_price cannot be negative")
        name = clean_plan_name(plan_name)
        table = self.settings.table("gold", "plans")
        # The table name comes from validated settings and the column list is a
        # constant. Everything a model supplies is a bound parameter.
        statement = (
            f"SELECT {', '.join(PLAN_COLUMNS)} FROM {table} "  # noqa: S608
            "WHERE (:plan_name IS NULL OR contains(lower(name), lower(:plan_name))) "
            "AND (:max_price IS NULL OR (kind = 'plan' AND billing_period = 'monthly' "
            "AND monthly_price_usd <= :max_price)) "
            "AND (:needs_international IS NULL OR (kind = 'plan' "
            "AND (international <> 'Not included') = :needs_international)) "
            f"ORDER BY monthly_price_usd, name LIMIT {MAX_PLAN_ROWS}"
        )
        rows = self.sql(
            statement,
            {
                "plan_name": ("STRING", name),
                "max_price": ("DOUBLE", None if max_price is None else str(float(max_price))),
                "needs_international": (
                    "BOOLEAN",
                    None if needs_international is None else str(needs_international).lower(),
                ),
            },
        )
        return [Plan.model_validate(row) for row in rows]

    def summarize_call(self, transcript_id: str) -> CallSummary:
        """Summarize one transcript. Reads the redacted transcript table only."""
        transcript_id = transcript_id.strip().upper()
        if not TRANSCRIPT_ID_RE.fullmatch(transcript_id):
            raise ToolError(
                f"{transcript_id[:20]!r} is not a valid transcript id. "
                "An id is the letter T and four digits, such as T0007."
            )
        table = self.settings.table("silver", "transcripts_redacted")
        rows = self.sql(
            "SELECT transcript_id, category, resolution, to_json(turns) AS turns_json "  # noqa: S608
            f"FROM {table} WHERE transcript_id = :transcript_id LIMIT 1",
            {"transcript_id": ("STRING", transcript_id)},
        )
        if not rows:
            raise ToolError(f"No transcript was found with the id {transcript_id}")
        row = rows[0]
        turns = json.loads(row["turns_json"])
        conversation = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in turns)
        reply = self.llm.invoke(
            [
                ("system", SUMMARY_PROMPT),
                (
                    "user",
                    f'<transcript id="{transcript_id}" topic="{row.get("category")}" '
                    f'recorded_outcome="{row.get("resolution")}">\n{conversation}\n</transcript>',
                ),
            ]
        )
        fields = parse_json_object(message_text(reply))

        def checked(value: object) -> str:
            # The transcript is redacted, but the model may still write out something
            # that looks like personal data. Whatever is not in the transcript is replaced,
            # so this path gets the same output check as an answer from the agent.
            return redact_answer(str(value or "").strip(), self.redactor, [conversation]).text

        try:
            summary = CallSummary(
                transcript_id=transcript_id,
                summary_bullets=[checked(bullet) for bullet in fields.get("summary_bullets") or []],
                intent=checked(fields.get("intent")),
                sentiment=fields.get("sentiment"),
                next_step=checked(fields.get("next_step")),
            )
        except ValidationError as error:
            raise ToolError("The model's summary did not have the expected fields") from error
        return summary.model_copy(update={"related_articles": self._related(summary.intent)})

    def _related(self, intent: str) -> list[Citation]:
        """Up to three help articles about what the customer wanted, one per article."""
        if not intent:
            return []
        seen: dict[str, str] = {}
        for hit in self.retriever.search(intent, top_k=5):
            seen.setdefault(hit.url, hit.title)
        return [
            Citation(number=number, title=title, url=url)
            for number, (url, title) in enumerate(list(seen.items())[:3], start=1)
        ]

    def draft_hand_off(
        self, reason: str, category: str = "other", urgency: Urgency = "normal"
    ) -> HandOffDraft:
        """Prepare a hand-off without writing anything.

        The category is brought to a known one, and ``reason``, which a model or
        an agent wrote, is cut to length and redacted. The result is what the
        agent is shown to approve, and what ``escalate_to_human`` writes.
        """
        if urgency not in get_args(Urgency):
            raise ToolError("urgency must be low, normal or high")
        category = category.strip().lower().replace(" ", "_").replace("-", "_")
        if category not in ESCALATION_TEAMS:
            category = "other"
        safe_reason = self.redactor.redact(reason.strip()[:MAX_REASON_CHARS]).text
        return HandOffDraft(
            category=category,
            urgency=urgency,
            reason=safe_reason,
            team=ESCALATION_TEAMS[category],
        )

    def escalate_to_human(
        self, reason: str, category: str = "other", urgency: Urgency = "normal"
    ) -> EscalationTicket:
        """Open a hand-off to a human specialist and return what the agent should say.

        ``reason`` is free text written by a model, so it is redacted before it
        is stored or returned. If the ticket cannot be written, a ticket is
        still returned with ``recorded`` false, so the agent is never left
        without a next step.

        With ``record_escalations`` off (an evaluation run), nothing is written
        and ``recorded`` is false, but the script is the one a written ticket
        gets, so the answer that is evaluated is the answer an agent would see.
        """
        draft = self.draft_hand_off(reason, category, urgency)
        category, safe_reason = draft.category, draft.reason
        ticket_id = self._ticket_id()
        table = self.settings.table("ops", "escalations")
        dry_run = not self.settings.record_escalations
        recorded = False
        if not dry_run:
            try:
                self.sql(
                    f"INSERT INTO {table} "  # noqa: S608
                    "(ticket_id, created_at, category, urgency, reason, status) "
                    "VALUES (:ticket_id, :created_at, :category, :urgency, :reason, 'open')",
                    {
                        "ticket_id": ("STRING", ticket_id),
                        "created_at": ("TIMESTAMP", self._now().strftime("%Y-%m-%d %H:%M:%S")),
                        "category": ("STRING", category),
                        "urgency": ("STRING", urgency),
                        "reason": ("STRING", safe_reason),
                    },
                )
                recorded = True
            except Exception as error:
                # A failed write must not lose the hand-off: the agent still gets a script.
                # Only the kind of error is logged; its message can quote the statement.
                logger.warning("A hand-off ticket could not be written (%s)", type(error).__name__)
        team = ESCALATION_TEAMS[category]
        if recorded or dry_run:
            script = (
                f"I can't do this myself, so I'm passing you to {team}. "
                f"Your reference is {ticket_id}. They will take it from here."
            )
        else:
            script = (
                f"I could not open a ticket just now. Please transfer the customer to {team} "
                f"by hand and give them the reference {ticket_id}."
            )
        return EscalationTicket(
            ticket_id=ticket_id,
            category=category,
            urgency=urgency,
            reason=safe_reason,
            agent_script=script,
            recorded=recorded,
        )
