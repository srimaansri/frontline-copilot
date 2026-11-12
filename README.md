# Frontline Copilot

> Unofficial demo. Not affiliated with or endorsed by any carrier. No real customer data.

An AI copilot for frontline support agents at a wireless carrier, built end to end on **Databricks Free Edition**. An agent asks a question in plain words and gets a short, plain-language answer with cited help articles, a plan lookup grounded in SQL, a summary of a redacted call transcript, or a hand-off to a human when the request needs real account access.

## Status

This repo is being built milestone by milestone. **No results are reported yet**: every number that appears here later will come from a real run, with its date and git SHA.

| Milestone | What | State |
|---|---|---|
| M0 | Scaffold: tooling, config loader, CI | Done |
| M1 | Data generation and PII redaction, measured locally | Next |
| M2 | Databricks pipelines: bronze, silver, gold, quality checks | |
| M3 | Retrieval-augmented answers and the first evaluation | |
| M4 | Agent with tools, guardrails, escalation | |
| M5 | Streamlit app on Databricks Apps, MCP server | |
| M6 | Results, model and data cards, responsible-AI notes | |

The full specification is in [PLAN.md](PLAN.md).

## What it is built with

Unity Catalog, Delta Lake and PySpark for the data pipeline. Databricks AI Search for retrieval. An open-weight LLM served by the Databricks Foundation Model APIs. MLflow 3 for tracing and evaluation, with RAGAS. LangGraph for the agent. Presidio and spaCy for PII redaction. Streamlit on Databricks Apps for the interface, and an MCP server so other assistants can call the same tools.

## Development

Requires Python 3.11 or 3.12.

```bash
python -m venv .venv
```

Activate the environment (`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` elsewhere), then:

```bash
pip install -e ".[dev]"
```

Checks, the same ones CI runs:

```bash
ruff check .
```

```bash
ruff format --check .
```

```bash
mypy src/
```

```bash
pytest --cov=src/copilot
```

Configuration comes from `config/settings.yaml`, overridden by a local `.env` (copy `.env.example`) and by environment variables. Nothing secret is committed.

## How this was built

With AI coding assistants, under written rules. [CLAUDE.md](CLAUDE.md) is the working agreement given to Claude Code, and [docs/BUILD_LOG.md](docs/BUILD_LOG.md) records what was asked, what was produced, and what was changed or rejected.
