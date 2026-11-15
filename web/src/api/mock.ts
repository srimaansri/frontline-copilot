/**
 * Built-in fixtures for mock mode (`VITE_USE_MOCK=1`).
 *
 * They let the interface be developed and screenshotted with no server. The
 * wording follows the synthetic Northline help articles and plan catalogue, and
 * the step titles are the ones the real API sends. Nothing here is used by a
 * normal build.
 */

import { DEMO } from "@/lib/devHooks";

import { ApiError } from "./client";
import type {
  Api,
  AskRequest,
  AskResponse,
  CallListItem,
  CallSummary,
  CallTranscript,
  Citation,
  Meta,
  Resolution,
  Step,
} from "./types";

const HELP = "https://help.northline.example/articles";

/** The ticket the hand-off fixture opens. It is in the answer and on the hand-off step. */
const HANDOFF_REFERENCE = "ESC-4F2A91C7";

const META: Meta = {
  app_name: "Frontline Copilot",
  carrier: "Northline Wireless",
  model: "databricks-gpt-oss-120b",
  prompt_version: "v3",
  search: { chunk_config: "A", query_type: "ann", top_k: 5 },
  tracing: true,
  tools: [
    { name: "search_kb", label: "Help articles" },
    { name: "get_plan_details", label: "Plan catalogue" },
    { name: "summarize_call", label: "Call summary" },
    { name: "escalate_to_human", label: "Hand-off to a person" },
  ],
  examples: [
    {
      question: "How much is the late payment fee, and can it be waived?",
      tool: "search_kb",
      hint: "An answer from the help articles, with its source",
    },
    {
      question: "Which plans cost $25 a month or less?",
      tool: "get_plan_details",
      hint: "A lookup in the plan catalogue",
    },
    {
      question: "Summarize call T0002.",
      tool: "summarize_call",
      hint: "A summary of a redacted call",
    },
    {
      question: "Refund the $5 late fee on this customer's account.",
      tool: "escalate_to_human",
      hint: "A request that needs a person",
    },
  ],
  disclaimer:
    "Unofficial demo. Not affiliated with or endorsed by any carrier. " +
    "Northline Wireless is fictional and all data is synthetic.",
};

// --- Calls -------------------------------------------------------------------------------

const CATEGORIES = [
  "billing",
  "troubleshooting",
  "device_setup",
  "plan_change",
  "add_line",
  "international",
  "lost_stolen",
  "cancel_port",
  "scam",
  "accessibility",
] as const;

const RESOLUTION_CYCLE: readonly Resolution[] = [
  "escalated",
  "resolved",
  "resolved",
  "escalated",
  "resolved",
  "resolved",
  "unresolved",
  "resolved",
  "resolved",
  "unresolved",
];

const CALL_COUNT = 200;

/** Two hundred rows, the same on every load. Only T0001 and T0002 have a transcript. */
const CALLS: CallListItem[] = Array.from({ length: CALL_COUNT }, (_, index) => {
  // Shift each block of ten, so the list does not repeat in an obvious pattern.
  const block = Math.floor(index / CATEGORIES.length);
  return {
    transcript_id: `T${String(index + 1).padStart(4, "0")}`,
    category: CATEGORIES[(index + block * 3) % CATEGORIES.length] ?? "billing",
    resolution: RESOLUTION_CYCLE[(index + block * 7) % RESOLUTION_CYCLE.length] ?? "resolved",
  };
});

const TRANSCRIPTS: Record<string, CallTranscript> = {
  T0001: {
    transcript_id: "T0001",
    turns: [
      {
        speaker: "agent",
        text: "Thank you for calling Northline Wireless. My name is <PERSON_1>. Who am I speaking with?",
      },
      {
        speaker: "customer",
        text: "Hi, this is <PERSON_2>. There is a late fee on my bill and I don't think it is right.",
      },
      {
        speaker: "agent",
        text: "Hi <PERSON_2>! I can help you look at that. Can you confirm the phone number on the account?",
      },
      { speaker: "customer", text: "Sure, it's <PHONE_NUMBER_1>." },
      {
        speaker: "agent",
        text: "Thank you. The Late Payment Fee is $5. It is added when a bill is more than 10 days past its due date.",
      },
      {
        speaker: "customer",
        text: "I paid as soon as the reminder reached me at <EMAIL_ADDRESS_1>. Can you take the fee off?",
      },
      {
        speaker: "agent",
        text: "You can ask for a one-time waiver of the fee. I can't remove it myself, so I'm passing you to the billing team. They will review the request.",
      },
      { speaker: "customer", text: "All right. Will I have to explain everything again?" },
      {
        speaker: "agent",
        text: "No. I have written down the reason for them. Is there anything else I can help with today?",
      },
      { speaker: "customer", text: "No, that's all. Thank you." },
      {
        speaker: "agent",
        text: "Thank you for calling Northline Wireless, <PERSON_2>. Have a good day.",
      },
    ],
  },
  T0002: {
    transcript_id: "T0002",
    turns: [
      {
        speaker: "agent",
        text: "Thank you for calling Northline Wireless. This is <PERSON_1>. How can I help?",
      },
      {
        speaker: "customer",
        text: "Hello, my name is <PERSON_2>. My phone has said No Service since this morning.",
      },
      {
        speaker: "agent",
        text: "I'm sorry about that, <PERSON_2>. Let's try a few simple steps. First, please restart the phone: hold the power button, choose Power off, wait a few seconds, then turn it on again.",
      },
      { speaker: "customer", text: "Okay, I did that. It still says No Service." },
      {
        speaker: "agent",
        text: "Thank you. Next, turn on Airplane Mode, wait 10 seconds, then turn it off.",
      },
      { speaker: "customer", text: "One moment. Oh, the bars are back. It's working now." },
      {
        speaker: "agent",
        text: "Good. If it happens again, you can also check for an outage at northline.example/outage.",
      },
      { speaker: "customer", text: "I'll write that down. Thank you for being patient with me." },
      { speaker: "agent", text: "You're welcome. Is there anything else I can help with today?" },
      { speaker: "customer", text: "No, that is all." },
      { speaker: "agent", text: "Thank you for calling Northline Wireless. Goodbye." },
    ],
  },
};

const SUMMARIES: Record<string, CallSummary> = {
  T0001: {
    transcript_id: "T0001",
    summary_bullets: [
      "The customer called about a $5 Late Payment Fee on the bill.",
      "The agent explained that the fee is added when a bill is more than 10 days past its due date.",
      "The customer asked for the fee to be removed.",
      "The agent passed the request to the billing team for a one-time waiver review.",
    ],
    intent: "dispute late fee",
    sentiment: "neutral",
    next_step: "The billing team reviews the request for a one-time waiver.",
    related_articles: [
      { number: 1, title: "Late payment fee", url: `${HELP}/late-payment-fee` },
      { number: 2, title: "Dispute a charge", url: `${HELP}/dispute-a-charge` },
    ],
  },
  T0002: {
    transcript_id: "T0002",
    summary_bullets: [
      "The customer's phone had shown No Service since the morning.",
      "Restarting the phone did not fix it.",
      "Turning Airplane Mode on and off brought the service back.",
      "The agent said where to check for an outage if it happens again.",
    ],
    intent: "phone shows no service",
    sentiment: "positive",
    next_step: "No follow-up is needed. The problem was fixed on the call.",
    related_articles: [{ number: 1, title: "Phone shows no service", url: `${HELP}/no-service` }],
  },
};

// --- Steps, worded as the real API words them ---------------------------------------------

const NO_PERSONAL_DETAILS: Step = {
  stage: "redaction",
  title: "No personal details found",
  detail: "The question was checked before anything was logged.",
  status: "ok",
  tool: null,
  reference: null,
};

const REQUEST_ALLOWED: Step = {
  stage: "input_check",
  title: "Request allowed",
  detail: "Not an account change and not an attempt to override the instructions.",
  status: "ok",
  tool: null,
  reference: null,
};

const CITATIONS_CHECKED: Step = {
  stage: "output_check",
  title: "Citations checked",
  detail: "Every citation points to a retrieved source.",
  status: "ok",
  tool: null,
  reference: null,
};

const ANSWER_CLEAN: Step = {
  stage: "output_check",
  title: "No personal details in the answer",
  detail: "Checked against the sources the answer was written from.",
  status: "ok",
  tool: null,
  reference: null,
};

// --- Redaction of the typed question (a stated name, phone numbers, email addresses) ---------

interface Redacted {
  text: string;
  flags: string[];
  step: Step;
}

const DETAIL_PATTERNS: readonly { kind: string; name: string; pattern: RegExp }[] = [
  {
    kind: "PERSON",
    name: "a name",
    pattern: /(?<=\bname is )[A-Z][a-z]+(?: [A-Z][a-z]+)?/g,
  },
  { kind: "EMAIL_ADDRESS", name: "an email address", pattern: /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g },
  {
    kind: "PHONE_NUMBER",
    name: "a phone number",
    pattern: /(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b/g,
  },
];

function listed(items: string[]): string {
  if (items.length <= 1) {
    return items.join("");
  }
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1] ?? ""}`;
}

function redactQuestion(question: string): Redacted {
  let text = question;
  const found: string[] = [];
  const flags: string[] = [];
  for (const { kind, name, pattern } of DETAIL_PATTERNS) {
    let count = 0;
    text = text.replace(pattern, () => {
      count += 1;
      return `<${kind}_${count}>`;
    });
    if (count > 0) {
      found.push(name);
      flags.push(`pii_in_question:${kind}`);
    }
  }
  if (found.length === 0) {
    return { text, flags, step: NO_PERSONAL_DETAILS };
  }
  const names = listed(found);
  return {
    text,
    flags,
    step: {
      stage: "redaction",
      title: "Personal details removed",
      detail: `${names.charAt(0).toUpperCase()}${names.slice(1)} ${
        found.length === 1 ? "was" : "were"
      } replaced before the question was processed or logged.`,
      status: "notice",
      tool: null,
      reference: null,
    },
  };
}

// --- Answers --------------------------------------------------------------------------------

/** Everything about an answer that does not depend on the redaction of its question. */
type AnswerBody = Omit<AskResponse, "question_as_processed" | "steps" | "guardrail_flags"> & {
  flags: string[];
  /** The steps after the redaction step. */
  steps: Step[];
};

/**
 * An answer exactly as the live model wrote it, kept because it differs from a
 * tidy fixture in two ways the renderer has to handle. Bold is used for a
 * heading-like label and for a stray "or" as well as for facts, and the
 * numbered list is interrupted by bullets, so its second half arrives as a
 * separate list that starts at 3.
 */
function waiverStepsAnswer(): AnswerBody {
  return {
    answer: [
      "The late-payment fee is **$5**. You can ask for a one-time waiver of that fee.",
      "",
      "**How to request a waiver**",
      "",
      "1. Have your account number and the bill with the fee handy.",
      "2. Call Northline support:",
      "- Dial **611** from your Northline phone, **or**",
      "- Call **1-800-555-0199** from any phone.",
      "3. Tell the representative you want a **one-time waiver** of the $5 late-payment fee.",
      "4. The billing team will review your request and, if approved, remove the fee from your bill.",
      "",
      "(Details from the help article [1])",
    ].join("\n"),
    citations: [{ number: 1, title: "Late payment fee", url: `${HELP}/late-payment-fee` }],
    tools_used: ["search_kb"],
    escalated: false,
    flags: [],
    seconds: 2.9,
    trace_id: "tr-mock-waiver-steps",
    steps: [
      REQUEST_ALLOWED,
      {
        stage: "tool",
        title: "Searched the help articles",
        detail: "1 source cited.",
        status: "ok",
        tool: "search_kb",
        reference: null,
      },
      CITATIONS_CHECKED,
      ANSWER_CLEAN,
    ],
  };
}

function lateFeeAnswer(): AnswerBody {
  const citations: Citation[] = [
    { number: 1, title: "Late payment fee", url: `${HELP}/late-payment-fee` },
    { number: 2, title: "If you cannot pay on time", url: `${HELP}/payment-arrangement` },
  ];
  return {
    answer: [
      "The Late Payment Fee is **$5**. It is added when a bill is more than 10 days past its due date. It is a one-time charge, not a recurring one [1].",
      "Yes, it can be waived **one time**. To ask for the waiver:",
      [
        "1. Have the account number and the bill with the fee ready.",
        "2. Call support at **611** from a Northline phone, or **1-800-555-0199** from any phone.",
        "3. Ask for a one-time waiver of the Late Payment Fee. The billing team reviews the request [1].",
      ].join("\n"),
      "A payment arrangement adds up to 14 extra days to pay, and the fee is not charged while it is approved. It has to be asked for before the bill is due [2].",
      "Paying by the due date, or asking for a payment arrangement before it, avoids the fee [1, 2].",
    ].join("\n\n"),
    citations,
    tools_used: ["search_kb"],
    escalated: false,
    flags: ["answer_simplified"],
    seconds: 2.4,
    trace_id: "tr-mock-late-fee",
    steps: [
      REQUEST_ALLOWED,
      {
        stage: "tool",
        title: "Searched the help articles",
        detail: "2 sources cited.",
        status: "ok",
        tool: "search_kb",
        reference: null,
      },
      {
        stage: "output_check",
        title: "Rewritten in plainer words",
        detail: "The first draft was above the reading target.",
        status: "notice",
        tool: null,
        reference: null,
      },
      CITATIONS_CHECKED,
      ANSWER_CLEAN,
    ],
  };
}

function plansAnswer(): AnswerBody {
  return {
    answer: [
      "Three plans cost $25 a month or less:",
      [
        "| Plan | Price a month | Data |",
        "| --- | --- | --- |",
        "| Northline Talk | $15 | None. Talk and text only. |",
        "| Northline Starter 1 | $20 | 1 GB |",
        "| Northline Everyday 5 | $25 | 5 GB |",
      ].join("\n"),
      "All three include unlimited talk and text. None of them includes hotspot data or international calling.",
    ].join("\n\n"),
    citations: [],
    tools_used: ["get_plan_details"],
    escalated: false,
    flags: [],
    seconds: 1.7,
    trace_id: "tr-mock-plans",
    steps: [
      REQUEST_ALLOWED,
      {
        stage: "tool",
        title: "Looked up the plan catalogue",
        detail: "Prices and features come from the catalogue table, not from memory.",
        status: "ok",
        tool: "get_plan_details",
        reference: null,
      },
      ANSWER_CLEAN,
    ],
  };
}

function summaryAnswer(transcriptId: string): AnswerBody {
  const summary = SUMMARIES[transcriptId];
  if (!summary) {
    return {
      answer: `I could not summarize that call. No transcript was found with the id ${transcriptId}`,
      citations: [],
      tools_used: ["summarize_call"],
      escalated: false,
      flags: ["tool_error:summarize_call"],
      seconds: 0.9,
      trace_id: "tr-mock-summary-missing",
      steps: [
        REQUEST_ALLOWED,
        {
          stage: "tool",
          title: "Summarized the call",
          detail: "The lookup failed, and the copilot said so.",
          status: "warning",
          tool: "summarize_call",
          reference: null,
        },
        ANSWER_CLEAN,
      ],
    };
  }
  const related = summary.related_articles
    .map((article) => `${article.title} [${article.number}]`)
    .join(", ");
  return {
    answer: [
      `Call ${summary.transcript_id} was about: ${summary.intent}.`,
      summary.summary_bullets.map((bullet) => `- ${bullet}`).join("\n"),
      `The customer's mood was ${summary.sentiment}.`,
      `Next step: ${summary.next_step}`,
      `Related: ${related}`,
    ].join("\n\n"),
    citations: summary.related_articles,
    tools_used: ["summarize_call"],
    escalated: false,
    flags: [],
    seconds: 3.1,
    trace_id: `tr-mock-summary-${summary.transcript_id.toLowerCase()}`,
    steps: [
      REQUEST_ALLOWED,
      {
        stage: "tool",
        title: "Summarized the call",
        detail: "Read from the redacted transcript only.",
        status: "ok",
        tool: "summarize_call",
        reference: null,
      },
      CITATIONS_CHECKED,
      ANSWER_CLEAN,
    ],
  };
}

function handOffAnswer(): AnswerBody {
  return {
    answer: [
      "I can't refund, credit or waive a charge myself. This needs a human specialist: the billing team has to handle it.",
      `What to tell the customer: "I can't do this myself, so I'm passing you to the billing team. Your reference is ${HANDOFF_REFERENCE}. They will take it from here."`,
    ].join("\n\n"),
    citations: [],
    tools_used: ["escalate_to_human"],
    escalated: true,
    flags: ["account_action_requested"],
    seconds: 0.6,
    trace_id: "tr-mock-hand-off",
    steps: [
      {
        stage: "input_check",
        title: "Account request: handed to a person",
        detail: "The copilot cannot change or look up a customer's account.",
        status: "warning",
        tool: null,
        reference: null,
      },
      {
        stage: "tool",
        title: "Opened a hand-off",
        detail: "A ticket was written for a human specialist, with the reason redacted.",
        status: "ok",
        tool: "escalate_to_human",
        reference: HANDOFF_REFERENCE,
      },
      ANSWER_CLEAN,
    ],
  };
}

/** The plain refusal. It has no trace id, so it also shows an answer without feedback buttons. */
function refusalAnswer(): AnswerBody {
  return {
    answer:
      "I can't help with that. I can answer Northline support questions, look up plans, and summarize a call.",
    citations: [],
    tools_used: [],
    escalated: false,
    flags: ["injection_suspected"],
    seconds: 0.1,
    trace_id: null,
    steps: [
      {
        stage: "input_check",
        title: "Override attempt blocked",
        detail: "The request tried to change the copilot's instructions. No model was called.",
        status: "blocked",
        tool: null,
        reference: null,
      },
      ANSWER_CLEAN,
    ],
  };
}

function noContextAnswer(): AnswerBody {
  return {
    answer:
      "I could not find this in the help articles, so I can't give you a reliable answer. Please pass this question to a human specialist.",
    citations: [],
    tools_used: ["search_kb"],
    escalated: false,
    flags: ["no_context"],
    seconds: 1.3,
    trace_id: "tr-mock-no-context",
    steps: [
      REQUEST_ALLOWED,
      {
        stage: "tool",
        title: "Searched the help articles",
        detail: "No article matched.",
        status: "notice",
        tool: "search_kb",
        reference: null,
      },
      ANSWER_CLEAN,
    ],
  };
}

/** Typing exactly this in mock mode makes the request fail, to show the error state. */
const ERROR_TRIGGER = "/error";

/** Typing exactly this in mock mode leaves the request waiting, to show the pending state. */
const PENDING_TRIGGER = "/pending";

function chooseAnswer(question: string): AnswerBody {
  const transcriptId = /\bT\d{4}\b/i.exec(question)?.[0].toUpperCase();
  if (/\b(?:ignore|disregard|forget)\b.*\binstructions\b|\bsystem prompt\b/i.test(question)) {
    return refusalAnswer();
  }
  if (/\b(?:refund|credit|cancel|unlock)\b/i.test(question)) {
    return handOffAnswer();
  }
  if (transcriptId && /\bsummar/i.test(question)) {
    return summaryAnswer(transcriptId);
  }
  if (/\bplans?\b/i.test(question)) {
    return plansAnswer();
  }
  if (/\bwaiver\b/i.test(question)) {
    return waiverStepsAnswer();
  }
  if (/\blate\b|\bwaive/i.test(question)) {
    return lateFeeAnswer();
  }
  return noContextAnswer();
}

/**
 * The whole answer to a question, worked out at once. The mock API returns it
 * after a delay; the component gallery uses it directly.
 */
export function mockAnswer(question: string): AskResponse {
  const redacted = redactQuestion(question);
  const { flags, steps, ...body } = chooseAnswer(question);
  return {
    ...body,
    question_as_processed: redacted.text,
    guardrail_flags: [...redacted.flags, ...flags],
    steps: [redacted.step, ...steps],
  };
}

/** The fixtures themselves, for the component gallery. */
export {
  CALLS as mockCalls,
  META as mockMeta,
  SUMMARIES as mockSummaries,
  TRANSCRIPTS as mockTranscripts,
};

// --- The mock API ---------------------------------------------------------------------------

/** A page opened on a demo state shows it at once, so a screenshot need not wait. */
const DELAY_SCALE = DEMO === null ? 1 : 0;

function wait(duration: number, signal?: AbortSignal): Promise<void> {
  const milliseconds = duration * DELAY_SCALE;
  return new Promise((resolve, reject) => {
    const aborted = () => new DOMException("The request was cancelled.", "AbortError");
    if (signal?.aborted) {
      reject(aborted());
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(aborted());
    };
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** Never answers. It ends only when the request is cancelled. */
function untilCancelled(signal?: AbortSignal): Promise<never> {
  return new Promise((_resolve, reject) => {
    signal?.addEventListener(
      "abort",
      () => {
        reject(new DOMException("The request was cancelled.", "AbortError"));
      },
      { once: true },
    );
  });
}

function normalizeId(transcriptId: string): string {
  return transcriptId.trim().toUpperCase();
}

function notFound(id: string): ApiError {
  return new ApiError(
    `No transcript was found with the id ${id}. Mock mode has T0001 and T0002 only.`,
    404,
  );
}

export const mockApi: Api = {
  async getMeta(signal) {
    await wait(250, signal);
    return META;
  },

  async getHealth(signal) {
    await wait(150, signal);
    return { status: "ok" };
  },

  async ask(request: AskRequest, signal) {
    // Long enough to show the progress hint moving through its steps.
    await wait(2600, signal);
    const question = request.question.trim();
    if (question === ERROR_TRIGGER) {
      throw new ApiError("The copilot could not answer just now. Please try again.", 502);
    }
    if (question === PENDING_TRIGGER) {
      await untilCancelled(signal);
    }
    return mockAnswer(request.question);
  },

  async listCalls(signal) {
    await wait(450, signal);
    return CALLS;
  },

  async getCall(transcriptId, signal) {
    await wait(400, signal);
    const id = normalizeId(transcriptId);
    const transcript = TRANSCRIPTS[id];
    if (!transcript) {
      throw notFound(id);
    }
    return transcript;
  },

  async summarizeCall(transcriptId, signal) {
    await wait(1600, signal);
    const id = normalizeId(transcriptId);
    const summary = SUMMARIES[id];
    if (!summary) {
      throw notFound(id);
    }
    return summary;
  },

  async sendFeedback(_request, signal) {
    await wait(350, signal);
    return { saved: true };
  },
};
