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
    <div className="grid gap-4">
      <Skeleton className="h-12 w-3/5" />
      <Skeleton className="ml-auto h-12 w-1/2" />
      <Skeleton className="h-16 w-2/3" />
      <Skeleton className="ml-auto h-12 w-2/5" />
    </div>
  );
}

function Turns({ transcript }: { transcript: CallTranscript }) {
  const { turns } = transcript;
  if (turns.length === 0) {
    return <p className="text-ink-2">This call has no turns.</p>;
  }
  return (
    <ol className="flex animate-fade flex-col">
      {turns.map((turn, index) => {
        const agent = turn.speaker === "agent";
        const startsRun = turns[index - 1]?.speaker !== turn.speaker;
        return (
          <li
            // Turns are in spoken order and are never reordered.
            key={index}
            className={cn(
              "flex max-w-[min(88%,var(--container-md))] flex-col gap-2",
              agent ? "items-start self-start" : "items-end self-end",
              startsRun ? "mt-4 first:mt-0" : "mt-2",
            )}
          >
            <span className={cn("cue", !startsRun && "sr-only")}>
              {SPEAKER_LABELS[turn.speaker]}
            </span>
            {/* People's words keep soft-square corners. Only the copilot gets the cut corner. */}
            <p
              className={cn(
                "rounded-box border px-4 py-3 text-read leading-normal break-words text-ink",
                agent ? "border-line-strong bg-surface" : "border-transparent bg-sunken",
              )}
            >
              <PlaceholderText text={turn.text} />
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

/** One call as a script: the agent on the left, the customer on the right. */
export function TranscriptPanel({ transcript, onRetry }: TranscriptPanelProps) {
  return (
    <div className="px-4 pt-6 pb-8 sm:px-8">
      {transcript.status === "loading" && <Loading />}
      {transcript.status === "error" && (
        <ErrorNotice message={transcript.message} onRetry={onRetry} />
      )}
      {transcript.status === "ready" && <Turns transcript={transcript.data} />}
    </div>
  );
}
