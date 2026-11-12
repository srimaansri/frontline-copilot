# Build log

Dated notes on how this repo was built: what was asked of the AI tools, what they produced, and what was changed or rejected and why. Newest entry last.

---

## 2026-11-11 — Plan review before any code

**Tool:** Claude Code.

**Asked:** read `PLAN.md` and `CLAUDE.md` thoroughly before starting.

**What it did:** read both files, checked the plan's API details against the current official docs, and came back with a review instead of code. I approved the changes below and they were applied to `PLAN.md` and `CLAUDE.md` in this commit.

### Changes because the docs differ from the plan

| Plan said | Docs say (read 2026-11-11) | Source |
|---|---|---|
| `databricks-vectorsearch`, `VectorSearchClient` | Product renamed AI Search. Package `databricks-ai-search`, class `AISearchClient`. The old package is a shim that warns on import. | [Create AI Search endpoints and indexes](https://docs.databricks.com/aws/en/vector-search/create-vector-search), [PyPI](https://pypi.org/project/databricks-ai-search/) |
| `query_type="HYBRID"` | Examples use `query_type="hybrid"`; ANN is the default when the argument is omitted. | [Query an index](https://docs.databricks.com/aws/en/vector-search/query-vector-search) |
| MCP server built with `FastMCP` | The SDK README now shows `from mcp.server import MCPServer` and links a v2 migration guide. To be settled at M5 against the pinned version. | [python-sdk README](https://github.com/modelcontextprotocol/python-sdk) |
| Python 3.11 everywhere | Serverless environment versions 3–6 run Python 3.12.3. Databricks Apps runs 3.11. CI now tests both. | [Serverless environment versions](https://docs.databricks.com/aws/en/release-notes/serverless/environment-version/), [Apps environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env) |
| Embedding model `gte-large-en` or `bge-large-en` | `bge-large-en` has a 512-token window, too small for 800-token chunks. Only `gte-large-en` is used. | [Supported foundation models](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models) |
| Nothing about app uptime or quota | Free Edition apps stop 24 hours after each start. Exceeding the daily quota turns compute off for the rest of the day. Serverless outbound access is limited to trusted domains. | [Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations) |

### Changes because the plan contradicted itself or left a gap

- **Milestone order.** M3 asked for an evaluation that needs tools and guardrails from M4. M3 now evaluates the `kb` rows only; the full set is re-run after M4.
- **Experiment design.** The A/B run changed chunk size and query type together. It is now three runs, each changing one thing.
- **PII in traces.** Redaction inside a LangGraph node happens after MLflow has already recorded the graph input. `run_copilot` now redacts before any traced code, and a test will assert it.
- **Support numbers treated as PII.** The leak scan and the output guard would have flagged the carrier's own phone numbers in help articles. The scan now covers transcript tables only, and contact details that appear in a retrieved chunk are kept.
- **CPNI.** The plan injected bill amounts and usage figures but defined no entity for them. They are now `CPNI_AMOUNT` and `CPNI_USAGE`, measured and reported apart from the 0.95 PII recall target.
- **Judge model.** The judge was the same model as the copilot. It is now a different model family.
- **Eval cost.** RAGAS `Faithfulness` was dropped as a duplicate of `RetrievalGroundedness`. RAGAS `ContextPrecision` stays.
- **App layout.** `app.yaml` moves to the repo root so the deployed app can import `src/copilot`. The app authenticates as a service principal, so code never reads a token directly.
- **Downloads on serverless.** `tiktoken` and spaCy fetch files from hosts that serverless may block. Fallbacks are written into §6 and §14.
- **Scraped text.** Scraped articles are the carrier's copyright and are not committed. A synthetic KB, if used, is committed because an LLM cannot regenerate it deterministically.
- **New stretch milestone S-AWS.** A Bedrock provider switch, Bedrock Guardrails as an extra output check, and a quality / latency / cost comparison table. After M6.

### My decisions

- I chose the defaults Claude Code proposed for the KB source, CPNI handling and the judge model.
- I asked to keep RAGAS `ContextPrecision` when it proposed trimming the RAGAS scorers.
- I added the S-AWS milestone.

### Not yet verified

These depend on what Free Edition allows and are checked during workspace setup (PLAN.md §3): creating a personal access token, creating a catalog, which chat models are listed and whether the chosen one makes tool calls, and whether spaCy and `tiktoken` downloads work from a serverless notebook.

---

## 2026-11-11 — M0: scaffold

**Tool:** Claude Code.

**Asked:** apply the approved plan changes, then build Milestone 0, committing in small steps.

**What it built**

- `pyproject.toml`: hatchling build, pinned dependencies, ruff, `mypy --strict` with the pydantic plugin, pytest, and a coverage floor of 80%.
- `src/copilot/config.py`: a frozen `pydantic-settings` class. Sources in order: environment, `.env`, `config/settings.yaml`, defaults.
- `tests/test_config.py`: 17 tests covering source precedence, validation, and loading with no credentials present.
- `.github/workflows/ci.yml`: lint, format check, type check and tests on Python 3.11 and 3.12.
- `setup/00_setup.sql`, `.env.example`, `.gitignore`, `.gitattributes`, a README stub and an empty `data_gen/seed_urls.txt`.

**Local result:** `ruff check`, `ruff format --check`, `mypy src/` and `pytest --cov=src/copilot` all pass on Python 3.12.10 (Windows). 17 tests, 100% line and branch coverage of `src/copilot`. Python 3.11 is covered by CI only; it is not installed on the laptop.

**CI result:** the scaffold (commit `821f910`) passes every step on Python 3.11 and 3.12 in [GitHub Actions](https://github.com/srimaansri/frontline-copilot/actions/workflows/ci.yml). This closes M0.

**Decisions**

- **No token in settings.** `Settings` has no credential field and ignores `DATABRICKS_TOKEN` if it finds one in `.env`. A test asserts the token never appears on the object.
- **Defaults are the experiment baseline.** `chunk_config: A` and `query_type: ann` until real eval runs pick a winner. `min_retrieval_score` is 0 (off) because no real scores exist yet to set it from.
- **`ruff` rule set includes bandit (`S`).** `S608` flags string-built SQL, which backs the "parameterized SQL only" rule with a lint check.
- **Setup SQL uses a literal catalog name.** The `IDENTIFIER(:param)` clause is documented for tables, views and functions but not for `CREATE CATALOG`, `CREATE SCHEMA` or `CREATE VOLUME` ([docs](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-names-identifier-clause)), so the file says to find-and-replace the name instead.
- **Exact version pins**, as the plan asks. This may need loosening at M2 if an exact `pydantic` pin conflicts with what serverless preinstalls.
- **`venv` + `pip`**, because `uv` is not installed on the laptop. `uv sync` still works from the same `pyproject.toml`.
- **GitHub Actions at `@v6`** for `checkout` and `setup-python`. A `v7` shows up on mirrors but I could not confirm it on github.com.

**For me to review**

- The 2026-11-11 plan-review entry above was drafted by Claude Code in my voice. Edit anything that does not match how I would put it.
- The repo has no licence file yet. That choice is mine.
- The Copilot entry for the chunking unit tests (M2/M3) is mine to write.
