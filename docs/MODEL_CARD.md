# Model card: Frontline Copilot

A description of the system as a whole. It does not train a model; it uses hosted models and adds retrieval, tools and guardrails around them.

## What it is

An assistant for frontline support agents at a wireless carrier. The agent types a question and gets a short, plain-language answer with cited help articles, a plan lookup from the catalogue, a summary of a redacted call, or a hand-off to a human specialist.

| Part | What is used |
|---|---|
| Answering model | `databricks-gpt-oss-120b`, an open-weight model served by Databricks Foundation Model APIs. Temperature 0.1, up to 700 output tokens |
| Embeddings | `databricks-gte-large-en`, through a Delta Sync index on Databricks AI Search |
| Judge, for evaluation only | `databricks-meta-llama-3-3-70b-instruct`, a different model family from the one that answers |
| Redaction | Presidio 2.2.366 with spaCy `en_core_web_md` 3.8.0 and project-specific recognizers |
| Agent | LangGraph 1.2.22, four tools, at most 4 tool rounds per answer |
| Prompt | Version v3, in `src/copilot/prompts.py`. The version is recorded on every trace and evaluation run |
| Retrieval | Top 5 chunks, 800-token chunks with 100 overlap, vector search |

## Intended use

- Helping a support agent find and phrase an answer while they talk to a customer.
- Looking up plan prices and features from the catalogue.
- Summarizing an earlier call from its redacted transcript.
- Recognising a request that needs account access and handing it to a person.

## Out of scope

- Talking to customers directly, without an agent reading the answer first.
- Any action on an account. The system has no tool that can change one.
- Questions outside the carrier's help content and plan catalogue. It is instructed to decline them.
- Any use on real customer data. It has only been run on synthetic data.

## Data

All synthetic: 87 help articles for a fictional carrier, an 18-row plan catalogue, and 200 templated support transcripts. See the [data card](DATA_CARD.md).

## Evaluation results

Every number is from a real run, recorded with its date and git commit in [eval/results](../eval/results). The [README](../README.md) has the full tables.

**Redaction** (2026-11-12, commit `b0a26de`): on 30 labeled test transcripts, recall 1.000 (209/209) and precision 1.000 for personal data. On 50 hand-written lines the redactor was not tuned on, recall was 0.769 (30/39) on first contact and 0.923 (36/39) after fixes; the second figure is no longer held out.

**Answers, all 40 evaluation rows** (run finished 2026-11-15 00:58 UTC, commit `8624268`, prompt v3):

| Measure | Result |
|---|---|
| Correct against the expected facts | 27/31 |
| Followed the row's rules (hand-offs, refusals, no invented answer) | 11/11 |
| Hand-off opened exactly when needed | 40/40. In-sample: the rules were written with the 5 hand-off rows in view |
| Right tool used | 36/37 |
| No personal data in the answer | 40/40. One row plants personal data; the other 39 have none to leak |
| Expected help article retrieved and cited | 22/22 |
| Grounded in the retrieved text | 22/22 |
| Citations valid | 40/40 |
| Reading grade 8 or below | 37/40, mean grade 5.7 |
| Time to answer | Median 2.5 seconds, 95th percentile 4.3, slowest 13.4 |

## Known limitations and failure modes

These come from the evaluation runs and from running the system, not from speculation.

- **It can merge two nearby statements into a wrong one.** In an earlier run, an answer said the carrier "never asks for" the account PIN by phone, when support does ask for it on a call the customer makes. The article states both points close together.
- **Small chunks with vector search can miss the right article.** In one of three retrieval runs, a question about a suspicious text message did not retrieve the article on scam messages. Hybrid search retrieved it.
- **The model picks the wrong search scope if allowed to.** When the search tool offered a section filter, the model chose "Account" for a voicemail question and reported that no article existed. The filter is no longer offered to the model.
- **A call summary can leave out a key fact.** In the 40-row run the judge found one summary did not say that the customer had already typed in their card number.
- **It sometimes answers a plan question from the help articles** and not from the plan table. The one case seen was answered correctly.
- **Some answers are above the reading target.** 3 of 40 in the last run, after the one-time rewrite.
- **The redactor misses spoken forms**: phone numbers and dates said as words, email addresses spelled out, amounts written in words.
- **The judge is wrong some of the time.** In every run it marked two answers incorrect that contain every expected fact. Reported numbers are as the judge gave them. A hand check of the judge on 10 rows has not been done.
- **The hand-off rules were written with the evaluation's hand-off rows in view**, so the 5/5 on those rows is not an independent measure. Rules like these will miss phrasings nobody thought of; the model can still open a hand-off itself, and that path was not measured separately.
- **Tool calling on this model is documented as tuned for a single step.** Multi-step tool use worked in every case tried here, but that is a small sample.

## What has not been evaluated

- Real conversations, real help content, or real customers.
- Fairness across groups of customers. The data has no demographic information.
- Languages other than English.
- Behaviour under load, or cost per answer.
- Robustness to prompt injection beyond one planted example and one fixed-refusal rule.

## Ethical considerations

Covered in the [responsible-AI notes](RESPONSIBLE_AI.md): human oversight, handling of personal data and CPNI, transparency, plain language, and a mapping to the NIST AI Risk Management Framework.
