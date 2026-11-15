import type {
  Api,
  AskRequest,
  AskResponse,
  CallListItem,
  CallSummary,
  CallTranscript,
  ErrorBody,
  FeedbackRequest,
  FeedbackResponse,
  Health,
  Meta,
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

const httpApi: Api = {
  getMeta: (signal) => request<Meta>("/meta", { signal }),
  getHealth: (signal) => request<Health>("/health", { signal }),
  ask: (body: AskRequest, signal) => request<AskResponse>("/ask", post(body, signal)),
  listCalls: (signal) => request<CallListItem[]>("/calls", { signal }),
  getCall: (transcriptId, signal) =>
    request<CallTranscript>(`/calls/${encodeURIComponent(transcriptId)}`, { signal }),
  summarizeCall: (transcriptId, signal) =>
    request<CallSummary>(`/calls/${encodeURIComponent(transcriptId)}/summary`, {
      method: "POST",
      signal,
    }),
  sendFeedback: (body: FeedbackRequest, signal) =>
    request<FeedbackResponse>("/feedback", post(body, signal)),
};

/** The fixtures are loaded on first use, so a normal build never downloads them. */
function mockApi(): Api {
  const load = async (): Promise<Api> => (await import("./mock")).mockApi;
  return {
    getMeta: async (signal) => (await load()).getMeta(signal),
    getHealth: async (signal) => (await load()).getHealth(signal),
    ask: async (body, signal) => (await load()).ask(body, signal),
    listCalls: async (signal) => (await load()).listCalls(signal),
    getCall: async (transcriptId, signal) => (await load()).getCall(transcriptId, signal),
    summarizeCall: async (transcriptId, signal) =>
      (await load()).summarizeCall(transcriptId, signal),
    sendFeedback: async (body, signal) => (await load()).sendFeedback(body, signal),
  };
}

/** The one API client. Every component talks to the server through this. */
export const api: Api = USE_MOCK ? mockApi() : httpApi;
