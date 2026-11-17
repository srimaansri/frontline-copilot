# Model card: Frontline Copilot

A description of the system as a whole. It does not train a model; it uses hosted models and adds retrieval, tools, checks and a person's approval around them.

## What it is

An assistant for frontline support agents at a wireless carrier. The agent types a question and gets a short, plain-language answer with cited help articles, a plan lookup from the catalogue, a summary of a redacted call, or a drafted hand-off to a human specialist. After a call it drafts the wrap-up. While a recorded call is replayed it keeps a matching article, a next step and reminders on show.

| Part | What is used |
|---|---|
| Answering model | `databricks-gpt-oss-120b`, an open-weight model served by Databricks Foundation Model APIs. Temperature 0.1, up to 700 output tokens. Kept after a comparison with four others on the 40 questions |
| Routing | Plain rules hand off a clear account request with no model call. Everything else goes to `databricks-llama-4-maverick` at temperature 0 with router prompt r2 (`src/copilot/router.py`), which decides between a question, a request that needs a person, and an attempt to override the instructions. If it is slow or unreachable the rules decide, and the answer says so |
| Embeddings | `databricks-gte-large-en`, through a Delta Sync index on Databricks AI Search |
| Judge, for evaluation only | `databricks-meta-llama-3-3-70b-instruct`, a different model family from the one that answers |
| Redaction | Presidio 2.2.366 with spaCy `en_core_web_md` 3.8.0 and project-specific recognizers |
| Agent | LangGraph 1.2.22, four tools, at most 4 tool rounds per answer and 6 tools in one round |
| Checks on an answer | Citations, personal data, reading level, and every figure (price, amount, percent, phone number, web address) against the text the answer was written from |
| Prompt | Version v3, in `src/copilot/prompts.py`. The version is recorded on every trace and evaluation run |
| Retrieval | Top 5 chunks, 800-token chunks with 100 overlap, vector search |

## Intended use

- Helping a support agent find and phrase an answer while they talk to a customer.
- Looking up plan prices and features from the catalogue.
- Summarizing an earlier call from its redacted transcript, and drafting the after-call wrap-up for the agent to check and save.
- Recognising a request that needs account access and drafting a hand-off for the agent to approve.
- Checking redacted calls for five rule breaches, for a supervisor to review.

## Out of scope

- Talking to customers directly, without an agent reading the answer first.
- Any action on an account. The system has no tool that can change one, and it writes a ticket or a wrap-up only after the agent approves it.
- Questions outside the carrier's help content and plan catalogue. It is instructed to decline them.
- Listening to a live call. Call assist replays stored, redacted transcripts: there is no audio, no speech recognition and no live redaction.
- Any use on real customer data. It has only been run on synthetic data.

## Data

All synthetic: 87 help articles for a fictional carrier, an 18-row plan catalogue, 200 templated support transcripts, and 382 more in which a rule is or is nearly broken. See the [data card](DATA_CARD.md).

## Evaluation results

Every number is from a real run, recorded with its date and git commit in [eval/results](../eval/results). The [README](../README.md) has the tables, the intervals and the limits of each.

**Answers, all 40 evaluation rows** (run `m9-full`, finished 2026-11-16 06:53 UTC, commit `05bbad9`, prompt v3, with the router):

| Measure | Result |
|---|---|
| Correct against the expected facts, by the judge | 25/31 |
| Followed the row's rules (hand-offs, refusals, no invented answer) | 9/11 |
| Hand-off decision right | 40/40 |
| Right tool used | 36/37 |
| No personal data in the answer | 40/40. One row plants personal data; the others have none to leak |
| Expected help article retrieved, and cited | 22/22, 22/22 |
| Grounded in the retrieved text, by the judge | 21/22 |
| Every figure in the answer is in its sources | 40/40 |
| Reading grade 8 or below | 36/40, median grade 5.7 |
| Model calls for one answer | Median 3 |
| Time to answer | Median 4.4 seconds, 90th percentile 9.5. The slow tail is rate-limit waits on Free Edition |

**Routing** (133 clear messages written and labelled without sight of the rules): the plain rules alone 67/133; the router model alone 133/133 with its first prompt and 131/133 with the second, which is the one in use; the whole copilot 129/133, measured with the first prompt.

**The check on figures:** 170/194 deliberately changed figures caught, 0/76 real figures wrongly reported.

**Redaction** (2026-11-12, commit `b0a26de`): on 30 labeled test transcripts, recall 1.000 (209/209) and precision 1.000 for personal data. On 50 hand-written lines the redactor was not tuned on, recall was 0.769 (30/39) on first contact and 0.923 (36/39) after fixes; the second figure is no longer held out.

**Compliance review** (held-out wording, scored once): 20/20 and 26/26 breaches caught for the two rules that rest on redaction; 21/27, 15/20, 14/20 for the three that rest on wording; 0/200 clean calls flagged.

**Wrap-up** (2026-11-16, commit `a881459`, labels from the transcript generator): how the call ended 177/200, what it was about 197/200, no draft for 3.

## Known limitations and failure modes

These come from the evaluation runs and from running the system, not from speculation.

- **It can merge two nearby statements into a wrong one.** In an earlier run, an answer said the carrier "never asks for" the account PIN by phone, when support does ask for it on a call the customer makes. The article states both points close together.
- **The router can hand off a question.** With its first prompt it handed off "What is the account PIN and where does a customer change it?", which is a how-to question. The second prompt fixed that row and scored two lower on the held-out set; its two misses still reach the model that answers.
- **Small chunks with vector search can miss the right article.** In one of three retrieval runs, a question about a suspicious text message did not retrieve the article on scam messages. Hybrid search retrieved it.
- **An answer written after a search that found nothing is delivered with a flag.** It is not blocked. The check on figures also only flags.
- **A wrap-up can mark a hand-off as resolved**, and it says "unresolved" more often than the labels do. The draft is never saved unread.
- **A call summary can leave out a key fact.** In one run the judge found a summary did not say that the customer had already typed in their card number.
- **Some answers are above the reading target** after the one-time rewrite.
- **The redactor misses spoken forms**: phone numbers and dates said as words, email addresses spelled out, amounts written in words. It also leaves some account figures in plain text when no cue word is near them, which the compliance rules then cannot see.
- **The wording rules of the compliance review miss new phrasings**: they caught 70 to 78% on held-out wording, against all of the half they were written on.
- **The judge is wrong some of the time.** In several runs it marked two answers incorrect that contain every expected fact. Reported numbers are as the judge gave them. The tooling to check it against a person's labels and against deliberately wrong answers exists ([eval/judge_sheet.py](../eval/judge_sheet.py), [eval/judge_controls.py](../eval/judge_controls.py), [eval/judge_agreement.py](../eval/judge_agreement.py)); the labels are not done.
- **If the model that answers fails, the request fails.** There is no second model to fall back to. What each other failure does is in the README, under "When a part fails".
- **Tool calling on this model is documented as tuned for a single step.** Multi-step tool use worked in every case tried here, but that is a small sample.

## What has not been evaluated

- Real conversations, real help content, or real customers.
- Fairness across groups of customers. The data has no demographic information.
- Languages other than English.
- Behaviour under load. Tokens and model calls per answer are counted; cost in money is not.
- Whether a next step shown by call assist, or the notes of a wrap-up, are right. They are checked for personal data, not for truth.
- Robustness to prompt injection beyond the override attempts in the held-out routing set.

## Ethical considerations

Covered in the [responsible-AI notes](RESPONSIBLE_AI.md): human oversight, handling of personal data and CPNI, transparency, plain language, and a mapping to the NIST AI Risk Management Framework.
