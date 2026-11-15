import type { ReactNode } from "react";

import type { StepStatus } from "@/api/types";
import { cn } from "@/lib/cn";

interface Shape {
  /** The word that goes with the shape. */
  word: string;
  /** The colour, which only repeats what the shape already says. */
  tone: string;
  drawing: ReactNode;
}

const KNOCK = { fill: "none", stroke: "var(--knock)", strokeWidth: 1.9 } as const;

/** Circle OK, square Notice, triangle Warning, octagon Blocked. */
const SHAPES: Record<StepStatus, Shape> = {
  ok: {
    word: "OK",
    tone: "text-ok",
    drawing: (
      <>
        <circle cx="8" cy="8" r="7.2" fill="currentColor" />
        <path d="M4.5 8.3l2.4 2.4 4.6-5" {...KNOCK} />
      </>
    ),
  },
  notice: {
    word: "Notice",
    tone: "text-notice",
    drawing: (
      <>
        <path d="M1.3 1.3h13.4v13.4H1.3z" fill="currentColor" />
        <path d="M8 3.8v2M8 7.4v4.8" {...KNOCK} />
      </>
    ),
  },
  warning: {
    word: "Warning",
    tone: "text-warn",
    drawing: (
      <>
        <path d="M8 .8l7.6 14.2H.4z" fill="currentColor" />
        <path d="M8 5.8v4.4M8 11.6v1.9" {...KNOCK} />
      </>
    ),
  },
  blocked: {
    word: "Blocked",
    tone: "text-block",
    drawing: (
      <>
        <path d="M4.9.8h6.2l4.1 4.1v6.2l-4.1 4.1H4.9L.8 11.1V4.9z" fill="currentColor" />
        <path d="M4.2 8h7.6" {...KNOCK} />
      </>
    ),
  },
};

export interface StatusStampProps {
  status: StepStatus;
  /** Width and height in pixels: 16 beside text, 20 in a notice, 24 on the route. */
  size?: 16 | 20 | 24;
  className?: string;
}

/**
 * A status as a solid shape with its glyph knocked out. The shape alone says
 * the state, so it survives at 16px and without colour. Decorative: the word
 * is always written next to it, or given to screen readers by its container.
 */
export function StatusStamp({ status, size = 16, className }: StatusStampProps) {
  const shape = SHAPES[status];
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={cn("shrink-0", shape.tone, className)}
    >
      {shape.drawing}
    </svg>
  );
}

export interface StatusWordProps {
  status: StepStatus;
  className?: string;
}

/** The word for a status, in capitals and in the status colour: OK, NOTICE, WARNING, BLOCKED. */
export function StatusWord({ status, className }: StatusWordProps) {
  const shape = SHAPES[status];
  return (
    <span
      className={cn(
        "text-label font-bold tracking-status whitespace-nowrap uppercase",
        shape.tone,
        className,
      )}
    >
      {shape.word}
    </span>
  );
}

export interface StatusLabelProps {
  status: StepStatus;
  /** The words beside the shape, such as "Resolved". */
  children: ReactNode;
  className?: string;
}

/** A status shape with words of your choosing beside it, in the status colour. */
export function StatusLabel({ status, children, className }: StatusLabelProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 text-meta font-semibold whitespace-nowrap",
        SHAPES[status].tone,
        className,
      )}
    >
      <StatusStamp status={status} />
      {children}
    </span>
  );
}
