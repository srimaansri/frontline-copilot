import type { AskResponse, ToolInfo } from "@/api/types";
import { ChevronDownIcon, PanelIcon } from "@/components/icons/glyphs";
import { ToolBadge } from "@/components/shared/ToolBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatSeconds } from "@/lib/format";

import { FeedbackButtons, type FeedbackState } from "./FeedbackButtons";

export interface AnswerFooterProps {
  response: AskResponse;
  tools: readonly ToolInfo[];
  /** Whether this answer's sources and steps are the ones on show. */
  selected: boolean;
  /** True when the sources and steps sit in a side panel, not under the answer. */
  sidePanel: boolean;
  /** The id of the element under the answer that holds its sources and steps. */
  detailsId: string;
  onToggleDetails: () => void;
  /** The feedback state to start in. Only the component gallery sets it. */
  initialFeedback?: FeedbackState;
}

/**
 * The row under an answer: the tools it used, how long it took, the two
 * feedback buttons, and the button that shows its sources and steps.
 */
export function AnswerFooter({
  response,
  tools,
  selected,
  sidePanel,
  detailsId,
  onToggleDetails,
  initialFeedback,
}: AnswerFooterProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      {response.tools_used.length > 0 && (
        <ul aria-label="Used for this answer" className="flex flex-wrap items-center gap-2">
          {response.tools_used.map((name) => (
            <li key={name} className="flex">
              <ToolBadge name={name} tools={tools} />
            </li>
          ))}
        </ul>
      )}
      <p className="font-mono text-meta text-ink-2">
        <span className="sr-only">Answered in </span>
        {formatSeconds(response.seconds)}
      </p>

      <div className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
        {response.trace_id !== null && (
          <FeedbackButtons traceId={response.trace_id} initialState={initialFeedback} />
        )}
        {sidePanel ? (
          <Button
            size="sm"
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
            className="pr-2"
            aria-expanded={selected}
            aria-controls={detailsId}
            onClick={onToggleDetails}
          >
            Sources and steps
            <ChevronDownIcon
              size={16}
              className={cn("transition-transform", selected && "rotate-180")}
            />
          </Button>
        )}
      </div>
    </div>
  );
}
