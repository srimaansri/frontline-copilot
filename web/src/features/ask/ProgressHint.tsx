import type { StageEvent } from "@/api/types";
import { WorkingCard } from "@/components/shared/WorkingCard";

/** How far along each stage is, as the bar that is seeking: 0 to 3. */
const BAR_OF_STAGE: Record<string, number> = {
  redaction: 0,
  input_check: 1,
  model: 2,
  tool: 2,
  answer: 3,
  simplify: 3,
  output_check: 3,
};

/** Shown until the server has said what it is doing, and if it never does. */
const NOT_YET_KNOWN = "Working on it";

export interface ProgressHintProps {
  /** What the copilot is doing now, as the server reported it. */
  stage?: StageEvent;
}

/**
 * Shown while an answer is on its way: the copilot's card, with its signal
 * bars seeking and the stage that is really running. The words come from the
 * server, one event as each stage starts, so they change when the work does
 * and not on a timer. Before the first event, and against a server that sends
 * none, it says only that work is under way.
 */
export function ProgressHint({ stage }: ProgressHintProps) {
  const label = stage?.label ?? NOT_YET_KNOWN;
  const bar = stage ? (BAR_OF_STAGE[stage.stage] ?? 2) : 0;
  return (
    <WorkingCard bar={bar}>
      <span className="sr-only">Working on the answer.</span>
      <span key={label} aria-hidden="true" className="animate-fade">
        {label}
      </span>
    </WorkingCard>
  );
}
