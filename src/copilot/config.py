"""Typed application settings.

Values are merged from four places. The first one that provides a value wins:

1. environment variables (``CATALOG``, ``TOP_K``, ...; names are case-insensitive)
2. the ``.env`` file at the repo root
3. ``config/settings.yaml``
4. the field defaults in :class:`Settings`

No credential is read here. Code that talks to Databricks builds a
``WorkspaceClient()`` and lets the SDK resolve authentication, so the same code
runs locally (CLI profile or token) and as a Databricks App (service principal).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML_FILE = REPO_ROOT / "config" / "settings.yaml"
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

QueryType = Literal["ann", "hybrid"]

_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_IDENTIFIER_RE = re.compile(_IDENTIFIER_PATTERN)


class ChunkingConfig(BaseModel):
    """Size of one chunking variant, in approximate tokens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_size_tokens: int = Field(gt=0)
    overlap_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> Self:
        if self.overlap_tokens >= self.chunk_size_tokens:
            msg = (
                f"overlap_tokens ({self.overlap_tokens}) must be smaller than "
                f"chunk_size_tokens ({self.chunk_size_tokens})"
            )
            raise ValueError(msg)
        return self


def _default_chunking() -> dict[str, ChunkingConfig]:
    return {
        "A": ChunkingConfig(chunk_size_tokens=800, overlap_tokens=100),
        "B": ChunkingConfig(chunk_size_tokens=350, overlap_tokens=60),
    }


class Settings(BaseSettings):
    """All non-secret configuration for the copilot, pipelines and eval."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        yaml_file=DEFAULT_YAML_FILE,
        # `.env` also holds values meant for the Databricks SDK
        # (DATABRICKS_TOKEN); they are not settings and must not fail validation.
        extra="ignore",
        # A blank line such as `SQL_WAREHOUSE_ID=` means "not set".
        env_ignore_empty=True,
        frozen=True,
    )

    # Workspace
    databricks_host: str | None = None
    # Table names are built from this, so it must be a plain identifier.
    catalog: str = Field(default="frontline", pattern=_IDENTIFIER_PATTERN)
    sql_warehouse_id: str | None = None
    mlflow_experiment: str | None = None

    # Model serving endpoints
    llm_endpoint: str = "databricks-gpt-oss-120b"
    judge_endpoint: str = "databricks-meta-llama-3-3-70b-instruct"
    embedding_endpoint: str = "databricks-gte-large-en"
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=700, gt=0)
    # One model call may take this long, and is tried again this many times, before
    # the request fails. Without them a stalled endpoint holds a request open.
    llm_timeout_seconds: float = Field(default=60.0, gt=0.0)
    llm_max_retries: int = Field(default=2, ge=0)

    # Retrieval
    vs_endpoint: str = "frontline-vs"
    vs_index: str | None = Field(
        default=None,
        description="Full index name. Leave unset to derive it from the catalog; "
        "read it through `index_name`.",
    )
    top_k: int = Field(default=5, ge=1, le=50)
    query_type: QueryType = "ann"
    min_retrieval_score: float = Field(default=0.0, ge=0.0)

    # Chunking
    chunk_config: str = "A"
    chunking: dict[str, ChunkingConfig] = Field(default_factory=_default_chunking)

    # Redaction
    product_names: list[str] = Field(
        default_factory=list,
        description="Plan and add-on names. The redactor never treats these as a person.",
    )

    # Behaviour
    reading_grade_target: float = Field(default=8.0, gt=0.0)
    max_tool_iterations: int = Field(default=4, ge=1)
    # How a request is routed before the main model sees it. "rules" uses the plain
    # rules alone, at no cost. "model" keeps the rules for a clear account request,
    # gives everything else to a small model that reads the routing policy, and
    # falls back to the rules if that model cannot be reached or read. The default
    # is the one that scored best on the held-out routing set (eval/routing_eval.py).
    router: Literal["rules", "model"] = "model"
    router_endpoint: str = "databricks-llama-4-maverick"
    # A router that has not answered by now is given up on, and the rules decide.
    router_timeout_seconds: float = Field(default=8.0, gt=0.0)
    # True: the copilot drafts a hand-off and the agent approves it before anything is
    # written. False: the copilot writes the ticket itself, as it did at first.
    handoff_needs_approval: bool = True
    # False makes a hand-off a dry run: the ticket and the script are produced, and
    # nothing is written to the escalations table. Evaluation runs use it.
    record_escalations: bool = True
    # False makes saving an after-call wrap-up a dry run: the wrap-up is checked and
    # redacted as usual, and nothing is written to the wrap-ups table.
    record_wrapups: bool = True

    @field_validator("query_type", mode="before")
    @classmethod
    def _lowercase_query_type(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _chunk_config_is_defined(self) -> Self:
        if self.chunk_config not in self.chunking:
            known = ", ".join(sorted(self.chunking))
            msg = f"chunk_config {self.chunk_config!r} is not defined in chunking (have: {known})"
            raise ValueError(msg)
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Order the sources: arguments, environment, ``.env``, then YAML."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    @property
    def index_name(self) -> str:
        """Full name of the AI Search index."""
        return self.vs_index or self.table("gold", "kb_chunks_index")

    @property
    def active_chunking(self) -> ChunkingConfig:
        """The chunking variant selected by ``chunk_config``."""
        return self.chunking[self.chunk_config]

    def table(self, schema: str, name: str) -> str:
        """Return the three-part Unity Catalog name ``catalog.schema.name``.

        Raises:
            ValueError: If ``schema`` or ``name`` is not a plain identifier. The
                result is placed in SQL text, so nothing else is accepted.
        """
        for part in (schema, name):
            if not _IDENTIFIER_RE.fullmatch(part):
                msg = f"not a valid identifier: {part!r}"
                raise ValueError(msg)
        return f"{self.catalog}.{schema}.{name}"

    def volume_path(self, schema: str, volume: str) -> str:
        """Return the filesystem path of a Unity Catalog volume."""
        return "/Volumes/" + self.table(schema, volume).replace(".", "/")


def load_settings(*, yaml_file: Path | None = None, env_file: Path | None = None) -> Settings:
    """Build settings, optionally reading the YAML or ``.env`` file from another path.

    Args:
        yaml_file: Replacement for ``config/settings.yaml``. A missing file is not an error.
        env_file: Replacement for the repo-root ``.env``. A missing file is not an error.

    Returns:
        A validated, immutable ``Settings`` instance.
    """
    if yaml_file is None and env_file is None:
        return Settings()

    class _RelocatedSettings(Settings):
        model_config = SettingsConfigDict(
            yaml_file=yaml_file or DEFAULT_YAML_FILE,
            env_file=env_file or DEFAULT_ENV_FILE,
        )

    return _RelocatedSettings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once from the default files."""
    return load_settings()
