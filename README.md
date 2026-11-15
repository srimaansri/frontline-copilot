# Frontline Copilot

[![CI](https://github.com/srimaansri/frontline-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/srimaansri/frontline-copilot/actions/workflows/ci.yml)

> Unofficial demo. Not affiliated with or endorsed by any carrier. No real customer data.

An AI copilot for frontline support agents at a wireless carrier, built end to end on **Databricks Free Edition**. An agent asks a question in plain words and gets a short, plain-language answer with cited help articles, a plan lookup grounded in SQL, a summary of a redacted call transcript, or a hand-off to a human when the request needs real account access.

## Status

This repo is being built milestone by milestone. Every number here comes from a real run, with its date and git SHA, and the full reports are in [eval/results](eval/results).

| Milestone | What | State |
|---|---|---|
| M0 | Scaffold: tooling, config loader, CI | Done |
| M1 | Data generation and PII redaction, measured locally | Done |
| M2 | Databricks pipelines: bronze, silver, gold, quality checks | Done |
| M3 | Retrieval-augmented answers and the first evaluation | Done |
| M4 | Agent with tools, guardrails, escalation | |
| M5 | Streamlit app on Databricks Apps, MCP server | |
| M6 | Results, model and data cards, responsible-AI notes | |

The full specification is in [PLAN.md](PLAN.md).

## The data is synthetic

Nothing here comes from a real carrier or a real customer.

- **Knowledge base:** 87 help articles for a fictional carrier, "Northline Wireless", in [data/synthetic](data/synthetic). An open-weight model (`databricks-gpt-oss-120b`) wrote the prose on 2026-11-13. Every price, fee and policy comes from hand-written briefs in [data_gen/kb_topics.py](data_gen/kb_topics.py) and the plan catalogue, and an article is rejected if it quotes a dollar amount found in neither. Two review passes then read every article, one for contradictions between articles and one against each article's brief. That led to 170 corrections in 68 articles, each recorded with its reason in [data/synthetic/kb_corrections.jsonl](data/synthetic/kb_corrections.jsonl). The scraper in `data_gen/scrape_kb.py` exists but was not used.
- **Transcripts:** 200 support conversations assembled from templates by code, with no language model, so the position of every piece of personal data is known exactly.
- **Plans:** 8 invented plans and 10 add-ons and fees.

## The pipeline on Databricks

Five notebooks in [pipelines](pipelines) run as one serverless job, defined in [databricks.yml](databricks.yml) and [resources/frontline_pipeline.job.yml](resources/frontline_pipeline.job.yml). The logic they call lives in `src/copilot` and is installed on the cluster as a wheel. The figures below are from the run of 2026-11-14 at commit `55692f5`, on Databricks Free Edition.

| Step | What it does | Result |
|---|---|---|
| 01 Ingest | Landing volume to bronze Delta tables | 87 articles, 200 transcripts, 221 labels, 18 plan rows |
| 02 Redact | Presidio + spaCy inside Spark (`mapInPandas`), then scores itself on the labeled transcripts | 200 transcripts redacted, 1,472 values replaced. PII recall 1.000 (209/209), precision 1.000. Same as the local test-set run. |
| 03 Chunk | Heading-aware chunks into `gold.kb_chunks`, Change Data Feed on, merged by key | 87 chunks at 800/100 tokens, 168 at 350/60 |
| 04 Index | Delta Sync index on Databricks AI Search with `databricks-gte-large-en` embeddings | 255 of 255 rows indexed |
| 05 Quality checks | Keys, chunk sizes, coverage, and a scan of redacted transcripts for leftover phone numbers, emails and long digit runs | 18 of 18 checks passed, 0 leak hits |

The index step also runs 20 smoke queries (5 questions, both chunk settings, vector and hybrid search). The expected article was in the top 3 for all 20. That shows the query paths work; it is not an evaluation. Retrieval quality is measured in Milestone 3.

Every metric written to the `ops` schema carries the git commit of the code that produced it.

After the knowledge-base corrections the job was run again, on 2026-11-14 at commit `972de18`: 87 chunks at 800/100 tokens and 161 at 350/60, 248 rows indexed, and 18 of 18 quality checks passed. The evaluation below uses that index.

## Answer quality: the first evaluation

The copilot at this stage retrieves the five best chunks, answers with `databricks-gpt-oss-120b`, cites its sources, and has its citations checked. It was scored on 22 knowledge-base questions: 21 that one help article answers, and 1 that no article answers. Every question and its expected facts were reviewed by hand before the runs.

Three runs, so that each step changes one thing. All three are from 2026-11-14 at commit `1a35afb`, with prompt v2, MLflow 3.18.0 and RAGAS 0.4.4. The judge is `databricks-meta-llama-3-3-70b-instruct`, a different model family from the one that answers.

| Measure | A: 800-token chunks, vector search | B: 350-token chunks, vector search | B: 350-token chunks, hybrid search |
|---|---|---|---|
| Expected article in the top 5 | 21/21 | 20/21 | 21/21 |
| Mean reciprocal rank of that article | 0.97 | 0.95 | 0.94 |
| Share of retrieved chunks judged relevant | 0.53 | 0.64 | 0.65 |
| RAGAS context precision | 0.94 (n=20) | 0.92 (n=21) | 0.91 (n=21) |
| Retrieved text is enough to answer | 21/21 | 21/21 | 21/21 |
| Answer is grounded in the retrieved text | 21/21 | 21/21 | 21/21 |
| Answer is correct against the expected facts | 19/21 | 18/21 | 18/21 |
| The question no article answers: says so, invents nothing | 1/1 | 1/1 | 1/1 |
| Answer is relevant to the question | 22/22 | 22/22 | 22/22 |
| Citations are valid | 22/22 | 22/22 | 22/22 |
| Reading grade 8 or below | 20/22 | 19/22 | 20/22 |
| Mean reading grade (Flesch-Kincaid) | 5.4 | 5.7 | 5.8 |
| Median time to answer | 2.1 s | 2.1 s | 2.1 s |

Rates are passed/scored. The retrieval measures are scored on the 21 questions that have an article. One RAGAS call in run A was rejected by the workspace rate limit, so that cell covers 20 rows.

**What this shows**

- No setting is clearly better. With 21 questions, a difference of one row is noise, and no claim is made that one setting beats another.
- Smaller chunks made retrieval more focused: the share of retrieved chunks judged relevant rose from 0.53 to 0.64. They did not make answers more correct, because the larger chunks already held the answer for every question.
- Hybrid search found the one article that vector search over small chunks missed.
- Setting A with vector search stays the default. It has the fewest chunks to maintain and nothing here argues for a change.

**The answers marked incorrect**

Four of the eight "incorrect" marks were inspected against the answer text.

- One is a retrieval miss. With small chunks and vector search, the question about a text message asking for a PIN did not retrieve the article on scam messages, so the answer left out where to forward the message.
- One is a real mistake in the answer. It said the carrier "never asks for" the account PIN by phone, when support does ask for it on a call the customer makes. The article states both points close together and the answer merged them.
- Two are judge mistakes. The answers contain every expected fact. The judge marked them incorrect because the article lists further steps that the expected facts do not.

The table reports the marks as the judge gave them.

**Limits**

- 22 questions is a small set, and the knowledge base is synthetic and was written by the same model that answers.
- The judge is a language model and is wrong some of the time, as above. A hand check of the judge on 10 rows, with an agreement rate, has not been done yet.
- These runs cover knowledge-base questions only. Plan lookups, call summaries, hand-offs and trick questions are scored once the agent and guardrails exist (Milestone 4).
- An earlier draft run is kept in [eval/results](eval/results) for the record. It used questions that had not been reviewed and articles that had not been corrected, and the grading has changed since, so it is not comparable with the runs above.

Reproduce one run (it makes about 350 model calls and takes about 25 minutes on Free Edition; try `--limit 5` first):

```bash
python -m eval.run_eval --config A --query-type ann --tag my-run --category kb
```

## Redaction results so far

The redactor replaces personal data in support transcripts with typed placeholders such as `<PHONE_NUMBER_1>`. It is measured on synthetic transcripts whose personal values are inserted by code, so the labels are exact. All runs below are from 2026-11-12 with spaCy `en_core_web_md` 3.8.0 and Presidio 2.2.366.

| Set | What it tells you | PII recall | PII precision | CPNI recall | Commit |
|---|---|---|---|---|---|
| Test: 30 transcripts, 209 PII values | New names and numbers in phrasings the redactor was tuned on. An upper bound. | 1.000 (209/209) | 1.000 | 1.000 (12/12) | `b0a26de` |
| Challenge, first run: 50 hand-written lines, 39 PII values | Phrasings the redactor had never seen. **The number to trust.** | 0.769 (30/39) | 0.857 | 0.333 (2/6) | `ed7ad27` |
| Challenge, after fixes | The same lines after fixing the gaps they exposed. No longer held out. | 0.923 (36/39) | 0.973 | 0.667 (4/6) | `b0a26de` |

A detection counts when it overlaps the label by at least half (intersection over union) and has the right type.

What the redactor still misses: phone numbers and dates spoken as words ("four eight zero..."), email addresses spelled out loud, dollar amounts written in words, and usage figures with no cue word nearby. The first two are recorded as expected-failure tests. The sets are small and synthetic, so these figures describe this redactor on this data and are not a forecast for real calls.

Reproduce:

```bash
python -m data_gen.synth_transcripts --seed 42
```

```bash
python -m eval.redaction_eval
```

```bash
python -m eval.redaction_eval --challenge
```

## What it is built with

Unity Catalog, Delta Lake and PySpark for the data pipeline. Databricks AI Search for retrieval. An open-weight LLM served by the Databricks Foundation Model APIs. MLflow 3 for tracing and evaluation, with RAGAS. LangGraph for the agent. Presidio and spaCy for PII redaction. Streamlit on Databricks Apps for the interface, and an MCP server so other assistants can call the same tools.

## Development

Requires Python 3.11 or 3.12.

```bash
python -m venv .venv
```

Activate the environment (`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` elsewhere), then:

```bash
pip install -e ".[dev,models]"
```

`models` adds the spaCy pipeline the redactor uses by default. Without it the unit tests still run, on a smaller pipeline.

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
