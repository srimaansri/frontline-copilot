import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "@/api/client";
import type { AskResponse, ChatTurn, StageEvent } from "@/api/types";

/** One question and what came of it. */
export type Exchange =
  /** `stage` is what the copilot is doing now, once the server has said. */
  | { id: string; question: string; status: "pending"; stage?: StageEvent }
  | { id: string; question: string; status: "error"; message: string }
  | { id: string; question: string; status: "done"; response: AskResponse };

export type AnsweredExchange = Extract<Exchange, { status: "done" }>;

// The limits the server sets on a request.
export const MAX_QUESTION_CHARS = 2000;
const MAX_HISTORY_EXCHANGES = 20;
const MAX_TURN_CHARS = 8000;

/** The id of the exchange for a question the conversation opens with. */
export const FIRST_EXCHANGE_ID = "exchange-0";

/** The answered exchanges as the server wants them: the newest twenty, oldest first. */
function toHistory(exchanges: readonly Exchange[]): ChatTurn[] {
  return exchanges
    .filter((exchange) => exchange.status === "done")
    .slice(-MAX_HISTORY_EXCHANGES)
    .flatMap((exchange): ChatTurn[] => [
      { role: "user", content: exchange.question.slice(0, MAX_TURN_CHARS) },
      { role: "assistant", content: exchange.response.answer.slice(0, MAX_TURN_CHARS) },
    ]);
}

export interface Conversation {
  exchanges: Exchange[];
  /** True while a question is waiting for its answer. */
  waiting: boolean;
  /** Send a question. Returns the id of its exchange, or null if one is still waiting. */
  ask: (question: string) => string | null;
  /** Send the question of a failed exchange again. */
  retry: (id: string) => void;
}

/**
 * The conversation on the Ask view. A failed question stays in the list with
 * its text, so it can be sent again and is never lost.
 *
 * @param firstQuestion A question to open with and send at once. Only the
 *   `?demo=` hook of mock mode passes one. Its exchange is `FIRST_EXCHANGE_ID`.
 */
export function useConversation(firstQuestion: string | null = null): Conversation {
  const [exchanges, setExchanges] = useState<Exchange[]>(() =>
    firstQuestion === null
      ? []
      : [{ id: FIRST_EXCHANGE_ID, question: firstQuestion, status: "pending" }],
  );
  const nextId = useRef(1);
  const controller = useRef<AbortController | null>(null);

  const waiting = exchanges.some((exchange) => exchange.status === "pending");

  const send = useCallback((id: string, question: string, earlier: readonly Exchange[]) => {
    const current = new AbortController();
    controller.current = current;
    const settle = (settled: Exchange) => {
      setExchanges((list) => list.map((exchange) => (exchange.id === id ? settled : exchange)));
    };
    const onStage = (stage: StageEvent) => {
      setExchanges((list) =>
        list.map((exchange) =>
          exchange.id === id && exchange.status === "pending" ? { ...exchange, stage } : exchange,
        ),
      );
    };
    api.ask({ question, history: toHistory(earlier) }, current.signal, onStage).then(
      (response) => {
        settle({ id, question, status: "done", response });
      },
      (error: unknown) => {
        if (!isAbortError(error)) {
          settle({ id, question, status: "error", message: errorMessage(error) });
        }
      },
    );
  }, []);

  // Send the opening question, if there is one, and cancel whatever is in flight on the way out.
  useEffect(() => {
    if (firstQuestion !== null) {
      send(FIRST_EXCHANGE_ID, firstQuestion, []);
    }
    return () => {
      controller.current?.abort();
    };
  }, [firstQuestion, send]);

  const ask = useCallback(
    (question: string): string | null => {
      const text = question.trim();
      if (waiting || text === "") {
        return null;
      }
      const id = `exchange-${nextId.current}`;
      nextId.current += 1;
      setExchanges((list) => [...list, { id, question: text, status: "pending" }]);
      send(id, text, exchanges);
      return id;
    },
    [exchanges, send, waiting],
  );

  const retry = useCallback(
    (id: string) => {
      const index = exchanges.findIndex((exchange) => exchange.id === id);
      const failed = exchanges[index];
      if (waiting || failed?.status !== "error") {
        return;
      }
      const { question } = failed;
      setExchanges((list) =>
        list.map((exchange) => (exchange.id === id ? { id, question, status: "pending" } : exchange)),
      );
      send(id, question, exchanges.slice(0, index));
    },
    [exchanges, send, waiting],
  );

  return { exchanges, waiting, ask, retry };
}
