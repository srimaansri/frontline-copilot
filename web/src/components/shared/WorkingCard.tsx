import type { ReactNode } from "react";

import { CopilotMark } from "@/components/icons/CopilotMark";

import { SignalBars } from "./SignalBars";
import { Sim } from "./Sim";

export interface WorkingCardProps {
  /** Which of the four bars is seeking, 0 to 3. The bars before it are filled. */
  bar: number;
  /** What the copilot is doing, in words. */
  children: ReactNode;
}

/**
 * The copilot's card while it is working: its mark, its signal bars seeking,
 * and a few words. Used while an answer or a summary is on its way.
 */
export function WorkingCard({ bar, children }: WorkingCardProps) {
  return (
    <div role="status" className="flex">
      <Sim cut={16} bodyClassName="flex items-center gap-4 py-3 pr-8 pl-4 text-read">
        <CopilotMark size={16} working />
        <SignalBars level={bar} seeking={bar} />
        {children}
      </Sim>
    </div>
  );
}
