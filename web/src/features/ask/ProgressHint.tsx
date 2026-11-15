import { CopilotMark } from "@/components/icons/CopilotMark";
import { SignalBars } from "@/components/shared/SignalBars";
import { Sim } from "@/components/shared/Sim";
import { useCycle } from "@/hooks/useCycle";

/** The stages every question goes through. Shown in turn; they are not live progress. */
const HINTS = [
  "Removing personal details",
  "Checking the request",
  "Looking it up",
  "Checking the answer",
] as const;

const HINT_MILLISECONDS = 1800;

/**
 * Shown while an answer is on its way: the copilot's card, with its signal
 * bars seeking. It moves through the names of the four stages at a steady
 * pace and starts over, like a phone looking for its network. It claims
 * nothing about which stage is running.
 */
export function ProgressHint() {
  const index = useCycle(HINTS.length, HINT_MILLISECONDS);
  return (
    <div role="status" className="flex">
      <span className="sr-only">Working on the answer.</span>
      <Sim cut={16} bodyClassName="flex items-center gap-3.5 py-3.5 pr-9 pl-[18px] text-read">
        <CopilotMark size={18} />
        <SignalBars level={index} seeking={index} />
        <span key={index} aria-hidden="true" className="animate-fade">
          {HINTS[index]}
        </span>
      </Sim>
    </div>
  );
}
