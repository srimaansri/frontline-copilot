import type {
  Api,
  AskRequest,
  AskResponse,
  CallFindings,
  CallListItem,
  CallSummary,
  CallTranscript,
  CallWrapUp,
  ErrorBody,
  FeedbackRequest,
  FeedbackResponse,
  HandOffRequest,
  HandOffTicket,
  Health,
  Meta,
  SavedWrapUp,
  StageEvent,
  WrapUpFields,
} from "./types";

/** True when the build answers from fixtures. Set with `VITE_USE_MOCK=1`. */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === "1";

/** A failed request, with a message that is safe to show as it is. */
export class ApiError extends Error {
  /** The HTTP status, or 0 when the server could not be reached at all. */
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** True when a request ended because its caller cancelled it. */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** The words to show for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Something went wrong. Please try again.";
}

function isErrorBody(value: unknown): value is ErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "string"
  );
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (isErrorBody(body)) {
      return body.detail;
    }
  } catch {
    // The body was not JSON. Fall through to the plain message.
  }
  return `The request failed (${response.status}). Please try again.`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers({ Accept: "application/json" });
  if (init.body != null) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ApiError("The service could not be reached. Check the connection and try again.", 0);
  }
  if (!response.ok) {
    throw new ApiError(await readDetail(response), response.status);
  }
  return (await response.json()) as T;
}

function post(body: unknown, signal?: AbortSignal): RequestInit {
  return { method: "POST", body: JSON.stringify(body), signal };
}

/** One server-sent event: its name and its data, read as JSON. */
function readEvent(block: string): { name: string; data: unknown } | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice(5).trim());
    }
  }
  if (data.length === 0) {
    return null;
  }
  try {
    return { name, data: JSON.parse(data.join("\n")) as unknown };
  } catch {
    return null;
  }
}

/**
 * Ask over the streaming endpoint: each stage is passed to `onStage` as it
 * starts, and the answer is the last event. A server without the endpoint is
 * asked the ordinary way, so the answer never depends on the stream.
 */
async function askStreaming(
  body: AskRequest,
  signal: AbortSignal | undefined,
  onStage: (event: StageEvent) => void,
): Promise<AskResponse> {
  let response: Response;
  try {
    response = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ApiError("The service could not be reached. Check the connection and try again.", 0);
  }
  if (response.status === 404 || response.status === 405 || response.body === null) {
    return request<AskResponse>("/ask", post(body, signal));
  }
  if (!response.ok) {
    throw new ApiError(await readDetail(response), response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffered += decoder.decode(value, { stream: !done });
    const blocks = buffered.split("\n\n");
    buffered = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = readEvent(block);
      if (event === null) {
        continue;
      }
      if (event.name === "stage") {
        onStage(event.data as StageEvent);
      } else if (event.name === "answer") {
        return event.data as AskResponse;
      } else if (event.name === "error") {
        const detail = (event.data as { detail?: unknown }).detail;
        throw new ApiError(
          typeof detail === "string" ? detail : "The copilot could not answer just now.",
          502,
        );
      }
    }
    if (done) {
      throw new ApiError("The answer was cut off before it arrived. Please try again.", 502);
    }
  }
}

const httpApi: Api = {
  getMeta: (signal) => request<Meta>("/meta", { signal }),
  getHealth: (signal) => request<Health>("/health", { signal }),
  ask: (body: AskRequest, signal, onStage) =>
    onStage ? askStreaming(body, signal, onStage) : request<AskResponse>("/ask", post(body, signal)),
  listCalls: (signal) => request<CallListItem[]>("/calls", { signal }),
  getCall: (transcriptId, signal) =>
    request<CallTranscript>(`/calls/${encodeURIComponent(transcriptId)}`, { signal }),
  getFindings: (transcriptId, signal) =>
    request<CallFindings>(`/calls/${encodeURIComponent(transcriptId)}/findings`, { signal }),
  summarizeCall: (transcriptId, signal) =>
    request<CallSummary>(`/calls/${encodeURIComponent(transcriptId)}/summary`, {
      method: "POST",
      signal,
    }),
  draftWrapUp: (transcriptId, signal) =>
    request<CallWrapUp>(`/calls/${encodeURIComponent(transcriptId)}/wrapup`, {
      method: "POST",
      signal,
    }),
  saveWrapUp: (transcriptId, body: WrapUpFields, signal) =>
    request<SavedWrapUp>(
      `/calls/${encodeURIComponent(transcriptId)}/wrapup/save`,
      post(body, signal),
    ),
  openHandOff: (body: HandOffRequest, signal) =>
    request<HandOffTicket>("/handoffs", post(body, signal)),
  sendFeedback: (body: FeedbackRequest, signal) =>
    request<FeedbackResponse>("/feedback", post(body, signal)),
};

/** The fixtures are loaded on first use, so a normal build never downloads them. */
function mockApi(): Api {
  const load = async (): Promise<Api> => (await import("./mock")).mockApi;
  return {
    getMeta: async (signal) => (await load()).getMeta(signal),
    getHealth: async (signal) => (await load()).getHealth(signal),
    ask: async (body, signal, onStage) => (await load()).ask(body, signal, onStage),
    listCalls: async (signal) => (await load()).listCalls(signal),
    getCall: async (transcriptId, signal) => (await load()).getCall(transcriptId, signal),
    getFindings: async (transcriptId, signal) => (await load()).getFindings(transcriptId, signal),
    summarizeCall: async (transcriptId, signal) =>
      (await load()).summarizeCall(transcriptId, signal),
    draftWrapUp: async (transcriptId, signal) => (await load()).draftWrapUp(transcriptId, signal),
    saveWrapUp: async (transcriptId, body, signal) =>
      (await load()).saveWrapUp(transcriptId, body, signal),
    openHandOff: async (body, signal) => (await load()).openHandOff(body, signal),
    sendFeedback: async (body, signal) => (await load()).sendFeedback(body, signal),
  };
}

/** The one API client. Every component talks to the server through this. */
export const api: Api = USE_MOCK ? mockApi() : httpApi;
