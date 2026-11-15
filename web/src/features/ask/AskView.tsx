import { useEffect, useRef, useState } from "react";

import type { Meta, ToolInfo } from "@/api/types";
import type { Loadable } from "@/hooks/useLoad";
import { REDUCED_MOTION, useMediaQuery, WIDE_SCREEN } from "@/hooks/useMediaQuery";

import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";
import { ExchangeItem } from "./ExchangeItem";
import { InspectorPanel } from "./InspectorPanel";
import type { SourceHighlight } from "./SourceList";
import { useConversation } from "./useConversation";

const NO_TOOLS: readonly ToolInfo[] = [];

/** A highlighted source, and the exchange it belongs to. */
interface ExchangeHighlight extends SourceHighlight {
  exchangeId: string;
}

export interface AskViewProps {
  meta: Loadable<Meta>;
  onRetryMeta: () => void;
}

/**
 * The Ask view: the conversation, the question box pinned under it and, on
 * wide screens, a panel with the sources and steps of the selected answer.
 * On narrow screens those sit under the answer instead.
 */
export function AskView({ meta, onRetryMeta }: AskViewProps) {
  const { exchanges, waiting, ask, retry } = useConversation();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<ExchangeHighlight | null>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const sidePanel = useMediaQuery(WIDE_SCREEN);
  const reducedMotion = useMediaQuery(REDUCED_MOTION);

  const tools = meta.status === "ready" ? meta.data.tools : NO_TOOLS;
  const latest = exchanges.at(-1);
  const latestId = latest?.id;
  const latestStatus = latest?.status;

  // Start with the cursor in the question box, on first load and after "New conversation".
  // Not on touch screens, where that would open the on-screen keyboard unasked.
  useEffect(() => {
    if (window.matchMedia("(pointer: fine)").matches) {
      composerInput.current?.focus();
    }
  }, []);

  // Bring the newest question to the top when it is asked and when it is answered.
  useEffect(() => {
    if (latestId !== undefined && latestStatus !== undefined) {
      document
        .getElementById(latestId)
        ?.scrollIntoView({ block: "start", behavior: reducedMotion ? "auto" : "smooth" });
    }
  }, [latestId, latestStatus, reducedMotion]);

  const submit = (question: string): boolean => {
    const id = ask(question);
    if (id === null) {
      return false;
    }
    setSelectedId(id);
    return true;
  };

  const pick = (question: string) => {
    // The example cards go away once a question is asked, so focus moves to the question box.
    if (submit(question)) {
      composerInput.current?.focus();
    }
  };

  const cite = (exchangeId: string, number: number) => {
    setSelectedId(exchangeId);
    setHighlight((current) => ({ exchangeId, number, tick: (current?.tick ?? 0) + 1 }));
  };

  const toggleDetails = (exchangeId: string) => {
    // The side panel always shows something. Under an answer, the details can be closed.
    setSelectedId((current) => (!sidePanel && current === exchangeId ? null : exchangeId));
  };

  const selected = exchanges.find((exchange) => exchange.id === selectedId) ?? null;
  const highlightFor = (exchangeId: string): SourceHighlight | null =>
    highlight?.exchangeId === exchangeId ? highlight : null;

  let announcement = "";
  if (latestStatus === "done") {
    announcement = "The answer is ready.";
  } else if (latestStatus === "error") {
    announcement = "The question could not be answered.";
  }

  return (
    <div className="flex h-full min-h-0">
      <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col">
        <h1 className="sr-only">Ask the copilot</h1>
        <p role="status" className="sr-only">
          {announcement}
        </p>
        <div className="scroll-area min-h-0 flex-1">
          {exchanges.length === 0 ? (
            <EmptyState meta={meta} onRetryMeta={onRetryMeta} onPick={pick} />
          ) : (
            <div className="mx-auto max-w-3xl space-y-10 px-4 pt-8 pb-10 sm:px-6">
              {exchanges.map((exchange) => (
                <ExchangeItem
                  key={exchange.id}
                  exchange={exchange}
                  tools={tools}
                  selected={exchange.id === selectedId}
                  sidePanel={sidePanel}
                  highlight={highlightFor(exchange.id)}
                  onCite={(number) => {
                    cite(exchange.id, number);
                  }}
                  onToggleDetails={() => {
                    toggleDetails(exchange.id);
                  }}
                  onRetry={() => {
                    retry(exchange.id);
                  }}
                />
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0 px-4 pt-2 pb-3 sm:px-6">
          <div className="mx-auto max-w-3xl">
            <Composer inputRef={composerInput} onSend={submit} waiting={waiting} />
          </div>
        </div>
      </section>

      {sidePanel && exchanges.length > 0 && (
        <InspectorPanel
          exchange={selected}
          tools={tools}
          highlight={selected ? highlightFor(selected.id) : null}
        />
      )}
    </div>
  );
}
