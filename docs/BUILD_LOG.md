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
