import type { CallFindings, RuleFinding } from "@/api/types";
import { FlagIcon } from "@/components/icons/glyphs";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";
import { countOf } from "@/lib/format";

import { ruleTitle, turnNumber } from "./findingRules";

/**
 * What the check is, said every time it is shown. It is a set of fixed rules
 * with known misses, and a reader must not take silence, or a flag, for a verdict.
 */
function WhatThisIs({ found }: { found: boolean }) {
  return (
    <p className="mt-2 text-meta text-ink-2">
      {found
        ? "A finding is a reason to read the turn, not a verdict. "
        : "That does not show the call is clean. "}
      This is a rule check: fixed rules read the redacted call, and no model is involved. The rules
      miss some breaches, such as one said in words no rule has a pattern for, and can flag a turn
      that is fine.
    </p>
  );
}

interface FindingItemProps {
  finding: RuleFinding;
  /** False when the finding points at a turn the transcript on show does not have. */
  reachable: boolean;
  onGoToTurn: (turnIndex: number) => void;
}

function FindingItem({ finding, reachable, onGoToTurn }: FindingItemProps) {
  return (
    <li className="flex flex-wrap items-start gap-x-4 gap-y-2 border-t border-warn pt-3">
      <div className="min-w-0 flex-1 basis-56">
        <p className="font-semibold text-ink">{ruleTitle(finding.rule)}</p>
        <p className="mt-1 text-ui text-ink">{finding.reason}</p>
      </div>
      {reachable ? (
        <Button
          size="sm"
          onClick={() => {
            onGoToTurn(finding.turn_index);
          }}
        >
          Go to turn <span className="font-mono">{turnNumber(finding.turn_index)}</span>
        </Button>
      ) : (
        <p className="text-meta text-ink-2">
          Turn <span className="font-mono">{turnNumber(finding.turn_index)}</span>
        </p>
      )}
    </li>
  );
}

function Found({
  result,
  turnCount,
  onGoToTurn,
}: {
  result: CallFindings;
  turnCount: number | null;
  onGoToTurn: (turnIndex: number) => void;
}) {
  const { findings } = result;
  const found = findings.length > 0;
  return (
    // Soft-square corners: this is the product's rule check speaking, not something Cue wrote.
    <div
      className={cn(
        "animate-fade rounded-box border px-4 py-4 text-ink",
        // The tint the hand-off banner has: something here needs a person.
        found ? "border-warn bg-warn-tint" : "border-line-strong bg-surface",
      )}
    >
      <h3 className="flex flex-wrap items-center gap-x-3 gap-y-1 font-semibold">
        <FlagIcon className={found ? "text-warn" : "text-ink-2"} />
        Rule check
        <span className="font-mono text-meta font-semibold text-ink-2">
          {found ? countOf(findings.length, "finding") : "no rule fired"}
        </span>
      </h3>
      <WhatThisIs found={found} />
      {found && (
        <ol className="mt-4 grid gap-3">
          {findings.map((finding) => (
            <FindingItem
              key={`${finding.rule}-${finding.turn_index}`}
              finding={finding}
              reachable={turnCount !== null && finding.turn_index < turnCount}
              onGoToTurn={onGoToTurn}
            />
          ))}
        </ol>
      )}
    </div>
  );
}

export interface FindingsPanelProps {
  findings: Loadable<CallFindings>;
  /** How many turns the transcript on show has. Null until it has loaded. */
  turnCount: number | null;
  onGoToTurn: (turnIndex: number) => void;
  onRetry: () => void;
}

/**
 * What the rule check found in the call on show: each finding in plain words,
 * with a button that goes to the turn it points at.
 */
export function FindingsPanel({ findings, turnCount, onGoToTurn, onRetry }: FindingsPanelProps) {
  return (
    <section aria-label="Rule check">
      {findings.status === "loading" && <Skeleton className="h-24" />}
      {findings.status === "error" && <ErrorNotice message={findings.message} onRetry={onRetry} />}
      {findings.status === "ready" && (
        <Found result={findings.data} turnCount={turnCount} onGoToTurn={onGoToTurn} />
      )}
    </section>
  );
}
