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

export interface TurnsProps {
  transcript: CallTranscript;
  /**
   * A replay: only the turns up to this one are on show, counted from 0. Each
   * turn carries its number, so it can be matched to the assist panel, and the
   * list is announced as a log, because turns are added to it.
   */
  upTo?: number;
  /**
   * What the rule check found. Each turn a finding points at is marked. A replay
   * is given none: there call assist raises its own reminders as the call reaches
   * them, and a mark from the finished call would give them away.
   */
  findings?: readonly RuleFinding[];
  /** Gives every turn a DOM id (`turnElementId`), so a finding can go to its turn. */
  turnIdPrefix?: string;
}

/** The turns of a call, in spoken order: all of them, or the ones a replay has reached. */
export function Turns({ transcript, upTo, findings = NO_FINDINGS, turnIdPrefix }: TurnsProps) {
  const replay = upTo !== undefined;
  const turns = replay ? transcript.turns.slice(0, upTo + 1) : transcript.turns;
  if (transcript.turns.length === 0) {
    return <p className="text-ink-2">This call has no turns.</p>;
  }
  const flagged = findingsByTurn(findings);
  return (
    <ol
      role={replay ? "log" : undefined}
      aria-label={replay ? "The call so far" : undefined}
      className="flex animate-fade flex-col"
    >
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
              // In a replay a turn arrives once, when the call reaches it.
              replay && "animate-rise",
            )}
          >
            <span className={cn("cue", !startsRun && !replay && "sr-only")}>
              <span className={cn(!startsRun && "sr-only")}>{SPEAKER_LABELS[turn.speaker]}</span>
              {replay && (
                <span className="font-mono font-normal text-ink-3">
                  <span className="sr-only">, turn</span> {index + 1}
                </span>
              )}
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
