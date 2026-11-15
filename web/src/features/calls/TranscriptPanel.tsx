import { ShieldCheck } from "lucide-react";

import type { CallTranscript, Speaker } from "@/api/types";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";

const SPEAKER_LABELS: Record<Speaker, string> = {
  agent: "Agent",
  customer: "Customer",
};

function Loading() {
  return (
    <div className="space-y-4">
      <Skeleton className="ml-auto h-12 w-3/5 rounded-2xl" />
      <Skeleton className="h-12 w-1/2 rounded-2xl" />
      <Skeleton className="ml-auto h-16 w-2/3 rounded-2xl" />
      <Skeleton className="h-12 w-2/5 rounded-2xl" />
    </div>
  );
}

function Turns({ transcript }: { transcript: CallTranscript }) {
  const { turns } = transcript;
  if (turns.length === 0) {
    return <p className="text-[0.9375rem] text-fg-muted">This call has no turns.</p>;
  }
  return (
    <ol className="animate-fade">
      {turns.map((turn, index) => {
        const agent = turn.speaker === "agent";
        const startsRun = turns[index - 1]?.speaker !== turn.speaker;
        return (
          <li
            // Turns are in spoken order and are never reordered.
            key={index}
            className={cn(
              "flex flex-col",
              agent ? "items-end" : "items-start",
              startsRun ? "mt-5 first:mt-0" : "mt-1.5",
            )}
          >
            <span
              className={cn("mb-1 px-1 text-xs font-medium text-fg-subtle", !startsRun && "sr-only")}
            >
              {SPEAKER_LABELS[turn.speaker]}
            </span>
            <p
              className={cn(
                "max-w-[min(86%,36rem)] rounded-2xl px-4 py-2.5 text-[1.0625rem] leading-relaxed break-words text-fg",
                agent ? "rounded-br-md bg-accent-soft" : "rounded-bl-md border bg-surface",
              )}
            >
              <PlaceholderText
                text={turn.text}
                chipClassName={agent ? "border-accent/25 bg-surface/70" : undefined}
              />
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export interface TranscriptPanelProps {
  transcript: Loadable<CallTranscript>;
  onRetry: () => void;
}

/** One call as a conversation: the customer on the left, the agent on the right. */
export function TranscriptPanel({ transcript, onRetry }: TranscriptPanelProps) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <p className="flex items-start gap-2 text-sm leading-relaxed text-fg-subtle">
        <ShieldCheck aria-hidden="true" className="mt-[3px] size-4 shrink-0" />
        Personal details were replaced with placeholders before this was saved.
      </p>
      <div className="mt-6">
        {transcript.status === "loading" && <Loading />}
        {transcript.status === "error" && (
          <ErrorNotice message={transcript.message} onRetry={onRetry} />
        )}
        {transcript.status === "ready" && <Turns transcript={transcript.data} />}
      </div>
    </div>
  );
}
