import type { CSSProperties, ReactNode } from "react";

import { CopilotMark } from "@/components/icons/CopilotMark";
import { cn } from "@/lib/cn";

export interface SimProps {
  children: ReactNode;
  /** The size of the cut corner in pixels. The default comes from the `--cut` token. */
  cut?: number;
  /** Draws the outline heavier, for the answer whose details are on show. */
  selected?: boolean;
  className?: string;
  /** Classes for the card itself: padding, type. */
  bodyClassName?: string;
}

/**
 * A card with its top-right corner cut like a SIM. The shape means one thing:
 * the copilot wrote this. People's words, buttons and inputs never use it.
 */
export function Sim({ children, cut, selected = false, className, bodyClassName }: SimProps) {
  const style = cut === undefined ? undefined : ({ "--cut": `${cut}px` } as CSSProperties);
  return (
    <div className={cn("sim", className)} style={style} data-selected={selected}>
      <div className={cn("sim-body", bodyClassName)}>{children}</div>
    </div>
  );
}

/** The line at the top of anything the copilot wrote: its mark and its name. */
export function Byline({ className }: { className?: string }) {
  return (
    <p className={cn("flex items-center gap-2 cue", className)}>
      <CopilotMark size={16} />
      Cue
    </p>
  );
}
