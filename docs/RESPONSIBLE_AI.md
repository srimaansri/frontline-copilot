# Responsible AI notes

How this project handles privacy, human oversight, transparency and accessibility, and where it falls short. The controls are mapped to the four functions of the NIST AI Risk Management Framework at the end.

This is a demo on synthetic data. Nothing here is a claim about how a production system would perform.

## What the copilot is for

It helps a support agent answer a customer faster: it finds the help article, looks up a plan, summarizes an earlier call, or says the request needs a specialist.

It is **not** for:

- Talking to customers directly. A support agent reads every answer before anything reaches a customer.
- Acting on an account. It cannot see, change, refund or cancel anything.
- Advice outside the carrier's own help content and plan catalogue.

## Human oversight

- **The agent is always in the loop.** The copilot answers the agent, not the customer.
- **It cannot act on an account.** Its four tools search articles, read the plan catalogue, summarize a redacted transcript and open a hand-off. None writes to an account.
- **Account requests go to a person.** A request to change, refund, cancel, unlock or look up something on one customer's account is routed to a hand-off by plain rules, before any model is called. The model can also open a hand-off for a request the rules miss.
- **A failed hand-off is not silent.** If the ticket cannot be written, the agent is told to transfer the customer by hand.

## Personal data and CPNI

**What CPNI is.** Customer Proprietary Network Information is what a carrier knows about a customer from providing the service: who they call, when, how much they use, and what they are billed. United States law (47 U.S.C. § 222) requires carriers to protect it. For a carrier it sits alongside ordinary personal data such as names and addresses.

**How the design keeps both out of places they should not be:**

| Place | Control |
|---|---|
| Stored transcripts | Redacted in the pipeline. Only the redacted table is read at answer time |
| The question an agent types | Redacted before any traced code runs, because a trace records a function's inputs as soon as it is called |
| MLflow traces | Hold only redacted text. A test inspects a real recorded trace for a planted phone number and email |
| The evaluation dataset | MLflow is given redacted questions, because it stores the dataset with the run |
| Hand-off tickets | The reason is redacted before the insert |
| Answers | Checked last. Anything the redactor finds that is not written in the sources is replaced |
| The knowledge base | Contains only the carrier's public contact details. The answer check keeps those, so an answer can still say which number to call |
| Other assistants (MCP) | Free text arriving over MCP is redacted before it is used |

**What is measured.** The redactor's recall and precision are reported in the [README](../README.md), on a test set, and on a hand-written challenge set that it was not tuned on. The challenge set is the honest number: 0.77 recall on first contact, 0.92 after fixes, with the second no longer held out.

**What it misses.** Phone numbers and dates spoken as words, email addresses spelled out loud, amounts written in words, and usage figures with no cue word nearby. The first two are recorded as expected-failure tests so they are not forgotten.

## Transparency

- **Citations.** An answer drawn from a help article cites it, and the citation is checked against what was actually retrieved. A citation that points to nothing is removed and flagged.
- **Shown working.** The app shows which tools were used, the sources, any guardrail flags and the time taken.
- **Traces.** Every answer has an MLflow trace with the retrieval, each tool call and each model call.
- **Versioned prompts.** The prompt version is recorded on every trace and every evaluation run.
- **Says when it does not know.** The copilot is instructed to say so when its sources lack the answer, and one evaluation row tests that it does not invent one.

## Plain language and accessibility

Many customers of a carrier like the one imagined here are older adults, and the agent often reads the answer aloud.

- Answers are asked for at a grade 6 to 8 reading level, in short sentences, leading with the direct answer.
- Reading grade is measured on every evaluated answer. An answer well above the target is rewritten once, and the rewrite is kept only if it is easier to read.
- The app uses large type and strong contrast.

Reading grade is a rough proxy. A low grade does not prove an answer is clear.

## Fairness

The data is synthetic and carries no demographic information, so fairness across groups of customers has not been measured and no claim is made about it. Known gaps that would matter with real users: everything is in English, and names and addresses follow United States formats, so the redactor is untested on others.

## Safety and misuse

- **Prompt injection.** Text from help articles, transcripts and tool results is marked as reference material, not instructions. An obvious attempt to override the instructions gets a fixed refusal without a model call.
- **Parameterized SQL.** Every value that comes from a model is a bound parameter. No SQL is built from model output.
- **Bounded tool use.** The agent has a fixed number of tool rounds, after which it must answer with what it has.
- **Off-topic requests** are declined.

## Evaluation honesty

- Every reported number comes from a real run, with its date and git commit.
- The judge is a language model from a different family than the one that answers. It makes mistakes; two were found by inspecting failures and are described in the README. A hand check of the judge on 10 rows has not been done yet.
- The rules that route account requests to a hand-off were written with the evaluation's hand-off rows in view. The hand-off score on those rows shows the rules work on them; it is not an independent measure.
- The evaluation set is small and no significance is claimed for any difference.

## Mapping to the NIST AI Risk Management Framework

| Function | What this project does |
|---|---|
| **Govern** | Written working rules in [CLAUDE.md](../CLAUDE.md): no secrets in the repository, no unredacted transcript text in tables, logs or traces, no invented numbers. A build log records what was asked, built and changed. Prompts are versioned. |
| **Map** | Intended use and out-of-scope use are stated above. The data card records where every dataset came from and its limits. Risks specific to a carrier (CPNI, account actions) are named and each has a control. |
| **Measure** | Redaction recall and precision on test and held-out sets. Answer quality scored by model judges plus checks that need no model: citations, reading grade, hand-off, tool choice, personal data in answers, latency. Pipeline quality checks, including a scan for leftover personal data. |
| **Manage** | Guardrails on input and output. Hand-off to a person for account requests. Feedback buttons in the app that save a rating on the answer's trace. Known failure modes are listed with each result. |

## Not done

- No hand check of the judge yet.
- No monitoring of live use; the app saves feedback but nothing reviews it.
- No evaluation on real conversations or real help content.
- No access control beyond what the Databricks workspace provides.
