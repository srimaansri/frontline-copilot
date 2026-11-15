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

---

## 2026-11-13 — M1 closed: synthetic knowledge base

**Tool:** Claude Code, with `databricks-gpt-oss-120b` in my workspace writing the article text.

**Asked:** which knowledge base source it recommended. It recommended synthetic, which also matched the rule I had set (use synthetic if `seed_urls.txt` is empty when M1 starts), and went ahead.

**What it built**

- `data_gen/kb_topics.py`: 87 topics across six sections, each with a hand-written brief of the facts the article must state.
- `data_gen/synth_kb.py`: sends each brief to the model, validates the reply, retries up to three times, and resumes from a partly written file.
- `data/synthetic/kb_articles.jsonl`: the 87 generated articles, committed. 229 to 407 words each, median 293.

**Result:** 87 of 87 articles were written and all pass the checks. No article failed after retries. The run used four requests at a time and finished in under ten minutes; it was not timed more precisely than that.

**Decisions**

- The model writes prose only. Prices, fees, time limits and phone numbers come from the briefs and the plan catalogue. A test checks that every dollar amount in a brief exists in the catalogue.
- An article that quotes a dollar amount found in neither its brief nor the catalogue is rejected. This check was added while the first full run was in progress, then applied to the finished articles; none failed it.
- Typographic punctuation is mapped to ASCII. The trial run showed the model writing the support number with non-breaking hyphens, which a keyword search for the number would not match.
- Article URLs use the reserved `.example` domain so they cannot point at a real site.

**Known limit**

- The price check covers dollar amounts only. Reading two articles by hand, I found one detail no brief contains: the transfer article calls the PIN "six-digit". Details like this are harmless for grounding, because the copilot cites the article either way, but eval `expected_facts` must come from the briefs and not from the generated prose.

**Mistakes on the way**

- Claude Code said "88 topics" in two messages and a commit message. The list has 87. The commit message was corrected before pushing.
- Two of its scripted file edits corrupted escape sequences and broke two files. It repaired them by hand and the checks passed before anything was committed.

**M1 acceptance** (PLAN.md §12): at least 40 articles (87), 200 transcripts with 30 labeled, `plans.csv`, `redaction.py` with tests passing, and a local redaction evaluation that prints precision, recall and F1. All met.

---

## 2026-11-14 — M2: pipelines on Databricks

**Tool:** Claude Code, with the Databricks CLI and SDK.

**Asked:** start Milestone 2.

**What it built**

- `src/copilot/chunking.py`: the heading-aware chunker, with core tests.
- `data_gen/upload.py`: sends the four data files to the landing volume.
- `pipelines/01_ingest.py` to `05_quality_checks.py`: thin notebooks over `src/copilot`.
- `databricks.yml` and `resources/frontline_pipeline.job.yml`: a bundle that builds the project wheel and runs the five notebooks as one serverless job.
- `setup/01_probe_serverless.py`: a probe of what serverless can install and reach.

**Result of the first full run** (2026-11-14, commit `55692f5`, all five tasks succeeded)

| Task | Seconds | Outcome |
|---|---|---|
| ingest | 86 | 87 articles, 200 transcripts, 221 labels, 18 plan rows |
| redact | 82 | 200 transcripts redacted, 1,472 detections. PII 209/209 with 0 false positives; CPNI 12/12 with 1 false positive |
| chunk | 34 | 87 chunks for config A, 168 for config B, 255 rows inserted, Change Data Feed on |
| index | 1,922 | index created, 255 of 255 rows indexed, 20 of 20 smoke queries had the expected article in the top 3 |
| quality_checks | 48 | 18 of 18 checks passed, 0 PII leak hits |

The redaction numbers computed on Databricks are identical to the local test-set run, which is what should happen: same code, same 30 labeled transcripts.

**What the probe settled**

- The plan carried three fallbacks in case serverless could not download things. None was needed: PyPI, GitHub release downloads and the `tiktoken` file host are all reachable.
- The catch is the environment. A notebook task with no declared environment got Python 3.11.10 with pydantic 1.10.6, and installing Presidio over it left a stale `typing_extensions`, so the spaCy model failed to load. With serverless environment version 4 declared on the job, everything installs before the notebook starts and loads cleanly.

**Decisions**

- **Sections are packed into chunks.** The plan read as one chunk per section. On this knowledge base that would have made the experiment meaningless: sections are 60 to 150 tokens, so both the 800 and the 350 setting would have produced the same chunks. Claude Code raised this before writing the chunker. Packing whole sections up to the limit gives 87 chunks for A and 168 for B.
- **The job is a bundle, not notebooks run by hand.** The plan called this optional. It became the way the pipeline runs because it records the git commit with every metric.
- **Redaction output goes through a staging table**, so the model runs once and the result is split into redacted text (`silver`) and detection positions (`ops`). Detected values are never stored.
- **Chunks are merged by key**, so a re-run with unchanged articles writes nothing and the index does not re-embed.
- **Table names are validated.** `Settings.table()` and the catalog setting accept plain identifiers only, because the notebooks put them in SQL text.

**Things that went wrong on the way**

- Git Bash rewrote `/Workspace/...` into a Windows path, so the first CLI attempts failed. The SDK is used for those calls now, and CLAUDE.md says so.
- The folder I first chose for the probe notebook had the same path as the MLflow experiment, which is also a workspace object.
- Two new chunking tests miscounted the words in a chunk's first line. The tests were wrong, not the chunker.
- Another scripted edit corrupted escape sequences, the second time in two days. Claude Code now makes such edits one at a time.

**Worth knowing**

- The index task took 32 minutes, almost all of it Databricks provisioning the endpoint for its first index. A later sync should be much quicker, but that has not been measured.
- In one smoke query (config A, hybrid search, "How do I set up voicemail on a new phone?") the top hit was the article on resetting a voicemail PIN, with the expected article still in the top 3. Twenty smoke queries are not an evaluation; whether hybrid search helps or hurts is a Milestone 3 question.

**For me to review**

- `tests/test_chunking_core.py` was written by Claude Code so the chunker was verified before it ran on Databricks. `tests/test_chunking.py` is still mine to write with Copilot, with my own log entry.

**M2 acceptance** (PLAN.md §12): setup SQL run, data uploaded, notebooks 01 to 05 green on serverless, `gold.kb_chunks` with Change Data Feed, quality checks passing with zero PII leaks. All met.

## 2026-11-14 — M3: the copilot, the evaluation set and the first results

**Tool:** Claude Code, with reviewer agents for the knowledge base and the evaluation rows.

**Asked:** continue with Milestone 3. Part way through I changed the order of work: fix the help articles first, then have the questions reviewed, then review every question myself.

**What it built**

- `src/copilot/`: `schemas.py`, `prompts.py`, `llm.py`, `retriever.py`, `guardrails.py` and `agent.py`. A retrieve-then-answer copilot that redacts the question before any traced code runs, retrieves from the index, answers with numbered citations and checks every citation against what was retrieved.
- `eval/eval_set.jsonl`: 40 rows (22 knowledge base, 6 plan, 4 call summary, 5 escalation, 3 adversarial).
- `eval/scorers.py`: checks that need no model (answer recorded, reading level, citations, expected article, latency) and the judge models' checks.
- `eval/run_eval.py`: runs one configuration, matches rows to traces by tag and saves a result only from a clean working tree.

**Results** (2026-11-14, commit `1a35afb`, 22 knowledge-base rows, all reviewed, prompt v2, judge `databricks-meta-llama-3-3-70b-instruct`)

| Measure | A, vector | B, vector | B, hybrid |
|---|---|---|---|
| Expected article in the top 5 | 21/21 | 20/21 | 21/21 |
| Share of retrieved chunks judged relevant | 0.53 | 0.64 | 0.65 |
| RAGAS context precision | 0.94 (n=20) | 0.92 (n=21) | 0.91 (n=21) |
| Retrieved text is enough to answer | 21/21 | 21/21 | 21/21 |
| Grounded | 21/21 | 21/21 | 21/21 |
| Correct | 19/21 | 18/21 | 18/21 |
| No-answer question handled | 1/1 | 1/1 | 1/1 |
| Relevant | 22/22 | 22/22 | 22/22 |
| Citations valid | 22/22 | 22/22 | 22/22 |
| Reading grade 8 or below | 20/22 | 19/22 | 20/22 |
| Median time to answer | 2.1 s | 2.1 s | 2.1 s |

A is 800-token chunks, B is 350-token chunks. No setting is clearly better: with 21 questions a difference of one row is noise. Smaller chunks made retrieval more focused and did not make answers more correct. Hybrid search found the one article that vector search over small chunks missed. Setting A with vector search stays the default. The README has the full table and the reading of it.

Claude Code inspected four of the eight "incorrect" marks. One is a retrieval miss (E017 with B and vector search), one is a real mistake in the answer (E013, the account PIN), and two are judge mistakes (E014, E015: the answers contain every expected fact). The numbers are reported as the judge gave them.

**The review, in the order it happened**

1. A first draft pass (config A, plain search, commit `04138f9`) scored 16 of 22 on correctness. It is kept in `eval/results/` and marked superseded, because the rows had not been reviewed and the articles had not been corrected.
2. Two reviewer agents read all 87 help articles, one for consistency between articles and one against each article's brief. They reported 247 issues, which came to 170 distinct corrections in 68 articles (41 high, 55 medium, 74 low). Every correction is recorded in `data/synthetic/kb_corrections.jsonl`. The pipeline was re-run and the index rebuilt.
3. Two more reviewer agents read the 40 questions against the corrected articles, one for whether each question can be answered and one for how it is graded.
4. I reviewed all 40 rows on a page that showed each current row next to one proposed version. I accepted all 31 proposals and confirmed the other 9.

**What the question review changed**

- 27 rows were changed. The most common fault: a row expected a fact the question never asked for, so a short, correct answer would have been marked wrong.
- 4 rows were replaced to cover cases nothing tested: a question no article answers (E041), a call that was resolved (E042), a call that ended unresolved (E043) and an invalid transcript id (E044).
- After a smoke run I loosened one rule on E041. The judge failed "I don't have information about this in the available resources" because the rule said "help articles". The rule now names the behaviour, and an invented discount still fails.

**What changed in the grading**

- A row can list a second article that also holds the whole answer (`also_acceptable_sources`).
- A citation is required only where the row names an article.
- Rows with rules and no facts are graded by MLflow's `ExpectationsGuidelines` judge.
- The retrieval judges and RAGAS skip a row that names no article, because nothing retrieved can be sufficient for a question no article answers.
- An empty or missing answer cannot pass a check, and the runner stops without saving if any row has no answer.
- RAGAS now gets only the expected facts as its reference. MLflow's adapter joins every expectation value, so the reference used to read like `['fact', ...], late-payment-fee, False, search_kb`.
- The prompt gained an out-of-scope rule and became v2.

These changes mean the saved results are not comparable with the draft pass. They were made for fairness, each for a stated reason, and none lowers a bar the copilot has to clear.

**Decisions**

- **Retrieval queries use the Databricks SDK.** `AISearchClient` refused the OAuth sign-in a CLI profile gives, and the project rule is to let the SDK resolve auth.
- **Evaluation runs one row at a time, two judge calls a second.** MLflow's defaults got HTTP 429 from the judge endpoint. A test with six judges at once was no faster (53 seconds a row against 55) and had rejected calls, so the limit is the workspace's cap on the judge model. A 22-row pass takes about 24 minutes.
- **Product names are not people.** The redactor was replacing plan names such as "Northline Plus 10" with a person placeholder. Catalogue names are now protected. Redaction scores on the dev, test and challenge sets did not change.

**Things that went wrong on the way**

- I committed once with a lint error and fixed it in the next commit.
- A count in a status message was wrong twice (87 topics, not 88; 21 proposals, not 20).
- The model wrote citations as `【1】` and used non-breaking hyphens. Both are normalised now.

**Worth knowing**

- The judge is a model and makes mistakes. In the smoke run it marked a correct, cited answer about travel to Mexico as not grounded. The hand spot-check of the judge on 10 rows is still to do.
- The output guard planned for Milestone 4 must leave alone the catalogue names, amounts and support contact details that appear in the retrieved text. The redactor would otherwise strip the support phone number from an answer.
- The redactor turns a made-up transcript id such as "T99" into a person placeholder. To look at on the dev set in Milestone 4.

**For me to review**

- The results table above against `eval/results/SUMMARY.md`.
- The four inspected "incorrect" marks, and the other four that were not inspected.
- The judge has not been checked by hand on 10 rows yet. That needs a person.
- `tests/test_chunking.py` is still mine to write with Copilot.

**M3 acceptance** (PLAN.md §12): index online; `run_copilot` answers knowledge-base questions with citations; traces in MLflow carry no raw personal data in their inputs; all 40 evaluation rows reviewed; the three runs evaluated on the knowledge-base rows; results committed. All met. The hand check of the judge on 10 rows is not part of this milestone's criteria and is still open.

## 2026-11-14 — M4 and M5: the agent, its guardrails, the app and the MCP server

**Tool:** Claude Code.

**Asked:** keep going while the Milestone 3 evaluation runs were in progress, keep Streamlit, add no REST API or JavaScript front end, and put finishing the planned milestones and a README with real results first.

**What it built**

- `src/copilot/tools.py`: the four tools as plain typed functions, with a SQL runner on the Databricks SDK. Every value a model supplies is a bound parameter.
- `src/copilot/guardrails.py`: `check_input` (plain rules that route an account request to a hand-off and an instruction-override attempt to a fixed refusal) and `check_output` (one rewrite of a hard answer, then citations, then personal data).
- `src/copilot/agent.py`: the copilot as a LangGraph graph. `run_copilot` kept its signature, so the app and the evaluation did not change.
- `src/copilot/readability.py`, `src/copilot/transcripts.py`: reading grade, and reading redacted transcripts for display.
- `eval/scorers.py`: `escalation_correct`, `tool_choice` and `no_pii_leak`.
- `mcp_server/`: an MCP server for the four tools, with a Dockerfile.
- `app/app.py` and `app.yaml`: the Streamlit interface.
- `docs/MODEL_CARD.md`, `docs/DATA_CARD.md`, `docs/RESPONSIBLE_AI.md`.
- The table `frontline.ops.escalations`, created in the workspace.

**Result on all 40 rows** (run finished 2026-11-15 00:58 UTC, commit `8624268`, setting A with vector search, prompt v3)

| Kind of question | Rows | Correct | Rules followed | Hand-off right | Right tool | No personal data in the answer |
|---|---|---|---|---|---|---|
| Help articles | 22 | 18/21 | 1/1 | 22/22 | 22/22 | 22/22 |
| Plan lookups | 6 | 6/6 | 1/1 | 6/6 | 5/6 | 6/6 |
| Call summaries | 4 | 2/3 | 1/1 | 4/4 | 3/3 | 4/4 |
| Requests that need a person | 5 | not scored | 5/5 | 5/5 | 5/5 | 5/5 |
| Trick questions | 3 | 1/1 | 3/3 | 3/3 | 1/1 | 3/3 |
| All | 40 | 27/31 | 11/11 | 40/40 | 36/37 | 40/40 |

Median time to answer 2.5 seconds. 37 of 40 answers at reading grade 8 or below.

**How the work was kept apart from the running evaluation**

The evaluation refuses to start from a dirty folder and stamps its result with the current commit. So this work was done in a second working copy on its own branch (`git worktree`), and merged when the runs had finished.

**Decisions**

- **Tool schemas are written by hand.** The serving endpoint accepts no `anyOf` or `pattern` in a schema, which is what a schema generated from optional Python types contains.
- **Spans are opened by hand, not by autologging.** What a trace records is then decided in one place, which is what the personal-data rule needs.
- **Account requests are routed by rules, before the model.** Deterministic, free, and testable. The model can still open a hand-off for what the rules miss.
- **The answer check keeps what the sources state.** A phone number, price or address written in a retrieved article or a tool result is public and stays in the answer. Anything else the redactor finds is replaced.
- **MLflow is given redacted questions.** MLflow stores the evaluation dataset with the run, and one row has personal data in its question on purpose. The copilot is still called with the question as written.
- **FastMCP, not MCPServer.** The plan had noted a newer server class in the MCP SDK's README. The pinned release, 1.30.0, does not have it.
- **The app is a Streamlit page, as planned.** No REST API and no JavaScript front end were added.

**Things that went wrong on the way**

- **The model picked the wrong section to search.** The search tool offered a section filter. For a voicemail question the model chose "Account", the search returned that section's articles, and the copilot said no article exists. A smoke run on three rows caught it before the 40-row run. The model is no longer offered the filter.
- **The relevance judge failed correct refusals.** It marks "I can't help with that" as not relevant to a request for a poem. It now runs only where an answer is expected.
- **The 40-row run lost its report.** It scored every row, then got HTTP 401 while reading its traces back. The report was rebuilt from the same MLflow run with the runner's own functions, and the file says so.
- **I pushed a commit with one failing test.** The command that ran the checks did not stop on the failure. The test was a new one that loaded the local `.env` and changed settings for later tests; CI has no `.env` and would not have caught it. Fixed in the next commit.
- A file written by a local test run (`mlflow.db`) was staged by mistake and removed before anything was pushed.
- **The MCP server hung on its first real call over stdio.** The Databricks SDK signs in by running the Databricks CLI, which inherited the server's standard input, and over stdio that is the MCP channel. Unit tests could not see it; a live call from an MCP client did. The server now gives the transport its own copy of standard input.
- GitHub did not start CI jobs for about two hours ("account is locked due to a billing issue"). It cleared without a change to the repository.

**Worth knowing**

- The routing rules were written with the five hand-off rows in view. 5/5 on those rows is not an independent measure.
- In the 40-row run the judge again marked two answers incorrect that contain every expected fact.
- Tool calling on the answering model is documented by Databricks as tuned for a single step. Multi-step use worked in every case tried, which is a small sample.

**Not done**

- The app runs locally. It is not deployed to Databricks Apps.
- The MCP server was called by an MCP client over stdio against the live workspace, and its Docker image was built and answered over HTTP. It has not been registered with Claude Code itself, and its tools were not called inside the container.
- No demo video. No `eval.yml` gate. No hand check of the judge.

**For me to review**

- The three new documents in `docs/`, which state what the system does and does not do in my name.
- The README's reading of the results.
- `tests/test_chunking.py` is still mine to write with Copilot.

**M4 acceptance** (PLAN.md §12): all four tools working, the hand-off path, input and output guards, routing tests passing, the default setting evaluated on all 40 rows. All met.

**M5 acceptance** (PLAN.md §12): Streamlit app deployed as a Databricks App; MCP server working from Claude Code over stdio and in Docker. Partly met: the app runs locally and is not deployed, and the MCP server works over stdio from a client and starts in Docker. See "Not done".
