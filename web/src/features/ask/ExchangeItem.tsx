import type { ToolInfo } from "@/api/types";
import { PrivacyIcon } from "@/components/icons/glyphs";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { findRemovedDetails } from "@/lib/placeholders";

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
  // Where the removed details sat in the question as typed, to underline them.
  const removed = showProcessed ? findRemovedDetails(exchange.question.trim(), processed) : null;

  return (
    <article id={exchange.id} aria-labelledby={questionId} className="flex scroll-mt-6 flex-col">
      {/* The agent's own words: soft-square corners, on the sunken tone. */}
      <div className="flex max-w-[min(100%,40rem)] animate-rise flex-col items-end gap-1.5 self-end">
        <h2 className="text-label font-bold tracking-[0.01em] text-ink-2">Agent</h2>
        <p
          id={questionId}
          className="rounded-box bg-sunken px-[18px] py-3.5 text-read break-words whitespace-pre-wrap text-ink"
        >
          {removed === null
            ? exchange.question
            : removed.map((part, index) =>
                part.kind === "removed" ? (
                  // The parts of one text never reorder, so the position is a stable key.
                  <span key={index} className="pii" title="Replaced before processing">
                    {part.value}
                  </span>
                ) : (
                  part.value
                ),
              )}
        </p>
        {showProcessed && (
          <div className="grid animate-fade grid-cols-[20px_minmax(0,1fr)] gap-2 self-stretch px-[18px] pt-0.5 leading-[1.7] text-ink-2">
            <PrivacyIcon size={16} className="mt-[5px] text-notice" />
            <p className="break-words">
              As processed: <PlaceholderText text={processed} />
            </p>
          </div>
        )}
      </div>

      <div className="mt-5 w-full max-w-[45.5rem] self-start">
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
              <div
                id={detailsId}
                className="mt-3 animate-rise rounded-box border border-line bg-sunken px-5 py-6"
              >
                <AnswerDetails response={exchange.response} tools={tools} highlight={highlight} />
              </div>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
