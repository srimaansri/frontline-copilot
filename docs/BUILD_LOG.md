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

---

## 2026-11-12 — M1: data generation and redaction (knowledge base still open)

**Tool:** Claude Code.

**Asked:** start Milestone 1.

**What it built**

- `data_gen/plans.py`: 8 fictional plans and 10 add-ons and fees.
- `data_gen/synth_transcripts.py` and `transcript_templates.py`: 200 seeded transcripts across 10 issue categories, call and chat. Every personal value enters through a template slot and its character span is recorded at that moment. No language model is involved.
- `src/copilot/redaction.py`: a Presidio-based redactor for 10 PII types and 2 CPNI types, with placeholders numbered per conversation.
- `src/copilot/span_metrics.py` and `eval/redaction_eval.py`: span matching, precision, recall and F1, and a report that can only be saved from a clean working tree.
- `eval/data/redaction_challenge.txt`: 50 hand-written lines in phrasings the templates do not contain.
- `data_gen/scrape_kb.py`: a scraper that obeys robots.txt, waits between requests, caps pages and caches HTML.
- 169 tests pass and 2 are expected failures that document known limits. Line and branch coverage of `src/copilot` is 100%.

**Results** (all from 2026-11-12, spaCy `en_core_web_md` 3.8.0, Presidio 2.2.366; full reports in `eval/results/`)

| Set | PII recall | PII precision | CPNI recall | CPNI precision | Commit |
|---|---|---|---|---|---|
| Test, 30 transcripts | 1.000 (209/209) | 1.000 | 1.000 (12/12) | 0.923 | `b0a26de` |
| Challenge, first run | 0.769 (30/39) | 0.857 | 0.333 (2/6) | 1.000 | `ed7ad27` |
| Challenge, after fixes | 0.923 (36/39) | 0.973 | 0.667 (4/6) | 1.000 | `b0a26de` |

The plan's target was PII recall of at least 0.95. The test set meets it and the challenge set does not, before or after the fixes.

**How far to trust these numbers**

- The test set shares its templates with the dev set the redactor was tuned on. Only the names, numbers and the mix of blocks differ. A perfect score there shows the tuning worked; it says little about unseen phrasing.
- The challenge set is the better guide, and it is 45 labeled values. One miss moves PII recall by more than two points.
- Claude Code proposed the challenge set after the dev score reached 1.000. Without it this log would report a perfect score and nothing else.
- The second challenge result is not a held-out number, because the fixes were written after reading the first one. Both files are kept.

**Bugs found by tests and evaluation**

- *Presidio matches case-insensitively by default.* Patterns that rely on capitalisation were matching ordinary words: "I'm sorry we couldn't" was tagged as a person and "1 key, then follow the" as an address. The first dev run had 236 false positives on PERSON. The flags are a per-recognizer setting; the `regex_flags` argument of `analyze()` only affects allow-list matching, which the installed source confirmed.
- *Presidio's cue-word boost ignores stop words.* "used", "made" and "call" are stop words in spaCy, so "you made 412 minutes of calls" and "call you back at 3035550129" got no boost. Those cues are now part of the patterns.
- *A lookahead bug in the first draft.* The dollar pattern rejected any amount followed by a full stop, so "$119.45." at the end of a sentence was missed. CPNI_AMOUNT recall on dev went from 0.426 to 1.000 after the fix.
- *A regression caught by the dev set.* The grouped-digits account pattern added for the challenge set also matched phone-shaped numbers, and "account team" nearby made 6 phone numbers come out labeled as account numbers. The 30-transcript test set had no such line and showed nothing. Fixed in `b0a26de` with a regression test.
- *A wrong test.* One evaluation test assumed "Rex" would not be detected; the small spaCy model tags it as a person. The test was wrong, not the code.

**Decisions**

- Long identifiers (9 or more digits) are redacted with no cue word. Four digits, a dollar amount or a usage figure need a cue, because redacting all of them would wreck the text.
- A turn of eight words or fewer borrows the previous turn's words as cues. Borrowing on every turn caused false positives on dev.
- "A Late Payment Fee of $5 on your statement" is flagged as CPNI and the generator does not label it. That accounts for every CPNI false positive on dev and test. It was left as is, because a fee on a named customer's statement is arguably billing detail.
- An `Entity` stores a type, a span and a placeholder, never the raw value.
- `plans.csv` gained `kind` and `billing_period` columns. PLAN.md §5.3 is updated.
- The scraper's default User-Agent describes the tool without naming a person or the repo. `--user-agent` can add a contact.

**Known limits**

- Digits spoken as words, emails spelled out loud, dates and amounts written in words. Real call transcripts may contain these, depending on the speech-to-text system.
- Usage figures with no cue word nearby ("1,140 minutes of talk time in October").
- A full Social Security number is masked, but as `ACCOUNT_NUMBER`; there is no dedicated type.

**Still open in M1**

- The knowledge base. `data_gen/seed_urls.txt` is empty, so the scraper has not been run against a real site, and `synth_kb.py` is not written because it needs a model endpoint from the Databricks setup. The acceptance criterion "at least 40 articles" is not met yet.

**For me to review**

- Whether the "Late Payment Fee of $5" case should count as CPNI.
- The templates in `data_gen/transcript_templates.py`: they set the tone of every transcript.
- This entry, like the earlier ones, was drafted by Claude Code in my voice.

---

## 2026-11-13 — Databricks workspace setup

**Tool:** Claude Code, with the Databricks CLI.

**Asked:** help me get from a fresh Free Edition sign-up to a workspace the pipelines can use.

**What was done**

- I signed up for Free Edition and signed in with `databricks auth login` (OAuth in the browser) under a CLI profile named `frontline`. No access token is stored anywhere.
- Claude Code then created, through the CLI: the `frontline` catalog; the schemas `raw`, `bronze`, `silver`, `gold` and `ops`; the volume `frontline.raw.landing`; the AI Search endpoint `frontline-vs` (Standard); and the MLflow experiment. The SQL is the same as `setup/00_setup.sql`.
- It looked up the SQL warehouse ID and the available models instead of having me find them in the UI.

**What the checks showed** (PLAN.md §3 is updated to match)

- `CREATE CATALOG` is allowed on Free Edition, so the plan's fallback to the default catalog was not needed.
- All three planned models are available: `databricks-gpt-oss-120b` for the copilot, `databricks-meta-llama-3-3-70b-instruct` as the judge, `databricks-gte-large-en` for embeddings.
- One test request to `gpt-oss-120b` with a tool attached came back as a tool call with correct arguments. That is one request, so it shows the feature works and nothing about how often.
- The AI Search endpoint reported ONLINE as soon as it was created.

**Things that went wrong on the way**

- `winget` was not on the PATH of the shells Claude Code uses, and its first install attempt hung on a yes/no prompt that a hidden shell cannot answer. It worked through winget's full path with the accept flags.
- The CLI's sign-in opened Outlook instead of a browser, because Windows has Outlook set as the handler for web links on this machine. Setting `BROWSER=none` makes the CLI print the link, which was then opened in Chrome.
- My workspace home folder did not exist yet, so creating the MLflow experiment failed with "Parent directory does not exist". Creating the folder first fixed it.

**Not checked yet**

- Whether a serverless notebook can download the spaCy model and the `tiktoken` encoding. This is tested in the first M2 notebook run.
- Whether Free Edition allows personal access tokens. Only `eval.yml` in GitHub Actions would need one.
