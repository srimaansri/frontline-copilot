import { useCallback, useEffect, useState } from "react";

import { errorMessage, isAbortError } from "@/api/client";

/** A value that is fetched: on its way, here, or failed with a message to show. */
export type Loadable<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string };

type Settled<T> = Exclude<Loadable<T>, { status: "loading" }>;

interface Outcome<T> {
  load: (signal: AbortSignal) => Promise<T>;
  attempt: number;
  result: Settled<T>;
}

/**
 * Run `load` now and again whenever it changes or `reload` is called.
 *
 * `load` must keep its identity between renders (a module-level function or
 * `useCallback`), because a new function means a new request. A request that
 * is no longer wanted is cancelled.
 */
export function useLoad<T>(load: (signal: AbortSignal) => Promise<T>): {
  state: Loadable<T>;
  reload: () => void;
} {
  const [attempt, setAttempt] = useState(0);
  const [outcome, setOutcome] = useState<Outcome<T> | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).then(
      (data) => {
        setOutcome({ load, attempt, result: { status: "ready", data } });
      },
      (error: unknown) => {
        if (!isAbortError(error)) {
          setOutcome({ load, attempt, result: { status: "error", message: errorMessage(error) } });
        }
      },
    );
    return () => {
      controller.abort();
    };
  }, [load, attempt]);

  const reload = useCallback(() => {
    setAttempt((current) => current + 1);
  }, []);

  // The outcome of an earlier request is never shown for the current one.
  const current = outcome?.load === load && outcome.attempt === attempt;
  return { state: current ? outcome.result : { status: "loading" }, reload };
}
