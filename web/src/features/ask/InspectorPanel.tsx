import type { ToolInfo } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";

import { AnswerDetails } from "./AnswerDetails";
import type { SourceHighlight } from "./SourceList";
import type { Exchange } from "./useConversation";

function Waiting() {
  return (
    <div>
      <p className="text-ink-2">The sources and steps show here when the answer is ready.</p>
      <div className="mt-6 grid gap-6">
        {[0, 1, 2, 3].map((row) => (
          <div key={row} className="flex gap-3">
            <Skeleton className="size-6 shrink-0" />
            <div className="grid flex-1 gap-2 pt-0.5">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Note({ children }: { children: string }) {
  return <p className="text-ink-2">{children}</p>;
}

export interface InspectorPanelProps {
  /** The exchange whose details are on show, if one is selected. */
  exchange: Exchange | null;
  tools: readonly ToolInfo[];
  highlight: SourceHighlight | null;
}

/**
 * The copilot's side rail on wide screens: the sources and steps of the
 * selected answer, on the sunken tone that marks the copilot's own working.
 */
export function InspectorPanel({ exchange, tools, highlight }: InspectorPanelProps) {
  return (
    <aside
      aria-label="Sources and steps for the selected answer"
      className="flex w-96 shrink-0 animate-fade flex-col border-l border-line bg-sunken xl:w-110"
    >
      <div className="scroll-area min-h-0 flex-1 px-6 pt-6 pb-8">
        {exchange !== null && (
          <div className="mb-6">
            <p className="cue">Agent asked</p>
            <p className="mt-1 line-clamp-2 text-meta text-ink-2">{exchange.question}</p>
          </div>
        )}
        {exchange === null && <Note>Choose an answer to see its sources and steps.</Note>}
        {exchange?.status === "pending" && <Waiting />}
        {exchange?.status === "error" && (
          <Note>This question has no answer. Try it again to see sources and steps.</Note>
        )}
        {exchange?.status === "done" && (
          <AnswerDetails
            key={exchange.id}
            response={exchange.response}
            tools={tools}
            highlight={highlight}
          />
        )}
      </div>
    </aside>
  );
}
