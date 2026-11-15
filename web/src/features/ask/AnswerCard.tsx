import { ChevronDown, Headset, PanelRight, Timer } from "lucide-react";

import type { ToolInfo } from "@/api/types";
import { BrandMark } from "@/components/shared/BrandMark";
import { ToolIcon } from "@/components/shared/ToolIcon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatSeconds } from "@/lib/format";
import { toolLabel } from "@/lib/tools";

import { AnswerMarkdown } from "./AnswerMarkdown";
import { FeedbackButtons } from "./FeedbackButtons";
import type { AnsweredExchange } from "./useConversation";

function HandOffBanner() {
  return (
    <div className="mt-5 flex items-start gap-3 rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-warning">
      <Headset aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
      <p className="text-base leading-relaxed font-medium">
        This needs a person. A hand-off was opened.
      </p>
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

/** One answer: the text, a hand-off banner if one was opened, and what went into it. */
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
  return (
    <div
      className={cn(
        "rounded-xl border bg-surface transition-[border-color,box-shadow] duration-200",
        selected && sidePanel && "border-accent/60 shadow-[0_0_0_3px_var(--accent-soft)]",
      )}
    >
      <div className="px-5 pt-5 sm:px-6">
        <div className="mb-3.5 flex items-center gap-2.5">
          <BrandMark className="size-6 rounded-md" />
          <p className="text-sm font-semibold text-fg">Copilot</p>
        </div>
        <AnswerMarkdown
          markdown={response.answer}
          citations={response.citations}
          activeCitation={activeCitation}
          onCite={onCite}
        />
        {response.escalated && <HandOffBanner />}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 border-t px-5 py-2.5 sm:px-6">
        {response.tools_used.length > 0 && (
          <ul aria-label="Used for this answer" className="flex flex-wrap items-center gap-1.5">
            {response.tools_used.map((name) => (
              <li key={name} className="flex">
                <Badge tone="accent">
                  <ToolIcon name={name} />
                  {toolLabel(tools, name)}
                </Badge>
              </li>
            ))}
          </ul>
        )}
        <p className="inline-flex items-center gap-1.5 text-xs text-fg-subtle">
          <Timer aria-hidden="true" className="size-3.5" />
          <span className="sr-only">Answered in </span>
          {formatSeconds(response.seconds)}
        </p>

        <div className="ml-auto flex items-center gap-2">
          {response.trace_id !== null && <FeedbackButtons traceId={response.trace_id} />}
          {sidePanel ? (
            <Button
              variant="ghost"
              size="sm"
              aria-pressed={selected}
              onClick={onToggleDetails}
              className={cn(selected && "bg-accent-soft text-accent-soft-fg hover:bg-accent-soft")}
            >
              <PanelRight aria-hidden="true" />
              Sources and steps
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              aria-expanded={selected}
              aria-controls={detailsId}
              onClick={onToggleDetails}
            >
              Sources and steps
              <ChevronDown
                aria-hidden="true"
                className={cn("transition-transform duration-200", selected && "rotate-180")}
              />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
