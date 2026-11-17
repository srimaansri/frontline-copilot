import type { ToolInfo } from "@/api/types";
import { ErrorNotice } from "@/components/shared/ErrorNotice";

import { AnswerCard } from "./AnswerCard";
import { AnswerDetails } from "./AnswerDetails";
import { ProgressHint } from "./ProgressHint";
import { QuestionBubble } from "./QuestionBubble";
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
  /** Asks another question, from the demo's list of recorded ones. */
  onAsk: (question: string) => void;
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
  onAsk,
}: ExchangeItemProps) {
  const questionId = `${exchange.id}-question`;
  const detailsId = `${exchange.id}-details`;

  return (
    <article id={exchange.id} aria-labelledby={questionId} className="flex scroll-mt-6 flex-col">
      <QuestionBubble
        id={questionId}
        question={exchange.question}
        processed={exchange.status === "done" ? exchange.response.question_as_processed : null}
      />

      <div className="mt-5 w-full max-w-3xl self-start">
        {exchange.status === "pending" && <ProgressHint stage={exchange.stage} />}
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
              onAsk={onAsk}
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
