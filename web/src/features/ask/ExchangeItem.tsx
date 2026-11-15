import { ShieldCheck } from "lucide-react";

import type { ToolInfo } from "@/api/types";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { Card } from "@/components/ui/card";

import { AnswerCard } from "./AnswerCard";
import { AnswerDetails } from "./AnswerDetails";
import { ProgressHint } from "./ProgressHint";
import type { SourceHighlight } from "./SourceList";
import type { Exchange } from "./useConversation";

export interface ExchangeItemProps {
  exchange: Exchange;
  tools: readonly ToolInfo[];
  selected: boolean;
  /** True when sources and steps sit in a side panel, not under the answer. */
  sidePanel: boolean;
  /** The source to highlight, when a citation of this exchange was clicked. */
  highlight: SourceHighlight | null;
  onCite: (number: number) => void;
  onToggleDetails: () => void;
  onRetry: () => void;
}

/** One question with whatever came of it: a wait, an answer, or an error to retry. */
export function ExchangeItem({
  exchange,
  tools,
  selected,
  sidePanel,
  highlight,
  onCite,
  onToggleDetails,
  onRetry,
}: ExchangeItemProps) {
  const questionId = `${exchange.id}-question`;
  const detailsId = `${exchange.id}-details`;
  const processed =
    exchange.status === "done" ? exchange.response.question_as_processed.trim() : null;
  const showProcessed = processed !== null && processed !== exchange.question.trim();

  return (
    <article id={exchange.id} aria-labelledby={questionId} className="scroll-mt-6">
      <div className="flex animate-rise flex-col items-end">
        <h2 className="sr-only">Question</h2>
        <p
          id={questionId}
          className="max-w-[min(90%,40rem)] rounded-2xl rounded-br-md border bg-surface-muted px-4 py-2.5 text-[1.0625rem] leading-relaxed break-words whitespace-pre-wrap text-fg"
        >
          {exchange.question}
        </p>
        {showProcessed && (
          <div className="mt-2 flex max-w-[min(90%,40rem)] animate-fade items-start gap-2 text-sm leading-relaxed text-fg-muted">
            <ShieldCheck aria-hidden="true" className="mt-[3px] size-4 shrink-0 text-fg-subtle" />
            <p className="min-w-0 break-words">
              <span className="font-medium text-fg-subtle">As processed: </span>
              <PlaceholderText text={processed} />
            </p>
          </div>
        )}
      </div>

      <div className="mt-4">
        {exchange.status === "pending" && <ProgressHint />}
        {exchange.status === "error" && (
          <ErrorNotice className="animate-rise" message={exchange.message} onRetry={onRetry} />
        )}
        {exchange.status === "done" && (
          <div className="animate-rise">
            <h2 className="sr-only">Answer</h2>
            <AnswerCard
              exchange={exchange}
              tools={tools}
              selected={selected}
              sidePanel={sidePanel}
              detailsId={detailsId}
              activeCitation={highlight?.number ?? null}
              onCite={onCite}
              onToggleDetails={onToggleDetails}
            />
            {!sidePanel && selected && (
              <Card id={detailsId} className="mt-3 animate-rise p-5">
                <AnswerDetails response={exchange.response} tools={tools} highlight={highlight} />
              </Card>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
