/** The shapes exchanged with the Frontline Copilot API. All bodies are JSON. */

export type ToolName = "search_kb" | "get_plan_details" | "summarize_call" | "escalate_to_human";

export interface ToolInfo {
  /** A tool's identifier. Usually a `ToolName`, but the server may add tools. */
  name: string;
  label: string;
}

export interface ExampleQuestion {
  question: string;
  tool: string;
  hint: string;
}

export interface SearchSettings {
  chunk_config: string;
  query_type: string;
  top_k: number;
}

export interface Meta {
  app_name: string;
  carrier: string;
  model: string;
  prompt_version: string;
  search: SearchSettings;
  tracing: boolean;
  tools: ToolInfo[];
  examples: ExampleQuestion[];
  disclaimer: string;
  /**
   * Set only by the demo, which replays recordings of the live copilot: when the
   * recording was made (UTC) and the commit of the code that produced it.
   */
  recorded?: { at: string; git_sha: string };
}

export type ChatRole = "user" | "assistant";

export interface ChatTurn {
  role: ChatRole;
  content: string;
}

export interface AskRequest {
  question: string;
  history: ChatTurn[];
}

export interface Citation {
  number: number;
  title: string;
  url: string;
}

export type StepStage = "redaction" | "input_check" | "tool" | "output_check";

export type StepStatus = "ok" | "notice" | "warning" | "blocked";

export interface Step {
  stage: StepStage;
  title: string;
  detail: string;
  status: StepStatus;
  tool: string | null;
  /** The ticket reference on the hand-off step, such as "ESC-B695DE84". Null on every other step. */
  reference: string | null;
}

export type Urgency = "low" | "normal" | "high";

/** A hand-off the copilot drafted. Nothing is written until the agent opens it. */
export interface HandOffDraft {
  /** "billing", "plan_change", "account_access", "device", "cancellation" or "other". */
  category: string;
  urgency: Urgency;
  /** What is needed, with personal details already replaced. */
  reason: string;
  /** Who would pick it up, such as "the billing team". */
  team: string;
}

/** What the agent approved, as sent to the server. */
export interface HandOffRequest {
  reason: string;
  category: string;
  urgency: Urgency;
}

/** A hand-off that was opened. */
export interface HandOffTicket {
  /** The reference to give the customer, such as "ESC-B695DE84". */
  ticket_id: string;
  category: string;
  urgency: Urgency;
  reason: string;
  /** What to tell the customer. */
  agent_script: string;
  /** False when the ticket could not be written and the transfer must be made by hand. */
  recorded: boolean;
}

/** The model work one answer took, as the copilot counted it. */
export interface Usage {
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  /** Calls whose reply carried no token count. When not zero, the totals are a lower bound. */
  calls_without_counts: number;
}

export interface AskResponse {
  /** Markdown. May contain citation markers such as [1] or [1, 2]. */
  answer: string;
  /** The question after personal details were replaced with placeholders. */
  question_as_processed: string;
  citations: Citation[];
  tools_used: string[];
  escalated: boolean;
  guardrail_flags: string[];
  /** A hand-off waiting for the agent to approve it. Absent or null when there is none. */
  handoff_draft?: HandOffDraft | null;
  /** Absent in a recording made before it was counted. */
  usage?: Usage;
  seconds: number;
  trace_id: string | null;
  steps: Step[];
}

/** What the copilot is doing at one moment, sent while an answer is on its way. */
export interface StageEvent {
  /** "redaction", "input_check", "model", "tool", "answer", "simplify" or "output_check". */
  stage: string;
  /** The words to show, such as "Searching the help articles". */
  label: string;
  /** The tool that is running, on a "tool" stage. */
  tool: string | null;
  /** Seconds from the start of the request to the start of this stage. */
  at: number;
}

export type Resolution = "resolved" | "escalated" | "unresolved";

export interface CallListItem {
  transcript_id: string;
  category: string;
  resolution: Resolution;
  /**
   * The rules the rule check fired on this call, by name. Empty when none fired.
   * Null or absent when the call has not been checked, which is not the same thing.
   */
  findings?: string[] | null;
}

/** One thing the rule check found in a call. It holds no text from the call. */
export interface RuleFinding {
  /** The rule's name, such as "card_read_back". */
  rule: string;
  /** The turn it points at, counted from 0 in the call's turns. */
  turn_index: number;
  /** The checker's own fixed sentence about that turn. */
  reason: string;
}

/**
 * What the rule check found in one call. An empty list means no rule fired, not
 * that the call is clean: the rules miss some breaches.
 */
export interface CallFindings {
  transcript_id: string;
  findings: RuleFinding[];
  /** The names of the rules that were run. */
  rules_checked: string[];
}

export type Speaker = "agent" | "customer";

export interface TranscriptTurn {
  speaker: Speaker;
  text: string;
}

export interface CallTranscript {
  transcript_id: string;
  turns: TranscriptTurn[];
}

export type Sentiment = "positive" | "neutral" | "negative";

export interface CallSummary {
  transcript_id: string;
  summary_bullets: string[];
  intent: string;
  sentiment: Sentiment;
  next_step: string;
  related_articles: Citation[];
}

/** Who takes the next step after a call: the customer, the agent who took it, or another team. */
export type FollowUpOwner = "customer" | "agent" | "team";

export interface FollowUp {
  owner: FollowUpOwner;
  /** What the next step is, in one sentence. */
  action: string;
}

/** What the agent can change in a wrap-up, and what is saved. */
export interface WrapUpFields {
  /** How the call ended. The copilot works it out from the conversation. */
  disposition: Resolution;
  /** What the call was about: one of the ten call categories, such as "billing". */
  category: string;
  /** What happened, one short line each. */
  notes: string[];
  /** What the agent told the customer would happen after the call. May be empty. */
  promises: string[];
  /** Null when nothing is left to do. */
  follow_up: FollowUp | null;
  sentiment: Sentiment;
}

/** The after-call record the copilot drafted. Nothing is saved until the agent saves it. */
export interface CallWrapUp extends WrapUpFields {
  transcript_id: string;
  related_articles: Citation[];
}

/** A wrap-up as it was stored, with personal details replaced in every line. */
export interface SavedWrapUp extends WrapUpFields {
  /** The reference of the saved record, such as "WRP-4F2A91C7". */
  wrapup_id: string;
  transcript_id: string;
  /** False when the record could not be written. */
  recorded: boolean;
  /**
   * When it was saved, in UTC, such as "2026-11-16T14:02:11Z". On a record read
   * back from the server. The reply to a save does not carry it. Who saved it is
   * not here: the server does not record that.
   */
  saved_at?: string;
}

export interface FeedbackRequest {
  trace_id: string;
  helpful: boolean;
}

export interface FeedbackResponse {
  saved: boolean;
}

export interface Health {
  status: string;
}

/** The body of every 4xx and 5xx response. */
export interface ErrorBody {
  detail: string;
}

/** Everything the interface asks of the server. Implemented over HTTP and by the mock. */
export interface Api {
  getMeta(signal?: AbortSignal): Promise<Meta>;
  getHealth(signal?: AbortSignal): Promise<Health>;
  /** `onStage` is called as each stage of the answer starts, if the server reports them. */
  ask(
    request: AskRequest,
    signal?: AbortSignal,
    onStage?: (event: StageEvent) => void,
  ): Promise<AskResponse>;
  listCalls(signal?: AbortSignal): Promise<CallListItem[]>;
  getCall(transcriptId: string, signal?: AbortSignal): Promise<CallTranscript>;
  /** Run the rule check on one call. Plain rules on the redacted turns, with no model call. */
  getFindings(transcriptId: string, signal?: AbortSignal): Promise<CallFindings>;
  summarizeCall(transcriptId: string, signal?: AbortSignal): Promise<CallSummary>;
  /** Draft the after-call record of a call. It stores nothing. */
  draftWrapUp(transcriptId: string, signal?: AbortSignal): Promise<CallWrapUp>;
  /** Store the wrap-up the agent approved. This is the only call that saves one. */
  saveWrapUp(
    transcriptId: string,
    request: WrapUpFields,
    signal?: AbortSignal,
  ): Promise<SavedWrapUp>;
  /** The wrap-up most recently saved for a call, as it was stored. Null when none was. */
  getSavedWrapUp(transcriptId: string, signal?: AbortSignal): Promise<SavedWrapUp | null>;
  /** Write the hand-off the agent approved. This is the only call that opens a ticket. */
  openHandOff(request: HandOffRequest, signal?: AbortSignal): Promise<HandOffTicket>;
  sendFeedback(request: FeedbackRequest, signal?: AbortSignal): Promise<FeedbackResponse>;
}
