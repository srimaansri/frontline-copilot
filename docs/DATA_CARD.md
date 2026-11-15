# Data card

Everything in this project is synthetic. No real carrier, customer, call or account appears anywhere in it.

## What the data is

| Dataset | Size | How it was made | Where it lives |
|---|---|---|---|
| Help articles | 87 articles in 6 sections | Written by an open-weight model from hand-written briefs, then reviewed and corrected | `data/synthetic/kb_articles.jsonl` (committed) |
| Plan catalogue | 8 plans, 10 add-ons and fees | Written by hand | `data_gen/plans.py` |
| Support transcripts | 200 conversations | Assembled from templates by code, seed 42 | `data/raw/` (generated, not committed) |
| Redaction labels | 221 labels on 30 transcripts | Recorded by the generator as it inserts each value | `data/raw/` (generated, not committed) |
| Redaction dev set | 200 labeled transcripts | Same generator, seed 7 | `data/raw/dev/` (generated, not committed) |
| Redaction challenge set | 50 lines, 39 personal values | Written by hand, in phrasings the redactor was not tuned on | `eval/data/redaction_challenge.txt` |
| Evaluation questions | 40 rows | Drafted with a model, reviewed by two passes, then every row reviewed by hand | `eval/eval_set.jsonl` |

The carrier, "Northline Wireless", is fictional. Its web address uses the reserved `.example` domain.

## Help articles

- **Source of facts.** Every price, fee, limit and policy comes from a hand-written brief in `data_gen/kb_topics.py` or from the plan catalogue. The model wrote the prose around them.
- **Model.** `databricks-gpt-oss-120b`, on 2026-11-13. Model output is not deterministic, so the committed file is the source of truth. `python -m data_gen.synth_kb` only writes articles that are missing.
- **Checks at generation.** An article is rejected if it is too short or too long, has fewer than two sections, lacks the support contact line, contains non-ASCII characters, or quotes a dollar amount that is in neither its brief nor the catalogue.
- **Review.** Two review passes read all 87 articles, one for contradictions between articles and one against each article's brief. That produced 170 corrections in 68 articles (41 high, 55 medium, 74 low severity). Each is recorded with its reason in `data/synthetic/kb_corrections.jsonl`, and a test keeps that record and the metadata in step.
- **No scraped text.** A scraper exists (`data_gen/scrape_kb.py`) and was not used. No article text from a real carrier is in the repository.

## Transcripts and personal data

Transcripts are built from templates by code, with no language model. That choice is deliberate: because code inserts every personal value, the exact position of each one is known, so the redactor can be scored against exact labels.

Values are invented with the `faker` library and fixed formats. The types inserted are:

- **Personal data:** person name, phone number, email address, street address, date of birth, account number, IMEI, ICCID, last four digits of a Social Security number, payment card number.
- **CPNI** (see [RESPONSIBLE_AI.md](RESPONSIBLE_AI.md)): bill amounts and usage figures. Numbers a customer called are phone numbers and are covered by that type.

Payment card numbers are generated to pass the Luhn check so the card recognizer is tested on realistic input. They are not real cards.

Generation is seeded, so the same command gives the same files:

```bash
python -m data_gen.synth_transcripts --seed 42
```

## How the redaction sets are used

| Set | Purpose | Rule |
|---|---|---|
| Dev (seed 7) | Tuning the redactor | The only set the redactor may be tuned on |
| Test (seed 42, 30 labeled) | Reporting | Never tuned on. Same templates as dev, so it is an upper bound |
| Challenge (hand-written) | The number to trust | Held out at first. After it prompted fixes, the earlier result was kept and the later one is marked as no longer held out |

## Where data sits on Databricks

| Layer | Contents | Personal data |
|---|---|---|
| `raw` volume | The uploaded files | Synthetic values as written |
| `bronze` | Files as ingested | Synthetic values as written |
| `silver` | Cleaned tables, redacted transcripts | Replaced with placeholders such as `<PHONE_NUMBER_1>` |
| `gold` | Article chunks, plan catalogue, search index | None. Articles hold only the carrier's public contact details |
| `ops` | Quality checks, redaction metrics and detection positions, hand-offs | Positions and types only, never the values. Hand-off reasons are redacted before they are written |

The copilot's tools read `silver` and `gold` only. Nothing reads `bronze` at answer time.

## Evaluation questions

40 rows: 22 about help articles, 6 plan lookups, 4 call summaries, 5 requests that need a hand-off, and 3 trick questions (a prompt injection, a question containing personal data, and an off-topic request).

Each row has a question and either facts a correct answer must contain, rules it must follow, or both. The rules for writing rows, and the order in which they were reviewed, are in [PLAN.md](../PLAN.md) section 9.1.

## Limits

- Templates make transcripts more regular than real calls. Redaction scores on them say how the redactor does on these phrasings, not on real speech.
- The articles were written by the same model that answers questions about them, which may make them easier for it to read than a real help site.
- The evaluation set is small. One row is about 2.5 percent of the whole set and about 5 percent of the article questions.
- Everything is in English.

## Licence and attribution

All text was written for this project or generated for it. There is no third-party content to attribute.
