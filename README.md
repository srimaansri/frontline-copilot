# Frontline Copilot

[![CI](https://github.com/srimaansri/frontline-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/srimaansri/frontline-copilot/actions/workflows/ci.yml)

> Unofficial demo. Not affiliated with or endorsed by any carrier. No real customer data.

An AI copilot for the person on the phone with a customer: a frontline support agent at a wireless carrier. Built end to end on **Databricks Free Edition**.

Answering a question from a help article is the easy part. The hard part is being safe to lean on while a customer waits. That means never repeating a customer's details to a model or a log, never stating a price the source does not hold, never changing an account or filing a ticket by itself, knowing when a person is needed, and being able to say with numbers how often each of those goes wrong. This repository is about that second part.

[![The copilot answering a billing question. The answer highlights the facts to say out loud and numbers its sources; a side rail lists its source and the five steps taken.](docs/img/cue-answer.png)](https://srimaansri.github.io/frontline-copilot/)

**See it in a browser:** <https://srimaansri.github.io/frontline-copilot/> is a public demo. The page is static and calls no server, so it cannot run the copilot: it replays recordings. Every answer in it is what the live copilot returned for that question, recorded by [eval/record_demo.py](eval/record_demo.py) with the date and the commit, which the page shows under "What's running". For a question with no recording it offers the closest recorded questions to click, and says that nothing was run. The picture above is from it. The live app, which calls the real agent, runs on Databricks Apps and needs a sign-in to the workspace; see [Try it](#try-it).

## What it does, and how well

Every figure below comes from a saved run with its date and commit, and each links to the section that gives its interval and its limits. The sets are small and the data is synthetic, so read these as what was measured, not as a forecast.

| What it does | Measured on | Result |
|---|---|---|
| [Sends each message the right way](#routing-measured-on-messages-the-rules-had-never-seen): answer it, hand it to a person, or refuse it | 133 held-out messages, written and labelled without sight of the rules | 129 of 133 right. The plain rules it started with: 67 of 133 |
| [Checks every figure in an answer](#a-check-on-every-figure-in-an-answer) against the text it was written from | 43 live answers, and 194 copies with one figure changed | 170 of 194 changed figures caught; 0 of 76 real figures wrongly reported |
| [Keeps personal data out](#redaction-results-so-far) of the model, the logs and the traces | 39 personal values in phrasings the redactor had never seen | 30 found on first contact, 36 after fixing what that showed |
| [Reviews every call](#checking-every-call-for-a-broken-rule) for five rule breaches | 200 held-out calls with seeded breaches, and the 200 clean ones | 46 of 46 for the two rules that rest on redaction; 21 of 27, 15 of 20, 14 of 20 for the three that rest on wording; 0 of 200 clean calls flagged |
| [Answers from help articles and the plan catalogue](#the-agent-all-40-questions), with its sources | 40 reviewed questions, scored by code and by an LLM judge | 25 of 31 judged correct, 21 of 22 grounded, 22 of 22 cite the right article |
| Drafts a hand-off or an after-call wrap-up and waits | The deployed app | Nothing is written until the agent approves it |
| Shows what it is doing while it works | The deployed app, through Databricks' proxy | Each stage reaches the page within 0.1 second of starting |

## The ideas that carry it

- **Redact before the trace opens.** MLflow records a traced function's inputs before its body runs, so redacting inside the trace is too late. The question and its conversation are redacted first, outside any span, and a test reads a real recorded trace for a planted phone number. What the model writes is checked again before it goes on a span.
- **Rules, then a small model, then the rules again.** Plain rules hand off a clear account request at no cost. Everything else is routed by a small model that reads the policy in words. If that model is slow or unreachable, the rules decide and the answer says so. The order came from measurement: putting the rules' refusals in front of the model made it worse.
- **The copilot drafts; a person approves.** A hand-off and a wrap-up are drafts in the answer. A ticket is someone else's work queue, and a copilot that fills it by itself on a misread request cannot be undone by the agent.
- **A number has to be able to fail.** The first evaluation sat at its ceiling and the routing score was measured on the rows the rules were written from. The fixes: sets written by someone who never saw the code, first-contact results that are kept when later ones improve, intervals on every rate, and a CI gate that fails when the code an evaluation measured has changed.
- **Say what was not done.** Each section ends with its limits, and [docs/BUILD_LOG.md](docs/BUILD_LOG.md) records what went wrong on the way, including an outside review that found three real gaps and how each was closed.

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
| 02 Redact | Presidio + spaCy inside Spark (`mapInPandas`), then scores itself on the labeled transcripts | 200 transcripts redacted, 1,472 values replaced. PII recall 1.000 (209/209), precision 1.000. Same as the local test-set run, and an upper bound: these transcripts use phrasings the redactor was tuned on. On phrasings it had not seen, recall was 0.769 ([redaction results](#redaction-results-so-far)). |
| 03 Chunk | Heading-aware chunks into `gold.kb_chunks`, Change Data Feed on, merged by key | 87 chunks at 800/100 tokens, 168 at 350/60 |
| 04 Index | Delta Sync index on Databricks AI Search with `databricks-gte-large-en` embeddings | 255 of 255 rows indexed |
| 05 Quality checks | Keys, chunk sizes, coverage, and a scan of redacted transcripts for leftover phone numbers, emails and long digit runs | 18 of 18 checks passed, 0 leak hits |

The index step also runs 20 smoke queries (5 questions, both chunk settings, vector and hybrid search). The expected article was in the top 3 for all 20. That shows the query paths work; it is not an evaluation. Retrieval quality is measured in Milestone 3.

Every metric written to the `ops` schema carries the git commit of the code that produced it.

After the knowledge-base corrections the job was run again, on 2026-11-14 at commit `972de18`: 87 chunks at 800/100 tokens and 161 at 350/60, 248 rows indexed, and 18 of 18 quality checks passed. The evaluation below uses that index.

## Answer quality: the first evaluation

The copilot at this stage retrieves the five best chunks, answers with `databricks-gpt-oss-120b`, cites its sources, and has its citations checked. It was scored on 22 knowledge-base questions: 21 that one help article answers, and 1 that no article answers. Every question and its expected facts were reviewed by hand before the runs.

Three runs, so that each step changes one thing. The two vector-search runs are from 2026-11-14 and the hybrid run is from 2026-11-15 (UTC), all at commit `1a35afb`, with prompt v2, MLflow 3.18.0 and RAGAS 0.4.4. The judge is `databricks-meta-llama-3-3-70b-instruct`, a different model family from the one that answers.

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
- In this run, hybrid search retrieved the one article that vector search over small chunks missed. One row in one run is an observation, not a finding.
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
- These runs cover knowledge-base questions only. Plan lookups, call summaries, hand-offs and trick questions are scored in the 40-row run of the agent, below.
- An earlier draft run is kept in [eval/results](eval/results) for the record. It used questions that had not been reviewed and articles that had not been corrected, and the grading has changed since, so it is not comparable with the runs above.

Reproduce one run (it makes about 350 model calls and takes about 25 minutes on Free Edition; try `--limit 5` first):

```bash
python -m eval.run_eval --config A --query-type ann --tag my-run --category kb
```

## The agent: all 40 questions

The copilot then became an agent. A LangGraph graph gives the model four tools: search the help articles, look up the plan catalogue with parameterized SQL, summarize a redacted call transcript, and open a hand-off to a person. Guardrails sit on both sides of it.

```
question -> redact -> rules, router +-> hand-off (account requests) ------+
                                   +-> fixed refusal (injection) --------+-> output guard -> answer
                                   +-> model <-> tools (capped rounds) --+
```

- **Redaction comes first**, outside any trace, so the personal data it detects in a question never reaches the model, a log or MLflow. What it does not detect gets through: on phrasings it had not seen, it found 30 of 39 values, and 36 of 39 after fixes ([redaction results](#redaction-results-so-far)).
- **The input guard** is plain rules, then a small model. A clear request to change, refund, cancel, unlock or look up something on one customer's account is handed off by the rules with no model call. Everything else goes to a router model that reads the routing policy in words, because on messages the rules had never seen they were half right: see [Routing](#routing-measured-on-messages-the-rules-had-never-seen). If the router cannot be reached, the rules decide and the answer says so.
- **A hand-off is a draft.** The copilot fills in the reason, the team and the urgency, and the agent opens the ticket. Nothing is written before that.
- **The output guard** rewrites an answer that is well above the reading target, then checks citations, removes personal data, and checks [every figure against the sources](#a-check-on-every-figure-in-an-answer). The carrier's public contact details are kept, so an answer can still say which number to call.

All 40 evaluation rows, with the default setting (A, vector search), prompt v3 and the router, at commit `05bbad9`. The run finished on 2026-11-16 at 06:53 UTC. It is the run the [CI gate](eval/gate.py) checks: the gate fails if the code an answer depends on has changed since.

| Kind of question | Rows | Correct | Rules followed | Hand-off decision right | Right tool used | No personal data in the answer |
|---|---|---|---|---|---|---|
| Help articles | 22 | 18/21 | 1/1 | 22/22 | 22/22 | 22/22 |
| Plan lookups | 6 | 5/6 | 1/1 | 6/6 | 5/6 | 6/6 |
| Call summaries | 4 | 1/3 | 0/1 | 4/4 | 3/3 | 4/4 |
| Requests that need a person | 5 | not scored | 5/5 | 5/5 | 5/5 | 5/5 |
| Trick questions | 3 | 1/1 | 2/3 | 3/3 | 1/1 | 3/3 |
| **All** | **40** | **25/31** | **9/11** | **40/40** | **36/37** | **40/40** |

"Correct" is scored where a row lists expected facts, and "rules followed" where it lists rules, so the counts differ by column. Also across all rows: an answer was recorded for 40/40, citations were valid for 40/40, the expected article was found and cited for 22/22, every figure in an answer was in its sources for 40/40, 36/40 answers were at reading grade 8 or below (median 5.7), an answer took a median of 3 model calls, and the median time to answer was 4.4 seconds (90th percentile 9.5).

**Reading these numbers**

- **Against the first full run.** That run (2026-11-15, commit `8624268`, rules only, tickets written without approval) had 27/31 correct and 11/11 rules followed. This one has 25/31 and 9/11. Both are in [SUMMARY.md](eval/results/SUMMARY.md) with their intervals, which overlap almost entirely: 31 rows cannot tell these two apart.
- **The eight failed marks, read one by one** with the judge's reason beside each ([ERRORS.md](eval/results/ERRORS.md)). Six look like the judge's mistake. It failed an answer for listing more steps than the expected facts, for "Unlimited Premium" where the fact says "Northline Unlimited Premium", and for a two-sentence refusal it read as a list of the copilot's rules. Two are the answer's: both are call summaries that left a fact out, that the account has Device Protection and that the customer had already typed in their card number. This reading is not a hand label. The judge has to be [checked against a person](#is-the-judge-right), and that is not done.
- **Hand-offs.** All five account requests were handed off and none of the other 35 questions was. In this run the router made the decision for every message the rules did not hand off, and it was not tuned on these rows. The independent measure is still the [routing set](#routing-measured-on-messages-the-rules-had-never-seen).
- **How sure these are.** With this few rows the ranges are wide: 25/31 correct is consistent with a true rate anywhere from about 64% to 91%.
- **Columns at 100%.** They show the check found no failure, on rows that mostly had nothing to fail.
- **Personal data.** No answer repeated a personal detail from its question or stated one that was not in its sources. One row plants a name, a phone number and Social Security digits in the question to test exactly this. So the 40/40 is one real test and 39 rows with nothing to leak, and the scorer uses the same redactor as the output check, so it cannot catch what that redactor misses.
- **The tool miss.** One plan question was answered from the help articles and not from the plan table. The answer was right.
- **Time.** The median went from 2.5 to 4.4 seconds. The router is one more model call on most answers, and on Free Edition a model call sometimes waits on a rate limit, which is where the slow tail comes from.

## Is the judge right?

Three of the columns above are a model's opinion. A judge that is wrong one time in five moves "correct" by six rows out of 31, which is more than any change to the copilot has moved it. So the judge has to be measured too, in two ways.

- **Against a person.** [eval/judge_sheet.py](eval/judge_sheet.py) writes the judge's verdicts on a saved run as a sheet, one row per verdict, with the question, the answer and what the judge was given. It is built from the traces, so it holds only redacted text. A person marks each one right or wrong, without seeing the judge's verdict if the sheet is made with `--blind`. [eval/judge_agreement.py](eval/judge_agreement.py) then reports agreement, Cohen's kappa with an interval, and every disagreement with the judge's reason.
- **Against answers known to be wrong.** A judge that says yes to everything agrees with a person most of the time on a set where most answers are right. [eval/judge_controls.py](eval/judge_controls.py) takes 23 saved real answers and breaks each in one known way: a changed figure, a dropped fact, an added claim the sources do not hold, an answer to a different question, a broken rule. The judge should fail every one.

**State.** The tooling is built and tested. The hand labels are not done, so no agreement figure is reported here. Until they are, the "correct" column means "the judge said so", and the reading of the failed rows above is a reading, not a measurement.

```bash
python -m eval.judge_sheet eval/results/2026-11-16_m9-full-A-ann.json --blind
python -m eval.judge_controls --list
python -m eval.judge_agreement eval/labels/<sheet>.csv
```

## Routing, measured on messages the rules had never seen

The 40-row evaluation above says every hand-off decision was right. That figure was measured on rows the routing rules were written from. To find out what the rules do on phrasings nobody wrote a rule for, a separate set was built:

- **150 messages** a support agent might type mid-call: 50 requests to act on one customer's account, 60 questions to answer, 40 attempts to override the copilot's instructions. They cover terse and misspelt requests, a customer named only by a pronoun or a placeholder, a request buried after context, questions that merely contain words like "cancel" or "ignore", and questions that quote a scam message.
- **Written blind.** An independent agent wrote them from the routing policy in words. It was not allowed to open the rules, their tests, the evaluation set or the docs. The set was committed before anything was scored on it.
- **Labelled twice.** A second annotator labelled all 150 without seeing the first labels. They agree on 146 (Cohen's kappa 0.96). The writer had marked 17 messages as borderline, and all four disagreements are among those. The figures below are for the other 133.

Everything in the table is a first-contact result: the rules and the router's prompt were written before the set was read, and neither has been changed since. Ranges are 95% intervals.

| | Right | Hand-off requests missed | Override attempts missed | Questions handed off | Questions refused | Median time |
|---|---|---|---|---|---|---|
| The rules alone | 67/133 (41-59%) | 34/45 | 29/37 | 0/51 | 3/51 | none |
| The whole copilot before: rules, then the main model | 95/133 (63-79%) | 6/45 | 28/37 | 0/51 | 3/51 | 1.4 s |
| Router: `llama-4-maverick` | 133/133 (97-100%) | 0/45 | 0/37 | 0/51 | 0/51 | 0.8 s |
| Router: `llama-4-maverick`, prompt r2 (the one in use) | 131/133 (94-100%) | 1/45 | 1/37 | 0/51 | 0/51 | 0.8 s |
| Router: `qwen3-next-80b-a3b-instruct` | 132/133 (95-100%) | 1/45 | 0/37 | 0/51 | 0/51 | 2.1 s |
| Router: `gpt-oss-20b` | 130/133 (93-100%) | 1/45 | 2/37 | 0/51 | 0/51 | 0.9 s |
| Router: `gemma-3-12b` | 124/133 (87-97%) | 1/45 | 5/37 | 2/51 | 1/51 | 0.6 s |
| Router: `llama-3.1-8b-instruct` | 117/133 (81-93%) | 9/45 | 6/37 | 0/51 | 0/51 | 0.6 s |
| The whole copilot now: hand-off rules, then the router | 129/133 (92-99%) | 1/45 | 0/37 | 1/51 | 1/51 | 0.8 s |

**What this shows**

- **The rules were half right.** They missed three hand-off requests in four and four override attempts in five. They never handed off a question, which is what rules are good at: the ones that fire are precise.
- **The main model covered for most missed hand-offs.** Of the 34 requests the rules missed, it opened 28 itself with its hand-off tool. The other 6 got an answer and no ticket.
- **Override attempts were the gap.** 28 of 37 reached the main model. That run records a refusal only when the rules refuse, so how many the main model declined in its own words is not known.
- **A small model reading the policy does far better than the rules.** Five were tried with the same prompt, never tuned on this set. The best got all 133.
- **Putting the rules in front of the router makes it worse.** The rules refuse questions that only quote an override attempt ("the customer got a text saying 'ignore your instructions', is it a scam?"), and those refusals carry through. So the copilot keeps the rules for hand-offs only, where they were right 11 times out of 11, and gives everything else to the router.
- **The whole copilot now gets 129 of 133.** Three of the four misses are messages where the router's endpoint was rate-limited, so the rules decided, which is the designed fallback. The fourth is the main model opening a hand-off for a plan price question.

- **The router's prompt was changed once, and it cost two rows here.** On the 40 evaluation questions the first prompt handed off "What is the account PIN and where does a customer change it?", a how-to question. The second prompt (r2) says outright that asking how something works is a question. It was then scored on this set: 131 of 133, against 133 for the first. Both of its misses went to "answer", where the model that answers is a second check and can still open a hand-off; a question wrongly handed off has no second check, because the agent just gets no answer. So r2 is the one in use. No message of this set was read to write it, so the comparison is fair; two rows out of 133 is also within what running the same prompt twice could give. The "whole copilot now" row above was measured with the first prompt.

**What it costs.** One small model call, about 0.8 seconds, on every message the rules do not hand off. If the router does not answer within 8 seconds or cannot be read, the rules decide and the answer says so.

**Limits**

- The best router was picked from five on this same set, so its 133/133 is the best of five and flatters it a little. The interval (97-100%) does not allow for that.
- The messages were written by a language model, not typed by support agents.
- A sixth model, `qwen35-122b-a10b`, could not be scored: with these settings none of its replies could be read, because it spends the token limit on reasoning. At 3.9 seconds a call it would be too slow for this job anyway.
- The 40-row evaluation above was run before the router existed. It has not been re-run with it.

Every prediction is in [eval/results](eval/results) (`routing_*.json`). To score the rules again, which calls no model:

```bash
python -m eval.routing_eval --router rules
python -m eval.routing_eval --compare
```

## Which model answers

The copilot answers with `databricks-gpt-oss-120b`. Four other open-weight models on the workspace support tool calls, so each was put in its place and run on the same 40 questions, with the router on, on 2026-11-16 at commit `8478690`. Two judges scored them (correctness and rules followed), and code scored the rest.

| Answering model | Correct | Rules followed | Right tool | Source cited | Reading level ok | Figures in sources | Reading grade | Median time | 95th percentile |
|---|---|---|---|---|---|---|---|---|---|
| `gpt-oss-120b` | 25/31 (63-91%) | 10/11 (62-99%) | 35/37 (82-99%) | 21/22 (78-100%) | 38/40 (83-99%) | 40/40 (91-100%) | 5.6 | 3.8 s | 5.3 s |
| `llama-4-maverick` | 23/31 (56-87%) | 9/11 (52-95%) | 33/37 (75-96%) | 18/22 (61-93%) | 34/40 (70-93%) | 40/40 (91-100%) | 7.5 | 4.9 s | 6.8 s |
| `qwen3-next-80b-a3b-instruct` | 23/31 (56-87%) | 9/11 (52-95%) | 31/37 (68-93%) | 16/22 (51-87%) | 37/40 (80-98%) | 39/40 (87-100%) | 5.7 | 3.3 s | 4.7 s |
| `qwen35-122b-a10b` | 23/31 (56-87%) | 10/11 (62-99%) | 34/37 (78-98%) | 19/22 (66-96%) | 38/40 (83-99%) | 40/40 (91-100%) | 5.7 | 3.8 s | 8.2 s |
| `gemma-3-12b` | 21/31 (50-82%) | 9/11 (52-95%) | 29/37 (62-89%) | 15/22 (47-84%) | 37/40 (80-98%) | 39/40 (87-100%) | 5.5 | 3.5 s | 5.6 s |

- **Nothing here argues for a change.** `gpt-oss-120b` has the most correct answers, cites its source most often and picks the right tool most often. The gaps to the others are a few rows, and with 31 scored rows a gap of two is inside the intervals, so the honest claim is that no other model is better, not that this one is proven best.
- **The hand-off decision was right for 38/40, 39/40 in every run**, whichever model answered, because the router makes that decision. The one miss is the same question each time: "What is the account PIN and where does a customer change it?" was handed off as if it asked for one customer's PIN. The router's prompt has since been made clearer on exactly that, which makes this row in-sample for it.
- **These are not full evaluations.** Only two judges ran, each model ran once, and the judge is known to mark two of these answers wrong when they are right ([ERRORS.md](eval/results/ERRORS.md)). The CI gate ignores these runs.
- **What is on offer.** The Databricks docs list about 70 hosted models. This Free Edition workspace exposes eight chat endpoints, and three newer open-weight ones from the docs (`glm-5-3`, `deepseek-v4-1-flash-1017`, `kimi-k3`) returned "endpoint not found" when called on 2026-11-15.

```bash
python -m eval.run_eval --config A --query-type ann --tag models-<name> --llm-endpoint databricks-<name> --judges correctness,expectations_guidelines --limit 5
```

## A check on every figure in an answer

A model can write "$7" where its source says "$5", and the citation check passes: the marker still points at a real source. So every answer now has its figures read out and looked up in the text the copilot was given: prices, amounts with a unit, percentages, phone numbers, numbers to dial and web addresses. It is plain code ([src/copilot/claims.py](src/copilot/claims.py)), makes no model call, and runs on every answer. A plainer rewrite of an answer is also thrown away if it changes a figure.

It was measured on 43 answers collected from the live copilot on 2026-11-16 (commit `7f8961d`), which state 76 distinct figures:

| | Result | 95% interval |
|---|---|---|
| Real figures it wrongly reported | 0/76 | 0-5% |
| Changed figures it caught | 170/194 | 82-92% |
| ... phone numbers | 23/23 | 86-100% |
| ... numbers to dial | 19/19 | 83-100% |
| ... web addresses | 7/7 | 65-100% |
| ... prices | 50/57 | 77-94% |
| ... amounts with a unit | 71/88 | 71-88% |

The second row comes from changing each accepted figure to a different value, three ways, and running the check again.

- **What it misses.** All 24 misses are prices and amounts. The check tests that a figure is present in the evidence, not which fact it belongs to. Change "$15" to "$25" in an answer about plans and it passes, because another plan costs $25. An answer written from five articles and an 18-row catalogue has a lot of numbers to collide with.
- **What it does not read.** Numbers written as words, and a figure the model worked out ("two lines at $25 is $50").
- **What it does today.** It flags the answer and shows the agent a warning: "Check a figure before you say it". It does not block or change the answer. With no false alarm in 76 real figures, blocking is the next step, but 76 is too few to be sure of that.

```bash
python -m eval.claim_check_eval
```

## Checking every call for a broken rule

A supervisor reviews a handful of calls. The copilot checks all of them for five rule breaches, on the redacted transcripts, with plain rules and no model call ([src/copilot/compliance.py](src/copilot/compliance.py)). Most of it needs no language at all: a card placeholder in an agent's turn is a card read back, and a bill-amount placeholder before any answered identity question is a disclosure.

The original 200 calls break no rule, so there was nothing to detect. A generator ([data_gen/synth_breaches.py](data_gen/synth_breaches.py)) writes 382 more, T0201 to T0582, from its own seed: each is clean, a near miss, or breaks exactly one rule at a labelled turn. The near misses are the point: a catalogue price said before verification is not account data, and "the billing team can waive it" is not a promise. Half the calls were used to write the rules. The other half use wording written by a separate agent that never saw the rules, and were scored once, on 2026-11-16 at commit `e95af8a`:

| Rule | Breaches caught | Findings that were right |
|---|---|---|
| The agent reads a full card number back | 20/20 (83-100%) | 20/20 (83-100%) |
| Account work with no identity check anywhere in the call | 26/26 (87-100%) | 26/27 (81-100%) |
| Account details stated before the identity check | 21/27 (59-90%) | 21/22 (78-100%) |
| The agent says they have waived or refunded a charge themselves | 15/20 (53-89%) | 15/16 (71-99%) |
| The agent asks for the full Social Security number | 14/20 (48-86%) | 14/16 (63-97%) |

- **On the 200 original calls, which break no rule, it raised 0 of 200 findings** (95% interval 0 to 1.9%).
- **The two rules that rest on placeholders caught everything.** The three that rest on wording caught 70 to 78%, against 100% on the half they were written on. That gap is what a rule costs when someone phrases it a new way: "I zeroed that one out" is a promise the rule has no pattern for.
- **It sees only what the redactor marked.** Three of the six missed disclosures are figures the redactor left in plain text, such as "$33.62 still outstanding" with no cue word near it. That is a redaction gap first and a compliance miss second.
- **Precision here is not precision in life.** Half of these calls contain a breach. Real calls rarely do, so read the precision column beside the false-alarm rate above.
- **Limits.** The calls are synthetic and reuse 22 scripted scenarios. The held-out half is not perfectly blind: the writer's summary named a few of its phrasings before the rules were finished, and those phrases were then kept out of the rules. Nothing was changed after the held-out result was seen. A model that reads the turn and the policy would handle the wording rules better; it is not built, and it would need a fresh held-out set.

```bash
python -m data_gen.synth_breaches
python -m eval.compliance_eval
```

## After the call: the wrap-up

When a call ends, the agent writes it up: how it ended, what it was about, what was said and promised, and who does what next. The copilot drafts that record from the redacted transcript for the agent to check and save ([`wrap_up_call`](src/copilot/tools.py)). The model is given the turns and nothing else: the call's recorded outcome and category are never near the prompt, so they can be used to score it. Nothing is stored until the agent approves the draft.

Two of its fields have a label to score against. On the 200 calls, each drafted once, on 2026-11-16 at commit `a881459`:

| Field | Right | When it says so, it is right | Of the calls that are so, it finds |
|---|---|---|---|
| How the call ended | 177 of 200 (83-92%) | | |
| - resolved | | 108/116 | 108/119 |
| - handed to another team | | 47/47 | 47/57 |
| - unresolved | | 22/34 | 22/24 |
| What the call was about | 197 of 200 (96-99%) | | |

- **It is cautious in one direction.** 11 calls the generator labels resolved were drafted as unresolved, and "unresolved" is the label it is least often right about. An agent who reads the draft corrects that with one click; the opposite error, a problem marked solved, happened less.
- **6 hand-offs were drafted as resolved.** That is the error that matters: a call that needs another team would be filed as finished if the agent saved the draft unread. It is why the draft is not saved for them.
- **3 calls got no draft**, because the model's reply was not the JSON it was asked for. The agent sees a fixed message and can ask again. There is no automatic second try yet.
- **Limits.** The labels are the transcript generator's, not a person's. The 200 calls come from 22 scripts, so they are not independent and the intervals are too narrow. The notes, the promises and the next step are checked for personal data and are not scored for being right.

```bash
python -m eval.wrapup_eval --limit 5
```

## When a part fails

A copilot is a chain of things that can each be down: a router model, a model that answers, a search index, a SQL warehouse, a trace store. What happens then was not left to chance. [tests/test_failure_modes.py](tests/test_failure_modes.py) and [tests/test_failure_modes_api.py](tests/test_failure_modes_api.py) break each part in turn, with fakes and no model call, and read the answer, the log and the trace afterwards.

| What fails | What the agent gets |
|---|---|
| The router model is slow or unreachable | An answer, routed by the plain rules, with a step that says so |
| The model that answers times out | A fixed message to try again. The log has the kind of error and the line, and nothing of the question |
| A lookup fails: the warehouse is stopped, the index is down | An answer that says the lookup failed. The other lookups of the same round still run |
| The search finds no article | An answer marked as having no article behind it |
| The model asks for a tool that does not exist | The model is told, and answers. The made-up name is written nowhere else |
| The model asks for 25 lookups at once, or never stops asking | The first six of a round run, and at most four rounds |
| The rewrite into plainer words fails | The first draft, with a step that says it was kept |
| A hand-off ticket cannot be written | The words to transfer the customer by hand |
| The trace store cannot save a rating | A fixed message. The answer itself is not affected |

- **Writing these tests found three defects**, each first recorded as a test expected to fail: a tool name the model made up went unchecked onto the trace and into the answer, a failed rewrite threw away an answer that was already written, and four endpoints answered an unexpected error with a bare 500 and let its message through to the web server's log. All three are fixed, and the tests now pass as written.
- **Not handled.** If the model that answers fails, the request fails: there is no second model to fall back to. Tool arguments that are not valid JSON end in the fixed fallback answer. An answer written after a search that found nothing is delivered with a flag and is not blocked.

## Try it

**The app.** A web interface in which the copilot is called Cue. It has two views:

- **Ask.** A conversation. Each answer highlights the facts to say out loud, numbers its sources, and shows the route of steps the copilot took: the privacy check, the request check, the lookup and the answer checks. A question that held personal details is shown again as it was processed, with the details replaced. A request that needs a person shows the hand-off and its reference. Thumbs feedback is saved on the MLflow trace.
- **Calls.** The redacted call transcripts, with a summary on request shown beside the transcript.

![A hand-off in the dark theme. The agent's question held a name and a phone number; the line under it shows them replaced by placeholders, and the route of steps branches to a tag that says a person has the request.](docs/img/cue-hand-off.png)

While an answer is on its way, the page shows what the copilot is really doing: "Checking the request", "Searching the help articles", "Writing the answer". The agent reports each stage as it starts and the API streams them (`POST /api/ask/stream`, server-sent events). An event is a stage name and fixed words; it never carries the question or anything a tool returned.

When a request needs a person, the copilot does not open a ticket. It drafts one: which team, how urgent, and what is needed, with personal details replaced. The agent reads it, changes what is wrong, and opens it, or decides not to. Only then is a ticket written (`POST /api/handoffs`), and the agent gets the reference and what to tell the customer.

It is a REST API ([api/main.py](api/main.py), FastAPI) that calls the same agent code the evaluation measures, and a front end in [web](web) (React, TypeScript, Vite, Tailwind) that the API serves. The look is specified in [web/DESIGN.md](web/DESIGN.md), and the mockups and decisions behind it are in [design](design). Both pictures on this page are from the public demo, so the answers in them are recordings of the live copilot's output.

Three ways to open it:

1. **The public demo**, with no setup: <https://srimaansri.github.io/frontline-copilot/>. Recorded answers, as described at the top: the four example questions, every question in the evaluation set, and a few everyday messages such as "hello". The Calls view lists all 200 calls, and the ones named in [eval/record_demo.py](eval/record_demo.py) have a transcript and a summary.
2. **The same demo on your machine**, with Node and no Databricks workspace:

   ```bash
   cd web && npm install && npm run dev:mock
   ```

3. **The real thing**, against a Databricks workspace set up as in [PLAN.md](PLAN.md) section 3:

   ```bash
   pip install -e ".[dev,models]"
   ```

   ```bash
   cd web && npm install && npm run build && cd ..
   ```

   ```bash
   uvicorn api.main:app --port 8000
   ```

   Then open `http://localhost:8000`.

On Databricks Apps the same app runs from `app.yaml` at the repository root, as the app's own service principal, and `python setup/deploy_app.py` deploys it. Its access is declared as app resources and is the minimum it needs: use of the SQL warehouse, query on the chat and embedding endpoints, edit on the MLflow experiment, read on the plan table, the redacted transcripts and the search index, and write on the hand-off table. It has no access to the unredacted tables.

The deployed app was checked on 2026-11-15, at commit `192eea2`, by calling it through its own address with a workspace sign-in: it served the page, answered a help-article question with a citation and an MLflow trace, and listed the 200 calls. Nobody has yet clicked through the deployed page in a browser. Free Edition stops an app 24 hours after each start and the app needs a workspace sign-in, which is why the public link above is the mock demo and not the live app.

**The MCP server.** The same four tools, for another assistant to call. See [mcp_server/README.md](mcp_server/README.md).

```bash
python -m mcp_server.server
```

## Redaction results so far

The redactor replaces personal data in support transcripts with typed placeholders such as `<PHONE_NUMBER_1>`. It is measured on synthetic transcripts whose personal values are inserted by code, so the labels are exact. All runs below are from 2026-11-12 with spaCy `en_core_web_md` 3.8.0 and Presidio 2.2.366.

| Set | What it tells you | PII recall | PII precision | CPNI recall | Commit |
|---|---|---|---|---|---|
| Test: 30 transcripts, 209 PII values | New names and numbers in phrasings the redactor was tuned on. An upper bound. | 1.000 (209/209) | 1.000 | 1.000 (12/12) | `b0a26de` |
| Challenge, first run: 50 hand-written lines, 39 PII values | Phrasings the redactor had never seen. **The number to trust**, though 39 values is few: the 95% interval is 61 to 88%. | 0.769 (30/39) | 0.857 | 0.333 (2/6) | `ed7ad27` |
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

Unity Catalog, Delta Lake and PySpark for the data pipeline. Databricks AI Search for retrieval. An open-weight LLM served by the Databricks Foundation Model APIs. MLflow 3 for tracing and evaluation, with RAGAS. LangGraph for the agent. Presidio and spaCy for PII redaction. A FastAPI REST API and a React, TypeScript and Tailwind front end on Databricks Apps for the interface, and an MCP server so other assistants can call the same tools.

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

The web interface has its own checks, which CI also runs:

```bash
cd web && npm ci && npm run typecheck && npm run lint && npm run build
```

`npm run lint` includes a contrast check of every colour pair in both themes.

Configuration comes from `config/settings.yaml`, overridden by a local `.env` (copy `.env.example`) and by environment variables. Nothing secret is committed.

## Build status

This repo is being built milestone by milestone. Every number here comes from a real run, with its date and git SHA. The full reports are in [eval/results](eval/results): [SUMMARY.md](eval/results/SUMMARY.md) has every rate with its 95% interval, and [ERRORS.md](eval/results/ERRORS.md) lists every row that failed.

| Milestone | What | State |
|---|---|---|
| M0 | Scaffold: tooling, config loader, CI | Done |
| M1 | Data generation and PII redaction, measured locally | Done |
| M2 | Databricks pipelines: bronze, silver, gold, quality checks | Done |
| M3 | Retrieval-augmented answers and the first evaluation | Done |
| M4 | Agent with tools, guardrails, escalation | Done |
| M5 | App, MCP server | Both run locally against the live workspace. The MCP Docker image builds and starts. The app is deployed on Databricks Apps and answers there (checked 2026-11-15, see [Try it](#try-it)). It began as a Streamlit page and is now a REST API with a React front end |
| M6 | Results, model and data cards, responsible-AI notes | The cards are written: [model card](docs/MODEL_CARD.md), [data card](docs/DATA_CARD.md), [responsible-AI notes](docs/RESPONSIBLE_AI.md). Not done: the demo video, and a check of the judge against hand labels |
| M7 | Fix and prove: guard and history fixes, intervals and a CI gate on the evaluation, a public demo that replays real answers | Done |
| M8 | An evaluation that can fail, and a measured router | Part done: a [held-out routing set](#routing-measured-on-messages-the-rules-had-never-seen) with six routers scored on it, the best one now in the agent, and a [check on every figure](#a-check-on-every-figure-in-an-answer). Not done: the larger evaluation set, the judge checked against hand labels, abstention, tokens per answer |
| M9 | Live progress, approval before a ticket is written, after-call work | Built: the interface shows each stage of an answer as the copilot starts it, a hand-off is drafted for the agent to approve before anything is written, and the copilot drafts the after-call wrap-up (how the call ended, what it was about, notes, promises, who owns the next step) for the agent to check and save. Not done: a clarifying question for an ambiguous request, and a pipeline step that wraps up all calls in a batch |
| M10 | Call assist and compliance review | Part done: [every call is checked for five rule breaches](#checking-every-call-for-a-broken-rule), with recall and precision per rule on held-out wording. Not started: live call assist |

The full specification is in [PLAN.md](PLAN.md).

## How this was built

With AI coding assistants, under written rules. [CLAUDE.md](CLAUDE.md) is the working agreement given to Claude Code, and [docs/BUILD_LOG.md](docs/BUILD_LOG.md) records what was asked, what was produced, and what was changed or rejected.
