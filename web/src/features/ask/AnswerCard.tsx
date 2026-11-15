import { useMemo } from "react";

import type { ToolInfo } from "@/api/types";
import { ChevronDownIcon, HandoffIcon, PanelIcon } from "@/components/icons/glyphs";
import { Byline, Sim } from "@/components/shared/Sim";
import { ToolIcon } from "@/components/shared/ToolIcon";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatSeconds } from "@/lib/format";
import { toolLabel } from "@/lib/tools";

import { AnswerMarkdown } from "./AnswerMarkdown";
import { FeedbackButtons } from "./FeedbackButtons";
import type { AnsweredExchange } from "./useConversation";

function HandOffBanner() {
  return (
    <div className="mt-2 flex items-center gap-2.5 rounded-box border border-warn bg-warn-tint px-4 py-[11px] font-semibold text-ink">
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
}

/**
 * One answer. The card with the cut corner holds only what the copilot wrote.
 * The hand-off banner and the row of tools, timing and feedback sit under it.
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
}: AnswerCardProps) {
  const { response } = exchange;
  // The hand-off reference, if there is one, is a fact the agent reads out.
  const references = useMemo(
    () => response.steps.flatMap((step) => (step.reference ? [step.reference] : [])),
    [response.steps],
  );
  return (
    <div>
      <Sim selected={selected && sidePanel} bodyClassName="px-5 pt-5 pb-6 sm:px-[30px] sm:pb-7">
        <Byline className="mb-3" />
        <AnswerMarkdown
          markdown={response.answer}
          citations={response.citations}
          references={references}
          activeCitation={activeCitation}
          onCite={onCite}
        />
      </Sim>

      {response.escalated && <HandOffBanner />}

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3.5 gap-y-2">
        {response.tools_used.length > 0 && (
          <ul aria-label="Used for this answer" className="flex flex-wrap items-center gap-1.5">
            {response.tools_used.map((name) => (
              <li
                key={name}
                className="inline-flex h-[30px] items-center gap-[7px] rounded-box border border-line-strong bg-surface pr-2.5 pl-2 text-meta font-semibold text-ink-2"
              >
                <ToolIcon name={name} size={16} />
                {toolLabel(tools, name)}
              </li>
            ))}
          </ul>
        )}
        <p className="font-mono text-meta text-ink-2">
          <span className="sr-only">Answered in </span>
          {formatSeconds(response.seconds)}
        </p>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
          {response.trace_id !== null && <FeedbackButtons traceId={response.trace_id} />}
          {sidePanel ? (
            <Button
              size="sm"
              className="h-9"
              // Ink fill: these are the details on show in the side rail.
              variant={selected ? "on" : "outline"}
              aria-pressed={selected}
              onClick={onToggleDetails}
            >
              <PanelIcon size={16} />
              Sources and steps
            </Button>
          ) : (
            <Button
              size="sm"
              className="h-9 pr-2 pl-3"
              aria-expanded={selected}
              aria-controls={detailsId}
              onClick={onToggleDetails}
            >
              Sources and steps
              <ChevronDownIcon
                size={16}
                className={cn("transition-transform duration-200", selected && "rotate-180")}
              />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
