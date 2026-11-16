import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, errorMessage, isAbortError } from "@/api/client";
import type { AssistState } from "@/api/types";

type Settled = { status: "ready"; data: AssistState } | { status: "error"; message: string };

/** What the assist panel is given: the newest state there is, and what is still on its way. */
export interface Assist {
  /** The state of the latest turn that has been read, up to the turn on show. Null: none yet. */
  state: AssistState | null;
  /** True while the turn on show has been asked about and not answered. */
  pending: boolean;
  /** Why there is nothing newer to show, when the last request failed. */
  problem: string | null;
  /** Ask again about the turn on show. Absent when asking again cannot help. */
  retry?: () => void;
}

/**
 * Call assist for one call, asked turn by turn as the replay moves on.
 *
 * The server holds no session, so each turn is one request, and what comes
 * back is kept here by turn: going back, or playing the call again, asks
 * nothing twice. A request is not cancelled when the replay moves past its
 * turn, because its answer is still the newest there is until the next one
 * arrives. A call the server has no assist for (the demo, for a call that was
 * not recorded) is asked about once and not again.
 */
export function useAssist(transcriptId: string, turn: number): Assist {
  const [results, setResults] = useState<Record<number, Settled>>({});
  // Set when the server says there is no assist for this call at all.
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const asked = useRef(new Set<string>());
  const controller = useRef<AbortController | null>(null);

  // One controller for every request of this call. It is renewed when the effect
  // runs again, so a request cancelled on the way out is asked again on the way in.
  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    asked.current = new Set();
    return () => {
      current.abort();
    };
  }, [transcriptId]);

  useEffect(() => {
    const key = `${turn}:${attempt}`;
    if (unavailable !== null || asked.current.has(key)) {
      return;
    }
    asked.current.add(key);
    api.assistCall(transcriptId, turn, controller.current?.signal).then(
      (data) => {
        setResults((current) => ({ ...current, [turn]: { status: "ready", data } }));
      },
      (error: unknown) => {
        if (isAbortError(error)) {
          return;
        }
        if (error instanceof ApiError && error.status === 404) {
          setUnavailable(error.message);
          return;
        }
        setResults((current) => ({
          ...current,
          [turn]: { status: "error", message: errorMessage(error) },
        }));
      },
    );
  }, [transcriptId, turn, attempt, unavailable]);

  const retry = useCallback(() => {
    // The failed answer is dropped, so the turn counts as asked and not yet answered.
    setResults((current) =>
      Object.fromEntries(Object.entries(current).filter(([key]) => Number(key) !== turn)),
    );
    setAttempt((current) => current + 1);
  }, [turn]);

  if (unavailable !== null) {
    return { state: null, pending: false, problem: unavailable };
  }
  let state: AssistState | null = null;
  for (let index = turn; index >= 0 && state === null; index -= 1) {
    const result = results[index];
    if (result?.status === "ready") {
      state = result.data;
    }
  }
  const here = results[turn];
  return {
    state,
    pending: here === undefined,
    problem: here?.status === "error" ? here.message : null,
    retry: here?.status === "error" ? retry : undefined,
  };
}
