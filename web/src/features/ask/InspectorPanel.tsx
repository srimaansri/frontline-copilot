import type { ToolInfo } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";

import { AnswerDetails } from "./AnswerDetails";
import type { SourceHighlight } from "./SourceList";
import type { Exchange } from "./useConversation";

function Waiting() {
  return (
    <div>
      <p className="text-sm leading-relaxed text-fg-subtle">
        The sources and steps show here when the answer is ready.
      </p>
      <div className="mt-6 space-y-6">
        {[0, 1, 2, 3].map((row) => (
          <div key={row} className="flex gap-3.5">
            <Skeleton className="size-8 shrink-0 rounded-full" />
            <div className="flex-1 space-y-2 pt-1">
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
  return <p className="text-sm leading-relaxed text-fg-subtle">{children}</p>;
}

export interface InspectorPanelProps {
  /** The exchange whose details are on show, if one is selected. */
  exchange: Exchange | null;
  tools: readonly ToolInfo[];
  highlight: SourceHighlight | null;
}

/** The right-hand panel on wide screens: the sources and steps of the selected answer. */
export function InspectorPanel({ exchange, tools, highlight }: InspectorPanelProps) {
  return (
    <aside
      aria-label="Sources and steps"
      className="flex w-[23rem] shrink-0 animate-fade flex-col border-l bg-surface xl:w-[26rem]"
    >
      <div className="shrink-0 border-b px-6 py-4">
        <h2 className="text-sm font-semibold text-fg">Sources and steps</h2>
        <p className="mt-1 line-clamp-2 text-sm leading-snug text-fg-subtle">
          {exchange ? exchange.question : "No answer is selected."}
        </p>
      </div>
      <div className="scroll-area min-h-0 flex-1 px-6 py-6">
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
