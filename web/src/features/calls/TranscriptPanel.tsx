import type { CallTranscript, RuleFinding, Speaker } from "@/api/types";
import { FlagIcon } from "@/components/icons/glyphs";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";

import { findingsByTurn, ruleTitle, turnElementId, turnNumber } from "./findingRules";

const SPEAKER_LABELS: Record<Speaker, string> = {
  agent: "Agent",
  customer: "Customer",
};

const NO_FINDINGS: readonly RuleFinding[] = [];

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

interface TurnsProps {
  transcript: CallTranscript;
  findings: readonly RuleFinding[];
  turnIdPrefix: string | undefined;
}

function Turns({ transcript, findings, turnIdPrefix }: TurnsProps) {
  const { turns } = transcript;
  if (turns.length === 0) {
    return <p className="text-ink-2">This call has no turns.</p>;
  }
  const flagged = findingsByTurn(findings);
  return (
    <ol className="flex animate-fade flex-col">
      {turns.map((turn, index) => {
        const agent = turn.speaker === "agent";
        const startsRun = turns[index - 1]?.speaker !== turn.speaker;
        const found = flagged.get(index);
        return (
          <li
            // Turns are in spoken order and are never reordered.
            key={index}
            id={turnIdPrefix === undefined ? undefined : turnElementId(turnIdPrefix, index)}
            // A flagged turn can take focus, so "Go to turn" lands on it for the keyboard too.
            tabIndex={found ? -1 : undefined}
            className={cn(
              "flex max-w-[min(88%,var(--container-md))] scroll-mt-6 flex-col gap-2 rounded-box",
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
                agent ? "bg-surface" : "bg-sunken",
                // The turn a finding points at is outlined in the colour of "needs a person".
                found && "edge-flag",
                !found && (agent ? "border-line-strong" : "border-transparent"),
              )}
            >
              <PlaceholderText text={turn.text} />
            </p>
            {found && (
              <p className="flex items-start gap-2 text-meta font-semibold text-warn">
                <FlagIcon size={16} className="mt-0.5" />
                <span>
                  <span className="sr-only">Rule check, </span>
                  Turn <span className="font-mono">{turnNumber(index)}</span>:{" "}
                  {found.map((finding) => ruleTitle(finding.rule)).join("; ")}
                </span>
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export interface TranscriptPanelProps {
  transcript: Loadable<CallTranscript>;
  onRetry: () => void;
  /** What the rule check found. Each turn a finding points at is marked. */
  findings?: readonly RuleFinding[];
  /** Gives every turn a DOM id (`turnElementId`), so a finding can go to its turn. */
  turnIdPrefix?: string;
}

/** One call as a script: the agent on the left, the customer on the right. */
export function TranscriptPanel({
  transcript,
  onRetry,
  findings = NO_FINDINGS,
  turnIdPrefix,
}: TranscriptPanelProps) {
  return (
    <div className="px-4 pt-6 pb-8 sm:px-8">
      {transcript.status === "loading" && <Loading />}
      {transcript.status === "error" && (
        <ErrorNotice message={transcript.message} onRetry={onRetry} />
      )}
      {transcript.status === "ready" && (
        <Turns transcript={transcript.data} findings={findings} turnIdPrefix={turnIdPrefix} />
      )}
    </div>
  );
}
