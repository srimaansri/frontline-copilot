import { cn } from "@/lib/cn";

export interface CopilotMarkProps {
  /** Width and height in pixels. */
  size?: number;
  className?: string;
}

/**
 * The brand mark: a robot whose head is a SIM card, with the top-right corner
 * cut. Its eyes are the one use of the highlighter colour outside an answer's
 * script, and its antenna sends two signal arcs, drawn with the same cut
 * corner. Decorative: the product's name is always written beside it.
 *
 * public/favicon.svg is the same drawing with the colours written in.
 */
export function CopilotMark({ size = 30, className }: CopilotMarkProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={cn("shrink-0", className)}
    >
      {/* The antenna and its two signal arcs. */}
      <g fill="none" stroke="var(--brand-text)" strokeWidth="1.8">
        <path d="M9.5 14v-3.4" />
        <path d="M9.5 4.3h1.9l2.7 2.7v1.9" />
        <path d="M9.5.9h3.3l4.7 4.7v3.3" />
      </g>
      <rect x="7.8" y="7.2" width="3.4" height="3.4" fill="var(--brand-text)" />
      {/* The head: a SIM. */}
      <path d="M3 14h17l9 9v7H3z" fill="var(--brand)" />
      {/* The eyes, in highlighter. */}
      <rect x="8" y="19" width="3.8" height="4.4" fill="var(--hi)" />
      <rect x="16.2" y="19" width="3.8" height="4.4" fill="var(--hi)" />
      <path d="M9.8 25.8l1.3 1.3h5.8l1.3-1.3" fill="none" stroke="var(--on-brand)" strokeWidth="1.5" />
    </svg>
  );
}
