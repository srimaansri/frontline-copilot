# CLAUDE.md — Frontline Copilot

## What this repo is
Portfolio demo: an AI copilot for wireless-carrier frontline support agents, on Databricks Free Edition. Full spec and milestones live in `PLAN.md`. Read it before starting any task.

## How to work
- Work one milestone at a time (PLAN.md §12). Before starting a milestone, restate its acceptance criteria and list the files you'll touch.
- Verify any Databricks / MLflow / LangGraph / MCP API against current official docs before using it. If the docs differ from PLAN.md, follow the docs, update PLAN.md, and log the change in `docs/BUILD_LOG.md`.
- After each milestone: run `ruff check`, `ruff format --check`, `mypy src/`, `pytest`, then append a dated entry to `docs/BUILD_LOG.md` (what was built, decisions, anything I should review).
- When a step needs me to do something by hand in the Databricks UI, stop and give me an exact checklist.
- Commit after each coherent unit: a module with its tests, a config change, a doc update. Run the lint, type and test commands before every commit. Messages use a short conventional prefix (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`) and say why when it is not obvious.
- Add a dependency in the milestone that first uses it, pinned, in the matching optional group in `pyproject.toml`.

## Rules
- Never commit secrets. Config comes from `.env` and `config/settings.yaml` only.
- Never write unredacted transcript text to silver/gold tables, logs, or MLflow traces.
- Redact user input before it enters any traced function. MLflow records a traced function's inputs before its body runs, so redacting inside the trace is too late.
- Tune the redactor on the dev set only. Never tune on the test set. If the challenge set prompts a fix, keep the earlier result file and say the later one is no longer held out.
- Never commit scraped KB text or anything under `data/raw/`. Only `seed_urls.txt` and the scraper are committed.
- Never read `DATABRICKS_TOKEN` in code. Build `WorkspaceClient()` and let the SDK resolve auth, so the same code runs locally and as a Databricks App.
- SQL from tools must be parameterized. No string-built SQL from model input.
- Pure logic goes in `src/copilot/` with unit tests. Notebooks in `pipelines/` stay thin.
- Never invent eval or redaction numbers in README or docs. Only report numbers produced by a real run, with date and git SHA.
- Data generation is seeded and deterministic. Every pipeline step is idempotent.

## Commands
- Install: `python -m venv .venv`, activate it, then `pip install -e ".[dev,models]"` (or `uv sync --extra dev --extra models`)
- Lint: `ruff check .`
- Format check: `ruff format --check .`
- Types: `mypy src/`
- Tests: `pytest --cov=src/copilot`
- Data gen: `python -m data_gen.synth_transcripts --seed 42`, `python -m data_gen.plans`
- Knowledge base: `data/synthetic/kb_articles.jsonl` is committed and is the source. `python -m data_gen.synth_kb` only writes articles that are missing; `--force` rewrites all of them and should be a deliberate act. `python -m data_gen.scrape_kb` exists but is not used.
- Databricks CLI: signed in as profile `frontline`. Pass `--profile frontline` on every CLI command.
- Upload: `python -m data_gen.upload`
- Pipeline: commit first, then `databricks bundle deploy --profile frontline` and `databricks bundle run frontline_pipeline --profile frontline`. The job records the deployed git SHA with its metrics, so deploying uncommitted code makes those numbers untraceable.
- In Git Bash, Databricks paths such as `/Workspace/...` and `/Volumes/...` get rewritten into Windows paths. Use the Python SDK or PowerShell for commands that take them.
- Dev set for tuning the redactor: `python -m data_gen.synth_transcripts --seed 7 --out-dir data/raw/dev --labeled 200`
- Redaction eval: `python -m eval.redaction_eval` (test set), `--data-dir data/raw/dev --show-errors` (dev set), `--challenge` (hand-written set). Add `--save --tag <name>` to record a result; it needs a clean working tree.
- Eval: `python -m eval.run_eval --config A --query-type ann --tag baseline` (always try `--limit 5` first)
- App (local): `uvicorn api.main:app --port 8000` for the API, then `npm run dev` in `web/` for the interface. `npm run dev:mock` in `web/` needs no API.
- App (deploy): commit first, then `python setup/deploy_app.py`. It builds `web/`, uploads and deploys.
- MCP (stdio): `python -m mcp_server.server`

## Stack
Python 3.11+ (3.11 in Databricks Apps, 3.12 on serverless) · PySpark · Delta Lake · Unity Catalog · Databricks AI Search, formerly Vector Search (`databricks-ai-search`) · Databricks Foundation Model APIs (open-weight LLM) · MLflow 3 + RAGAS · LangGraph · databricks-langchain · Presidio + spaCy · FastAPI + React, TypeScript, Vite, Tailwind (Databricks Apps) · MCP Python SDK · Docker · pytest · ruff · mypy · GitHub Actions
