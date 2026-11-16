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
- The Databricks App `frontline-copilot`, created with its access declared as app resources: use of the SQL warehouse, query on the chat and embedding endpoints, edit on the MLflow experiment, `SELECT` on `gold.plans`, `silver.transcripts_redacted` and the index, `MODIFY` on `ops.escalations`. Nothing on `bronze`.

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
- **CI failed on Python 3.11 only, once it ran.** One test failed with "pyarrow requires NumPy 2.0 or newer, found 1.26.4". On 3.11 pip resolves `databricks-connect` to 16.x, which requires NumPy below 2, next to the newest pyarrow, which needs NumPy 2 and does not declare it. pyarrow is now capped below 20 on Python 3.11. A local Python 3.11 container was no help: its pip spent 42 minutes resolving and never finished. CI now writes the resolved versions as a notice on each run, which is how the cause was confirmed.

**Worth knowing**

- The routing rules were written with the five hand-off rows in view. 5/5 on those rows is not an independent measure.
- In the 40-row run the judge again marked two answers incorrect that contain every expected fact.
- Tool calling on the answering model is documented by Databricks as tuned for a single step. Multi-step use worked in every case tried, which is a small sample.

**Not done**

- The app is deployed on Databricks Apps and starts there. Nobody has yet opened the deployed page signed in and asked it a question, so its sign-in as a service principal and its access to the index are unconfirmed in use.
- The MCP server was called by an MCP client over stdio against the live workspace, and its Docker image was built and answered over HTTP. It has not been registered with Claude Code itself, and its tools were not called inside the container.
- No demo video. No `eval.yml` gate. No hand check of the judge.

**For me to review**

- The three new documents in `docs/`, which state what the system does and does not do in my name.
- The README's reading of the results.
- `tests/test_chunking.py` is still mine to write with Copilot.

**M4 acceptance** (PLAN.md §12): all four tools working, the hand-off path, input and output guards, routing tests passing, the default setting evaluated on all 40 rows. All met.

**M5 acceptance** (PLAN.md §12): Streamlit app deployed as a Databricks App; MCP server working from Claude Code over stdio and in Docker. Mostly met: the app is deployed and starts, the MCP server works over stdio from a client and starts in Docker. Still open: a signed-in check of the deployed app, and registering the server with Claude Code itself. See "Not done".

## 2026-11-15 — The web interface, its deployment and a public demo

**Tool:** Claude Code.

**Asked:** replace the Streamlit page with a designed web interface, off Streamlit, with its own colours and icons and not a default look; mock several directions and choose; give the copilot a name; compare typefaces and choose; review spacing and motion as a final pass; then deploy it and host it where people can see it. This reverses the instruction recorded in the entry above ("keep Streamlit, add no REST API or JavaScript front end"). That instruction put the milestones first. With them done, the interface was reopened.

**What it built**

- `api/main.py`: a REST API (FastAPI) over the same `copilot.agent` and `copilot.tools` code the evaluation calls. It also serves the built front end. `src/copilot/steps.py` turns an answer into the list of steps the interface draws.
- `web/`: the front end, in React, TypeScript, Vite and Tailwind. Two views, Ask and Calls. A mock mode answers from fixtures with no server, and a component gallery draws every component in every state from the real component code.
- `web/DESIGN.md`: the design rules as written rules: colour tokens, type, spacing, shape, motion, states. `web/scripts/check-contrast.mjs` checks every colour pair in use against WCAG in both themes and is part of `npm run lint`.
- `design/`: the mockups that were compared and the reasons for each choice.
- `setup/deploy_app.py`: the deployment to Databricks Apps. `app.yaml` now runs `uvicorn api.main:app`.
- `.github/workflows/pages.yml`: publishes the mock build to GitHub Pages. CI has a `web` job (type check, lint with the contrast check, build).
- Removed: `app/app.py`, `.streamlit/`, and the `streamlit` dependency.

**Decisions**

- **One interface.** The Streamlit page was removed, not kept beside the new one. Two interfaces would have meant two things to keep correct.
- **The API is a thin layer.** Every endpoint calls the code the evaluation measured, so the interface cannot show something that was not evaluated.
- **The direction, "Signal and Script".** Three directions were mocked and one chosen: cobalt on cool neutrals, a midnight-navy dark theme, a highlighter that marks only the facts an agent says out loud, a cut corner that marks only what the copilot wrote, and status shown by shape as well as colour. No decorative gradients and no shadows on cards.
- **The mark.** Twelve candidates in three families, five finalists tried in use, one chosen ("Aside") and refined in three passes. It has not been checked against registered trademarks.
- **The name.** In the interface the copilot is called Cue. The project, the repository and the Python package keep the name Frontline Copilot.
- **The type.** Eight sets were compared on real pieces of the interface, then the three jobs separately. Schibsted Grotesk for headings. Atkinson Hyperlegible Next and Mono were kept for reading and data: of the faces compared, only that one separates every look-alike character, which matters when an agent reads a phone number aloud. Its zero is always slashed; that cost was accepted.
- **The public demo is the mock build.** The Databricks app needs a workspace sign-in, and Free Edition stops it after 24 hours. A public page that called the real agent would also put the workspace's daily quota in anyone's hands. The Pages site calls no server and says "Mock mode" in its top bar.
- **The built front end is not committed.** The deploy script builds it and uploads it. It always builds first, because a mock build lands in the same folder.

**Docs that differed from the plan**

- The plan's `app.yaml` command was for Streamlit. For a FastAPI app the Databricks Apps docs (read 2026-11-15) list `UVICORN_HOST` and `UVICORN_PORT` among the variables the platform sets, so the command is `uvicorn api.main:app` with no host or port. Sources: [Databricks Apps environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env), [app runtime configuration](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime), [deploy an app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy). PLAN.md section 8.1 was rewritten.

**Things that went wrong on the way**

- **The first deployment was refused.** Free Edition had stopped the app, and a stopped app cannot be deployed to. The script now starts it first.
- **The second was refused too.** Starting a stopped app deploys the source folder by itself, and a second deployment cannot begin while one is in progress. The script now treats the start as the deployment and waits for it.
- **Two motion bugs survived until the final review.** Switching to Calls and back replayed the entrance animation of the whole conversation, and on a change of theme the buttons changed colour a moment after the page. Both were found by sampling the running page, not by looking at pictures.
- **Still pictures misled twice.** Headless screenshots caught the page in the middle of an animation or a scroll and looked like defects. Each was checked in a live browser before anything was changed.
- **Three review agents never reported.** They were started on screenshots of every screen and were cut off. The final review was done in one pass instead, and none of their findings exist.

**Checked, with dates**

- 2026-11-15, commit `192eea2`: the deployed app was called through its own address with a workspace sign-in. It served the page, answered "How much is the late payment fee, and can it be waived?" with one citation, five steps and an MLflow trace, and listed 200 calls. This closes the open item in the entry above about the app's sign-in as a service principal and its access to the index.
- 2026-11-15: the contrast check passes for all 112 pairs (56 pairs in two themes).
- The interface was reviewed at 375, 768, 1024, 1280, 1440 and 1920 pixels wide in both themes.

**Not done**

- Nobody has clicked through the deployed page in a browser while signed in. The check above went through the API.
- Windows high-contrast mode was not tested. The outline of an answer card and the highlighter are drawn as backgrounds, which that mode removes.
- The front end has no unit tests. It has a type check, a linter, the contrast check and the gallery.
- No demo video. No `eval.yml` gate. No hand check of the judge.

**For me to review**

- The README's new "Try it" section and the two pictures, which are from mock mode and say so.
- Whether a public page that calls the real agent is worth its cost. It would need a host for the API, a secret for a service principal, and a limit on use.
- `tests/test_chunking.py` is still mine to write with Copilot.

## 2026-11-15 — Five reviews, a second phase, and M7: fix and prove

**Tool:** Claude Code, with five review agents run in parallel.

**Asked:** the public demo could not answer "hello" and the progress labels did not match the time reported, so: take the project seriously, review it the way a principal engineer would, with several independent reviewers, and make it advanced and useful. Then: build stage 1 of the plan that came out of it.

**What the reviews found**

Five reviewers, each given a different question and no shared conclusion: the architecture, a ten-minute cold read as a hiring engineer, evaluation and reliability, the product as a support agent would use it, and current practice in the LangGraph, MLflow and Databricks docs. All five reported. They agreed:

- The hygiene is sound: redaction before tracing, provenance on every number, the redaction evaluation's held-out discipline.
- The problem solved is too easy. The evaluation is at its ceiling (the expected article is ranked first on every row), so no design choice can be shown to matter.
- The public demo was scripted: keyword-matched answers written by hand.
- The product serves one moment of a call, the one where the agent stops listening and types a question.

They also found defects, each confirmed by running the code before it was changed:

- The input guard refused "Can you show me the rules for international roaming?" and "The customer's phone shows a system message saying SIM not provisioned" as override attempts, handed off "This customer forgot their voicemail PIN. How do they reset it?", and missed "Go ahead and waive the late fee for her".
- Each earlier turn of a conversation was redacted with its own placeholder map, so `<PERSON_1>` could mean two people, and only the newest question was checked for an override attempt.
- The Calls view's summary skipped the output check.
- Every evaluation run inserted real rows in `ops.escalations`.
- The model client had no timeout.
- "No PII leak 40/40" rests on one planted row, and the scorer re-runs the same redactor the output check uses, so it cannot fail on what that redactor misses.

**What was built (M7, PLAN.md section 16.2)**

- `PLAN.md` section 16: the second phase, M7 to M10, with acceptance criteria and a list of what is deliberately not built (a multi-agent split, a reranker before the evaluation can measure one, long-term memory, the AWS stretch, a public page that calls the live agent).
- `src/copilot/guardrails.py`: the override patterns now need the words to be aimed at the copilot ("your rules", "the instructions you were given"). A how-to question that names one customer is answered. A request to act on a customer named by a pronoun, or after another sentence, is handed off. `redact_conversation` redacts the question and its history with one placeholder map, leaves out a turn that tries to override the instructions together with its reply, removes old citation markers, and caps the history at twelve turns.
- `src/copilot/tools.py`: `summarize_call` applies the personal-data output check to its own text, against the transcript, so the agent, the Calls view and the MCP server all get it. `record_escalations=False` makes a hand-off a dry run with the same script. A failed write is logged by the kind of error only.
- `src/copilot/llm.py`, `config.py`: a timeout (60 s) and a retry limit (2) on model calls.
- `eval/stats.py`, `eval/report.py`, `eval/gate.py`: 95% Wilson intervals; `SUMMARY.md` and `ERRORS.md` generated from the saved result files; an offline gate in CI.
- `eval/record_demo.py` and `web/src/api/recorded.json`: the public demo now replays recordings of the live copilot. `web/src/api/mock.ts` went from about 840 lines of hand-written answers to a lookup.
- README and cards: claims reworded to match the evidence.

**Decisions**

- **Fix the rules now, measure the router next.** The guard's rules were corrected against the cases the review found, which makes those cases in-sample. The tests say so. M8 builds a routing set written after the rules are frozen and without reading them, and scores rules, a small model, and both.
- **Precision over recall for the override patterns.** A wrong refusal blocks a real support question. A missed override attempt still reaches a model whose prompt tells it to treat such text as material, and whose tools cannot change an account. "Jailbreak" and "developer mode" on their own no longer trigger a refusal, because customers ask about both.
- **History is the caller's text, not the copilot's.** The API is stateless, so "assistant" turns arrive from the browser and cannot be trusted as the copilot's words. They are redacted and checked like the question. Server-side conversation state arrives with the checkpointer in M9.
- **Dry-run hand-offs keep the real script.** An evaluation run must not write tickets, but the answer it scores should be the answer an agent would see. So a dry run returns the script of a written ticket, with `recorded` false.
- **Generated reports, not appended ones.** `SUMMARY.md` was appended to one row at a time and its older rows had 16 cells under a 20-column header. It is now rebuilt from the JSON files, and CI fails if it is out of date.
- **Old result files are not rewritten.** Intervals for past runs are computed when the report is built. The JSON files are records.
- **The gate fails on a stale run.** A changed evaluation set or prompt version with no new saved run fails CI. The price is that M8's new evaluation set has to land together with its first saved run.
- **The demo replays, and matches exactly.** A typed question finds a recording only if its letters and digits match. A near match would show the answer to a different question as if it were the answer to this one. Anything else gets a note that is marked as coming from the page.
- **A recording has no trace id.** A visitor cannot open the workspace's traces, and a rating on a replay would be a rating of nothing. So the demo shows no rating buttons.
- **Recorded times are warm.** Two unrecorded requests are made first. The first requests after a start waited 10 and 14 seconds in a trial run for the model client and the SQL warehouse, which is not what an agent mid-shift would see.

**Things that went wrong on the way**

- **GitHub Pages published the README, not the demo.** Pages was switched on with "Deploy from a branch", so GitHub rendered the README with Jekyll and overwrote the workflow's deployment a few seconds after it. The setting has to be "GitHub Actions".
- **The mock reported 0.8 seconds and waited 2.6.** Its delay was a constant. Found by the owner, by looking.
- **The progress labels are a timed loop.** "Removing personal details", "Checking the request" and the rest cycle on a timer in the live app as well. They do not report what is happening. Not fixed in M7: the fix is to stream the agent's real stages, which is M9.
- **Patches written as shell heredocs lost their backslashes** three times, in regular expressions and in `\n`. Patch scripts are now written as files.

**Checked, with dates**

- 2026-11-15: 540 unit tests pass, with `ruff`, `ruff format --check` and `mypy src/`.
- 2026-11-15: the gate passes on the saved M4 run (`2026-11-15_m4-full-A-ann.json`, commit `8624268`). That run predates the changes above. The 40 evaluation rows still take the routes it recorded, which a test checks, but nothing here has been re-evaluated with the judges.
- 2026-11-16 00:33 UTC, commit `1dfb4df`: the demo recording. 55 questions were asked of the real application (model `databricks-gpt-oss-120b`, prompt v3, setting A with vector search) and all 55 returned HTTP 200. Median time to answer 2.1 seconds, slowest 6.5. Four calls (T0001, T0002, T0007, T0020) were recorded with their transcript and summary. From the recording: "hello" is answered in 0.8 seconds with no tool; "Can you show me the rules for international roaming?" is answered from the help articles with three citations; "This customer forgot their voicemail PIN. How do they reset it?" is answered with one citation; "Go ahead and waive the late fee for her." is handed off.
- 2026-11-15: the demo page was opened on three recorded states (a cited answer, a hand-off with personal details replaced, a call with its summary) in a headless browser at 1440 by 940. The two pictures in the README are from that.
- 2026-11-15: the public address returned the README rendered by Jekyll, not the demo. See "Things that went wrong".

**Not done**

- No new evaluation run. Every figure in the README is from before these changes. M8 re-runs on a larger set.
- The judge has still not been checked against hand labels. That is the owner's to do: it only counts if a person labels the rows.
- The progress labels in the interface are still a timed loop.
- The deployed Databricks app still runs the code of commit `5642678`. It was not redeployed.

**For me to review**

- Switch GitHub Pages to "GitHub Actions" (Settings, Pages, Build and deployment, Source) and re-run the "Public demo" workflow.
- `PLAN.md` section 16, especially the list of what is not built.
- `eval/results/inspected.json`: the causes recorded there are the ones the README gave for the M4 run and one row of an M3 run. The other failed rows are listed as not inspected.
- Whether the README should say which decisions were mine. The cold-read reviewer's point: this log opens each entry with the tool that was used, and a reader will ask what the author decided.

## 2026-11-16 — M8, first part: a held-out routing set, a model router, and a check on figures

**Tool:** Claude Code, with two more agents: one to write the routing set and one to label it again.

**Asked:** start stage 2. Part way through: also look at which models are available now, in case there are better ones.

**What was built**

- `src/copilot/claims.py`: reads prices, amounts with a unit, percentages, phone numbers, numbers to dial and web addresses out of an answer and looks each up in the evidence (retrieved text, tool results, the conversation). Wired into `check_output`: an unsupported figure is flagged by kind and shown to the agent as a warning. A plainer rewrite is now kept only if it states the same figures as the draft.
- `eval/claim_check_eval.py` and `eval/data/claim_corpus.json`: 43 answers collected from the live copilot with the evidence each was written from, and a mutation test over them.
- `eval/routing_set.jsonl` and `eval/routing_labels_second.jsonl`: 150 messages and a second, blind labelling.
- `src/copilot/router.py`: a small model routes a message from the policy in words. `eval/routing_eval.py` scores a router, a model, or the whole copilot on the set.
- `src/copilot/agent.py`: the agent now routes with the rules for a clear account request, then the router, then the rules again if the router fails. `config/settings.yaml` sets `router: model` and `router_endpoint: databricks-llama-4-maverick`.

**Results** (all in `eval/results`, each with its commit)

- Check on figures, corpus of 2026-11-16 at `7f8961d`: 0 of 76 real figures reported; 170 of 194 changed figures caught. All 24 misses are prices and amounts whose changed value also appears elsewhere in the evidence.
- Routing, 133 clear messages, first contact for everything:
  - rules alone 67 right; 34 of 45 hand-off requests and 29 of 37 override attempts missed
  - the copilot before (rules, then the main model) 95 right; the main model opened 28 of the 34 hand-offs the rules missed
  - `llama-4-maverick` 133, `qwen3-next-80b-a3b-instruct` 132, `gpt-oss-20b` 130, `gemma-3-12b` 124, `llama-3.1-8b-instruct` 117
  - the copilot now 129 right, at commit `57c8092`
- Annotators agree on 146 of 150 (Cohen's kappa 0.96). All four disagreements are on messages the writer had marked borderline.
- The public demo was recorded again on 2026-11-16 at 02:04 UTC, commit `2744452`, with the router on: 59 questions, all answered, median 2.3 seconds, slowest 5.1. Four of them are phrasings no rule was written for ("pls cancel his line" is handed off in 0.5 seconds; a question that quotes a scam text is answered). In one of the 59 the router was rate-limited and the rules decided, and the recording shows that step as it happened. Both README pictures were retaken from it.

**Decisions**

- **I wrote the rules, so I did not write their test.** An independent agent wrote the set from the policy in words and was not allowed to open the rules, their tests, the evaluation set or the docs. I did not read the messages before the first results were saved, and wrote the router's prompt without them.
- **Borderline messages are scored apart.** The writer flagged 17 where a careful person could defend two labels. The headline is the other 133, on which both annotators agree.
- **The rules stay, for hand-offs only.** "Rules, then the model" scored lower than the model alone (127 against 130 with `gpt-oss-20b`), because the rules refused three questions and two of them only quoted a scam message. The rules' hand-off matches were right 11 times out of 11 and cost nothing, so those are kept in front of the router.
- **The rules are the fallback.** If the router is slow, rate-limited or unreadable, the rules decide and the answer carries a notice. A request must never fail because routing failed.
- **`llama-4-maverick`, not the first model that looked good.** `gpt-oss-20b` was scored first and got 130. The owner asked whether better models existed. Four more were scored with the same prompt; one got all 133 and is slightly faster.
- **The check on figures warns and does not block.** It reported none of 76 real figures, but 76 is too few to let it stop an answer.
- **A figure may come from the conversation.** The evidence includes the question and earlier turns, so an answer may repeat a price the agent typed. It does not include the system prompt.

**Docs checked**

- Databricks supported-models page (updated 2026-11-13) and function-calling page (updated 2026-11-11). The docs list about 70 hosted models. This Free Edition workspace lists eight chat endpoints, and `databricks-glm-5-3`, `databricks-deepseek-v4-1-flash-1017` and `databricks-kimi-k3` each returned `ENDPOINT_NOT_FOUND` when called once on 2026-11-15.
- The function-calling page lists all eight as supporting tool calls, says parallel tool calls are not supported, and says function calling is "optimized for single turn".

**Things that went wrong on the way**

- **The first end-to-end run was lost.** It ran the copilot on all 150 messages, hit a rate limit on the main model at message 55 after two retries, and had saved nothing. It was rerun with eight retries. The runner should save as it goes.
- **A unit test reached the real router.** With `router: model` as the default, one test that builds a copilot from default settings called the live endpoint. It passed, because the fallback works, and was only noticed because the suite got slower.
- **`qwen35-122b-a10b` could not be scored.** Its reply arrives as one string holding a JSON list of reasoning and text blocks, and at 600 output tokens it stops while still reasoning. `message_text` now reads that form, but the router's token limit was not raised for one model.
- **The router was rate-limited three times in 150 back-to-back messages.** The fallback took over each time, and those are three of the copilot's four misses.
- **Three more patches lost their backslashes in shell heredocs**, and one of them truncated a test file, which was restored from git.

**Not done**

- The 40-row evaluation has not been re-run with the router on. Its figures in the README are from before.
- How many override attempts the main model declined on its own, before the router, was not measured. The run recorded the route, not the reply.
- The 300-row evaluation set, the judge against hand labels, abstention, tokens per answer.
- The deployed Databricks app still runs commit `5642678`. Its resources do not yet include the router's endpoint. `setup/deploy_app.py` now lists it and updates an existing app's resources before deploying, but that update has not been run against the workspace yet. Until it is, the deployed app would fall back to the rules on every message.

**For me to review**

- `eval/routing_set.jsonl`, especially the 17 borderline messages and the four the annotators disagree on (R024, R056, R084, R118). Your label settles those.
- Whether 0.8 seconds on most messages is a price worth paying for the routing. `router: rules` in `config/settings.yaml` turns it off.
- `databricks-llama-4-maverick` as the router. It is under the Llama 4 Community License.

## 2026-11-16 — M9, first part: the interface shows what the copilot is really doing

**Tool:** Claude Code.

**Asked:** (on 2026-11-15, looking at the demo) "why does it say removing personal details and then that's taking way more than 0.8 seconds". The labels were a timed loop: four stage names cycled every 1.8 seconds, in the live app as well as the demo, whatever the copilot was doing.

**What was built**

- `src/copilot/agent.py`: `run` takes an optional `on_stage` listener. Each node of the graph tells it what is starting: redaction, the request check, the first model call, each tool by name, writing the answer, a rewrite, the output check.
- `api/main.py`: `POST /api/ask/stream` sends those as server-sent events, each with the seconds since the request began, then one `answer` event with the body `/api/ask` returns, or one `error` event.
- `web/`: the client reads the stream, the conversation keeps the latest stage on the pending answer, and the working card shows its words. A server without the endpoint is asked the ordinary way.
- `eval/record_demo.py` records the stages with their times, and the demo replays them.

**Decisions**

- **A listener, not LangGraph's stream.** The plan said `astream`. The answer has to be worked out on one thread for its MLflow trace to stay whole, and FastAPI runs a streaming generator's steps on different worker threads. So the copilot runs on one thread and hands events to the response through a queue. It also keeps `run` as the one entry point the app, the evaluation and the tests share.
- **An event is a stage name and fixed words.** It carries no question, no answer and nothing a tool returned, so there is nothing in the stream to redact, and a test checks that.
- **A failing listener costs nothing.** A closed connection must not lose an answer that is already being worked out.
- **The answer never depends on the stream.** If the endpoint is missing, the client falls back to `/api/ask`.
- **"Working on it" until the server speaks.** The card no longer names a stage it has not been told about.

**Checked, with dates**

- 2026-11-15, against the live workspace, API run from this branch: five questions over the stream. Stages arrived as they started. For "Which plans cost $25 a month or less?": request check at 0.01 s, first model call at 0.84 s, the plan catalogue at 1.52 s, writing at 3.64 s, the answer at 4.18 s, with a trace.
- 2026-11-15, the built page served by that API, driven in a browser: the working card showed "Removing personal details", "Checking the request", "Working out what to look up", "Looking up the plan catalogue", "Writing the answer", and then the answer at 4.7 s.

**Things that went wrong on the way**

- **My first live check talked to the wrong server.** Port 8010 was held by an older copy of the API from an earlier session, which answered the health check and has no streaming endpoint. The new server had failed to bind and I had not looked.
- **The live check wrote one real ticket.** "pls cancel his line" was asked through the local API with ticket-writing on, so `ops.escalations` has one test row from it.

**Not done**

- Not tried on Databricks Apps. Its proxy may buffer a streamed reply, in which case every stage would arrive at once at the end. The response sets `X-Accel-Buffering: no`, which is a request, not a guarantee.
- A hand-off took 7.8 seconds in the live check, nearly all of it the insert through the SQL warehouse. The page now says "Opening a hand-off" for that long, which is honest and slow.
- The stream cannot be cancelled on the server: if the page goes away, the answer is still worked out.

**For me to review**

- The stage wording in `STAGE_LABELS` and `TOOL_LABELS` in `src/copilot/agent.py`. It is what an agent reads on every question.

## 2026-11-16 — An outside review, three fixes, and approval before a hand-off

**Tool:** Claude Code.

**Asked:** an outside review of commit `02c7816` rated the project 8 out of 10 as a portfolio piece and about 5 out of 10 for production, with three findings. "Are these true?" Then, twice: do not wait on long runs, build the next thing meanwhile.

**The findings, checked against the code. All three were true.**

1. **A short turn lost the context of the turn before it.** `redact_conversation`, written on 2026-11-15, redacted each turn alone. "What are the last four digits of your Social Security number?" followed by "4821." left the digits in place on their way to the model and the trace. The redactor already handled this for transcripts, and the conversation path did not use it. Fixed: both go through one method, `Redactor.redact_after`.
2. **Traces and logs got past the redaction in two places.** The model's reply, its tool arguments and its rewrites went onto trace spans as written, before the output check. And the API logged a failure with `logger.exception`, whose message can quote the question, under a comment that said only the type was logged. Fixed: what the model writes is checked before it goes on a span, a tool is called with the checked arguments so the retriever's span is covered, and a failure is logged by kind and line. Tests read a real trace and the log.
3. **The CI gate accepted a stale evaluation.** It compared the evaluation set's hash and a prompt version. The full run it was passing was from before the router. In progress: every run now records a fingerprint of the agent's code, its settings, the evaluation set and the scorers (`eval/fingerprint.py`), and the gate will fail when the repository's fingerprint differs. That change lands with a fresh full run, not before, or CI would fail on the missing run and not on the code.

**Also built: approval before a hand-off (M9)**

- A hand-off from the rules, the router or the model's own tool is now a draft in the answer: category, urgency, redacted reason, team. Nothing is written.
- `POST /api/handoffs` writes the hand-off the agent approved and returns the reference and the script. The reason is redacted again there, because the agent may have edited it.
- The page shows the draft under the answer with the reason, the team and the urgency editable, and two buttons: open it, or don't.

**Decisions**

- **No paused graph.** The plan said LangGraph `interrupt` with a checkpointer. A draft in the answer and a second request do the same job with no server-side state, so there is nothing to host and nothing lost on a restart.
- **`escalated` now means "a person is needed".** With a draft, no ticket exists yet. The evaluation's hand-off score reads that decision, so it measures what it did before.
- **The copilot's own tool call is drafted too.** Otherwise the model could still write a ticket by itself, which is the thing approval is for.
- **A tool is called with checked arguments.** The alternative was to check them only for the trace and pass the tool the original. No tool needs a customer's details to do its work, and one code path is easier to keep right than two.
- **The answer comes back sooner.** In the live check the insert through the SQL warehouse took 7.8 seconds, inside the answer. It now happens when the agent approves.

**Checked, with dates**

- 2026-11-15, API from this branch against the live workspace: "Refund the $5 late fee on this customer's account. Her number is 480-555-0132." returned a billing draft with the number replaced, in 2.1 seconds, and wrote nothing. "she is moving abroad and wants the line shut off for good, pls sort", which no rule matches, returned a cancellation draft through the router. Approving the second, with a phone number added to the reason by hand, wrote ticket `ESC-29123CC9` with that number replaced; the row was read back from `ops.escalations`.
- 2026-11-15, the built page in a browser: the draft card appeared, "Open the hand-off" returned `ESC-07305294` and the script.
- 639 unit tests pass.

**Not done**

- The stricter gate is written and not applied. It needs a fresh full evaluation of the current code first.
- These changes are on a branch. The 40-row evaluation has not been run on them.
- `ops.escalations` has three rows from these live checks (`ESC-29123CC9`, `ESC-07305294`, and one from the streaming check). They are test tickets.

**For me to review**

- The wording on the draft card (`web/src/features/ask/HandOffDraftCard.tsx`), and the six team names in it.
- Whether a declined hand-off should be recorded anywhere. Today it leaves no trace.

## 2026-11-16 — Five models compared as the one that answers

**Tool:** Claude Code.

**Asked:** "also research latest models, there might be updated and better ones too now", then "yes, compare them".

**What was done**

- `eval/run_eval.py` takes `--llm-endpoint` and `--judges`. `eval/scorers.py` gains `figures_supported`. The CI gate reads only runs that every judge scored, so a comparison cannot stand in for an evaluation. `SUMMARY.md` names the model and the router of each run.
- Five runs of the 40 questions, one per model, with the router on, two judges, at commit `8478690`.

**Results** (from `eval/results/*_models-*.json`)

| Answering model | Correct | Rules followed | Right tool | Source cited | Reading level ok | Figures in sources | Reading grade | Median time | 95th percentile |
|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-120b` | 25/31 (63-91%) | 10/11 (62-99%) | 35/37 (82-99%) | 21/22 (78-100%) | 38/40 (83-99%) | 40/40 (91-100%) | 5.6 | 3.8 s | 5.3 s |
| `llama-4-maverick` | 23/31 (56-87%) | 9/11 (52-95%) | 33/37 (75-96%) | 18/22 (61-93%) | 34/40 (70-93%) | 40/40 (91-100%) | 7.5 | 4.9 s | 6.8 s |
| `qwen3-next-80b-a3b-instruct` | 23/31 (56-87%) | 9/11 (52-95%) | 31/37 (68-93%) | 16/22 (51-87%) | 37/40 (80-98%) | 39/40 (87-100%) | 5.7 | 3.3 s | 4.7 s |
| `qwen35-122b-a10b` | 23/31 (56-87%) | 10/11 (62-99%) | 34/37 (78-98%) | 19/22 (66-96%) | 38/40 (83-99%) | 40/40 (91-100%) | 5.7 | 3.8 s | 8.2 s |
| `gemma-3-12b` | 21/31 (50-82%) | 9/11 (52-95%) | 29/37 (62-89%) | 15/22 (47-84%) | 37/40 (80-98%) | 39/40 (87-100%) | 5.5 | 3.5 s | 5.6 s |

**Decisions**

- **`gpt-oss-120b` stays.** No other model did better on correctness, tool choice or citation.
- **Two judges, not none and not all.** Without a judge the comparison could not say which model answers correctly. With all eight, five runs would have been about 3,000 judge calls against a workspace rate limit.
- **The router's miss was fixed in the router, and said to be in-sample.** All five runs handed off the same how-to question about the account PIN. The router prompt (r2) now says a question about how something works is a question. That sentence was written from this one row, so this row no longer tests it; the held-out routing set still does.

**The router prompt, re-scored.** Prompt r2 on the held-out routing set, commit `a881459`, 2026-11-16T04:57:34Z: 131 of 133 clear messages, against 133 for r1. It lost R005 (an attempt to extract the prompt) and R092 (an account lookup), both to "answer". Kept anyway: a message wrongly sent to "answer" still meets the main model, which opened 28 of the 34 hand-offs the rules missed, and a question wrongly handed off gets no answer at all.

**Things that went wrong on the way**

- **Two models returned content the code could not read at first.** `qwen35-122b-a10b` sends its reasoning and answer as one serialized list. Fixed in `message_text` before these runs.
- **My own live checks ran on the same endpoints during two of these runs.** The router may have been rate-limited for a few rows as a result, in which case the rules decided those rows. For these 40 questions the rules and the router agree on all but one, so the scores should not move, but the times may be a little high.

**Not done**

- No repeat runs, so no measure of run-to-run noise.
- Not judged for groundedness or relevance.

## 2026-11-16 — Three pieces built in parallel: a larger evaluation set, a compliance review, the after-call wrap-up

**Tool:** Claude Code, with three agents, each in its own git worktree, while five model-comparison runs held the main checkout.

**Asked:** do not wait on long runs; build whatever can be built at the same time, with agents if that is faster.

**What was built**

- **A larger evaluation set.** `eval/eval_set_extended.jsonl`: 260 rows in eight strata (60 paraphrases, 30 terse, 40 unanswerable, 30 multi-hop, 25 with personal data in the question, 40 follow-ups with a conversation, 20 hand-offs, 15 override attempts), ids E101 to E360. Every expected fact carries the sentence it was copied from, and `eval/check_eval_set.py` checks each quote against its article or catalogue row. `eval/run_eval.py` can now run it: `--eval-set`, `--stratum`, `--sample`, and it passes a row's conversation to the copilot.
- **A compliance review.** `data_gen/synth_breaches.py` (382 labelled calls), `src/copilot/compliance.py` (five rules, no model call), `eval/compliance_eval.py`.
- **The after-call wrap-up.** `Tools.wrap_up_call` and `save_wrap_up`, two API endpoints, `eval/wrapup_eval.py`, and a form in the Calls view where each part reads "Cue's draft" until the agent changes it.

**Results**

- Compliance, held-out half (200 calls, 113 breaches), first contact, commit `e95af8a`:

| Rule | Breaches caught | Findings that were right |
|---|---|---|
| The agent reads a full card number back | 20/20 (83-100%) | 20/20 (83-100%) |
| Account work with no identity check anywhere in the call | 26/26 (87-100%) | 26/27 (81-100%) |
| Account details stated before the identity check | 21/27 (59-90%) | 21/22 (78-100%) |
| The agent says they have waived or refunded a charge themselves | 15/20 (53-89%) | 15/16 (71-99%) |
| The agent asks for the full Social Security number | 14/20 (48-86%) | 14/16 (63-97%) |

- Compliance, the 200 original calls: 0 of 200 flagged.
- Wrap-up: a five-call trial against the live model on 2026-11-15 ran clean (4 of 5 dispositions and 5 of 5 categories matched the labels). Five calls show that the path works and nothing more. The 200-call measurement had not been run when this was written.
- The larger set: not run yet.

**Decisions**

- **Each agent got its own worktree and a list of files it must not touch.** The evaluation runs save only from a clean checkout, so nothing could be written into the main one for an hour and a half.
- **Rows of the larger set are marked unreviewed.** The plan says a person reviews every row. The evidence quotes make that fast, but it has not happened, so results on this set will say "0 of 260 reviewed", and the CI gate does not read them.
- **The compliance rules were kept as measured.** The 22 held-out errors were read after the result was saved, and fixing them now would turn the held-out half into a second development half.
- **The wrap-up prompt is not told the answer.** The summary prompt is given the call's recorded category and outcome. The wrap-up's lookup does not select them, and a test checks the prompt for both.
- **The wrap-up is saved by the agent, like a hand-off.** The copilot drafts; a person approves; only then is a row written.

**Things that went wrong on the way**

- **The agents' worktrees made the main checkout look dirty.** They are created under `.claude/`, which showed as untracked, and the next evaluation run would have refused to start. `.claude/` is now in `.git/info/exclude`.
- **The compliance held-out half is not perfectly blind.** Its writer's summary named a few phrasings before the rules were finished. The agent kept those phrases out of the rules and says so; four of the six missed Social Security requests are exactly those phrases.
- **The redactor leaves some account figures in plain text.** The compliance work found amounts and usage with no cue word nearby that were not replaced ("$33.62 still outstanding", "16.5 gigs"). That is a redaction gap, recorded here and not yet fixed.
- **A wrap-up line came back with a non-breaking hyphen** ("3-5 days"). Lines are now brought to plain punctuation. That fix has unit tests and has not been re-run live.

**Checked, with dates**

- 2026-11-15: `ops.call_wrapups` was created in the workspace from `setup/00_setup.sql`, and the insert's `from_json` form returned the two lists it was given.
- 2026-11-15: seed 42 still produces byte-identical transcripts. A test pins both hashes.
- 889 unit tests pass on the merged code.

**Not done**

- No row has been saved to `ops.call_wrapups` through the app. The insert has run on a warehouse only as the `from_json` check above.
- A saved wrap-up is not read back: after a reload the app does not know a call was wrapped up.
- The compliance checker is not shown anywhere in the interface.
- The larger set has not been run, and nobody has reviewed its rows.

**For me to review**

- `eval/eval_set_extended.jsonl`. Each row has `evidence`; the unanswerable rows are the ones to look at hardest, because "the article leaves this detail out" is a judgement.
- The five compliance rules and their definitions at the top of `src/copilot/compliance.py`.
- The wrap-up form's wording in `web/src/features/calls/WrapUpPanel.tsx`.
