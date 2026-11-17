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
- Eval reports: `python -m eval.report` rebuilds `eval/results/SUMMARY.md` and `ERRORS.md` from the saved runs (`--save` does it too). Never edit them by hand. `python -m eval.gate` is the offline check CI runs: it fails when the newest full run is below the thresholds, or was made with another evaluation set or prompt version.
- Monitoring: `python -m eval.monitoring_report --days 7` reads the copilot's traces and ratings and prints counts, times, flags and ids, never text from a trace (`--limit 20` for a quick look; `--save` needs a clean tree). Traces written by the deployed app arrive without spans, because the app cannot reach the storage host MLflow uploads them to.
- To stop a background run on Windows, stop its process ids and check they are gone. Ending the tool's task leaves the shell and its Python children running.
- Routing eval: `python -m eval.routing_eval --router rules` scores the rules on the held-out routing set with no model call; `--router model --endpoint <name>` scores a model router (try `--limit 5` first), `--router agent` runs the whole copilot, and `--compare` scores every saved result. `--save` needs a clean tree. Never tune the rules or the router prompt on `eval/routing_set.jsonl`: if either changes after its errors were read, say the later result is no longer held out.
- Claim check eval: `python -m eval.claim_check_eval` measures the check on figures on the saved answers, with no model call. `--collect` asks the live copilot again.
- Larger evaluation set: `eval/eval_set_extended.jsonl` (260 rows, none reviewed yet). `python -m eval.check_eval_set` checks every row and every evidence quote. Run it with `python -m eval.run_eval ... --eval-set eval/eval_set_extended.jsonl`, with `--sample N` for a stratified sample. The CI gate reads only full runs of the 40-row set.
- Compliance: `python -m data_gen.synth_breaches` writes the labelled calls under `data/raw/compliance/`; `python -m eval.compliance_eval` scores the development half. The held-out half has been scored once; a later `--held-out --save` is no longer first contact and says so.
- Wrap-up eval: `python -m eval.wrapup_eval --limit 5` first, then `--save` (about 200 model calls; `--resume` continues a stopped run).
- Call assist eval: `python -m eval.assist_eval --limit 5` first, then `--save` (about 1,100 searches and 300 model calls; `--resume` continues a stopped run). The thresholds in `src/copilot/assist.py` were set with calls T0001 to T0005 in view, so those five are not held out.
- Checking the judge: `python -m eval.judge_sheet eval/results/<run>.json` writes the judge's verdicts as a sheet under `eval/labels/` for a person to label (`--blind` keeps the verdicts out of sight). `python -m eval.judge_controls --list` shows 23 deliberately wrong answers; `--save --originals` has the judge score them. `python -m eval.judge_agreement <sheet.csv> ...` scores the judge against the labels. The `human` column is the owner's: never fill it with a model.
- Demo recording: commit first, then `python -m eval.record_demo` (try `--limit 3` first; it writes nothing). It writes `web/src/api/recorded.json`, which the public demo replays. Never edit that file by hand.
- App (local): `uvicorn api.main:app --port 8000` for the API, then `npm run dev` in `web/` for the interface. `npm run dev:mock` in `web/` needs no API: it replays the recording.
- App (deploy): commit first, then `python setup/deploy_app.py`. It builds `web/`, uploads and deploys.
- MCP (stdio): `python -m mcp_server.server`

## Stack
Python 3.11+ (3.11 in Databricks Apps, 3.12 on serverless) · PySpark · Delta Lake · Unity Catalog · Databricks AI Search, formerly Vector Search (`databricks-ai-search`) · Databricks Foundation Model APIs (open-weight LLM) · MLflow 3 + RAGAS · LangGraph · databricks-langchain · Presidio + spaCy · FastAPI + React, TypeScript, Vite, Tailwind (Databricks Apps) · MCP Python SDK · Docker · pytest · ruff · mypy · GitHub Actions
