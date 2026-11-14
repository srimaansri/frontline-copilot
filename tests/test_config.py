"""Settings loading: source precedence, validation, and no dependence on credentials."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from copilot.config import DEFAULT_YAML_FILE, ChunkingConfig, Settings, get_settings, load_settings


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every settings variable so the developer's shell cannot leak into a test."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)


def _load(tmp_path: Path, *, yaml_text: str | None = None, env_text: str | None = None) -> Settings:
    """Load settings from temp files only; a file that is not written simply does not exist."""
    yaml_file = tmp_path / "settings.yaml"
    env_file = tmp_path / ".env"
    if yaml_text is not None:
        yaml_file.write_text(yaml_text, encoding="utf-8")
    if env_text is not None:
        env_file.write_text(env_text, encoding="utf-8")
    return load_settings(yaml_file=yaml_file, env_file=env_file)


def test_defaults_load_without_files_or_credentials(tmp_path: Path) -> None:
    settings = _load(tmp_path)

    assert settings.catalog == "frontline"
    assert settings.top_k == 5
    assert settings.databricks_host is None
    assert settings.sql_warehouse_id is None


def test_yaml_overrides_defaults(tmp_path: Path) -> None:
    settings = _load(tmp_path, yaml_text="catalog: workspace\ntop_k: 3\n")

    assert settings.catalog == "workspace"
    assert settings.top_k == 3


def test_dotenv_overrides_yaml(tmp_path: Path) -> None:
    settings = _load(tmp_path, yaml_text="top_k: 3\n", env_text="TOP_K=7\n")

    assert settings.top_k == 7


def test_environment_overrides_dotenv_and_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOP_K", "9")

    settings = _load(tmp_path, yaml_text="top_k: 3\n", env_text="TOP_K=7\n")

    assert settings.top_k == 9


def test_blank_dotenv_value_means_not_set(tmp_path: Path) -> None:
    settings = _load(tmp_path, yaml_text="catalog: workspace\n", env_text="CATALOG=\n")

    assert settings.catalog == "workspace"


def test_token_in_dotenv_is_ignored_and_never_exposed(tmp_path: Path) -> None:
    settings = _load(tmp_path, env_text="DATABRICKS_TOKEN=not-a-real-token\nCATALOG=demo\n")

    assert settings.catalog == "demo"
    assert not hasattr(settings, "databricks_token")
    assert "not-a-real-token" not in repr(settings)


def test_index_name_is_derived_from_catalog(tmp_path: Path) -> None:
    settings = _load(tmp_path, yaml_text="catalog: workspace\n")

    assert settings.index_name == "workspace.gold.kb_chunks_index"


def test_explicit_index_name_wins(tmp_path: Path) -> None:
    settings = _load(tmp_path, env_text="VS_INDEX=other.gold.my_index\n")

    assert settings.index_name == "other.gold.my_index"


def test_table_builds_three_part_name(tmp_path: Path) -> None:
    settings = _load(tmp_path)

    assert settings.table("silver", "transcripts_redacted") == (
        "frontline.silver.transcripts_redacted"
    )


def test_volume_path(tmp_path: Path) -> None:
    assert _load(tmp_path).volume_path("raw", "landing") == "/Volumes/frontline/raw/landing"


@pytest.mark.parametrize("bad", ["gold; DROP TABLE x", "kb-chunks", "a.b", "", "1table", "x y"])
def test_table_rejects_anything_but_a_plain_identifier(tmp_path: Path, bad: str) -> None:
    settings = _load(tmp_path)

    with pytest.raises(ValueError, match="not a valid identifier"):
        settings.table("gold", bad)
    with pytest.raises(ValueError, match="not a valid identifier"):
        settings.table(bad, "kb_chunks")


@pytest.mark.parametrize("bad", ["front line", "frontline;--", "my-catalog", "a.b"])
def test_catalog_must_be_a_plain_identifier(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValidationError, match="catalog"):
        _load(tmp_path, yaml_text=f"catalog: '{bad}'\n")


def test_query_type_accepts_any_case(tmp_path: Path) -> None:
    settings = _load(tmp_path, env_text="QUERY_TYPE=HYBRID\n")

    assert settings.query_type == "hybrid"


def test_unknown_query_type_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="query_type"):
        _load(tmp_path, yaml_text="query_type: keyword\n")


def test_active_chunking_follows_chunk_config(tmp_path: Path) -> None:
    settings = _load(tmp_path, yaml_text="chunk_config: B\n")

    assert settings.active_chunking == ChunkingConfig(chunk_size_tokens=350, overlap_tokens=60)


def test_undefined_chunk_config_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="chunk_config 'C' is not defined"):
        _load(tmp_path, yaml_text="chunk_config: C\n")


def test_overlap_must_be_smaller_than_chunk() -> None:
    with pytest.raises(ValidationError, match="must be smaller than"):
        ChunkingConfig(chunk_size_tokens=100, overlap_tokens=100)


def test_settings_are_immutable(tmp_path: Path) -> None:
    settings = _load(tmp_path)

    with pytest.raises(ValidationError):
        settings.top_k = 10  # type: ignore[misc]


def test_committed_settings_file_matches_the_plan(tmp_path: Path) -> None:
    """Guards config/settings.yaml: the experiment in PLAN.md §9.4 depends on these values."""
    settings = load_settings(yaml_file=DEFAULT_YAML_FILE, env_file=tmp_path / ".env")

    assert settings.chunking["A"] == ChunkingConfig(chunk_size_tokens=800, overlap_tokens=100)
    assert settings.chunking["B"] == ChunkingConfig(chunk_size_tokens=350, overlap_tokens=60)
    assert settings.chunk_config == "A"
    assert settings.query_type == "ann"
    assert settings.judge_endpoint != settings.llm_endpoint


def test_product_names_in_the_committed_settings_match_the_plan_catalogue(tmp_path: Path) -> None:
    from data_gen.plans import PLANS

    settings = load_settings(yaml_file=DEFAULT_YAML_FILE, env_file=tmp_path / ".env")

    assert settings.product_names == [row.name for row in PLANS]
    assert (
        load_settings(yaml_file=tmp_path / "none.yaml", env_file=tmp_path / ".env").product_names
        == []
    )


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()

    assert get_settings() is get_settings()

    get_settings.cache_clear()
