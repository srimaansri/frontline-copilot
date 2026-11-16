import { useMemo } from "react";

import type { ToolInfo } from "@/api/types";
import { HandoffIcon } from "@/components/icons/glyphs";
import { Byline, Sim } from "@/components/shared/Sim";

import { AnswerFooter } from "./AnswerFooter";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { RecordedQuestions, SimilarQuestionNotice } from "./DemoNotice";
import { HandOffDraftCard } from "./HandOffDraftCard";
import type { AnsweredExchange } from "./useConversation";

function HandOffBanner() {
  return (
    <div className="mt-2 flex items-center gap-3 rounded-box border border-warn bg-warn-tint px-4 py-3 font-semibold text-ink">
      <HandoffIcon className="text-warn" />
      This needs a person. A hand-off was opened.
    </div>
  );
}

export interface AnswerCardProps {
  exchange: AnsweredExchange;
  tools: readonly ToolInfo[];
  /** Whether this answer's sources and steps are the ones on show. */
  selected: boolean;
  /** True when the sources and steps sit in a side panel, not under the answer. */
  sidePanel: boolean;
  /** The id of the element under the answer that holds its sources and steps. */
  detailsId: string;
  activeCitation: number | null;
  onCite: (number: number) => void;
  onToggleDetails: () => void;
  /** Asks another question. Used by the demo's list of recorded questions. */
  onAsk?: (question: string) => void;
}

/**
 * One answer. The card with the cut corner holds only what the copilot wrote.
 * The hand-off, which is the agent's to approve, and the row of tools, timing
 * and feedback sit under it.
 */
export function AnswerCard({
  exchange,
  tools,
  selected,
  sidePanel,
  detailsId,
  activeCitation,
  onCite,
  onToggleDetails,
  onAsk,
}: AnswerCardProps) {
  const { response } = exchange;
  // The hand-off reference, if there is one, is a fact the agent reads out.
  const references = useMemo(
    () => response.steps.flatMap((step) => (step.reference ? [step.reference] : [])),
    [response.steps],
  );
  return (
    <div>
      {response.demo?.shown_for != null && (
        <SimilarQuestionNotice shownFor={response.demo.shown_for} />
      )}
      <Sim selected={selected && sidePanel} bodyClassName="px-5 pt-5 pb-6 sm:px-8 sm:pt-6 sm:pb-8">
        <Byline className="mb-3" />
        <AnswerMarkdown
          markdown={response.answer}
          citations={response.citations}
          references={references}
          activeCitation={activeCitation}
          onCite={onCite}
        />
      </Sim>

      {/* A draft waits for the agent. An answer from before drafts, or from a copilot
          set to write tickets itself, has already opened one. */}
      {response.handoff_draft ? (
        <HandOffDraftCard draft={response.handoff_draft} />
      ) : (
        response.escalated && <HandOffBanner />
      )}

      <div className="mt-3">
        <AnswerFooter
          response={response}
          tools={tools}
          selected={selected}
          sidePanel={sidePanel}
          detailsId={detailsId}
          onToggleDetails={onToggleDetails}
        />
      </div>
      {response.demo && <RecordedQuestions note={response.demo} onAsk={onAsk} />}
    </div>
  );
}
