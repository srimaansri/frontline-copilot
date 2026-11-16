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

export interface AskResponse {
  /** Markdown. May contain citation markers such as [1] or [1, 2]. */
  answer: string;
  /** The question after personal details were replaced with placeholders. */
  question_as_processed: string;
  citations: Citation[];
  tools_used: string[];
  escalated: boolean;
  guardrail_flags: string[];
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
  summarizeCall(transcriptId: string, signal?: AbortSignal): Promise<CallSummary>;
  sendFeedback(request: FeedbackRequest, signal?: AbortSignal): Promise<FeedbackResponse>;
}
