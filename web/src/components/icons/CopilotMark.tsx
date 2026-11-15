import { cn } from "@/lib/cn";

export interface CopilotMarkProps {
  /**
   * Width and height in pixels. 16, 32 and 64 land every edge on a whole
   * pixel; use those where the mark stands alone.
   */
  size?: number;
  /** The copilot is working: the eyes glance out through the visor and back. */
  working?: boolean;
  className?: string;
}

/** One drawing of the mark: the head, and the two eyes as [x, y, width, height]. */
interface Drawing {
  grid: number;
  head: string;
  eyes: readonly (readonly [number, number, number, number])[];
  /** The corner radius of an eye, in grid units. */
  eyeRadius: number;
  /** How far the eyes travel when they glance, in grid units. */
  glance: number;
}

/*
 * The mark is a helmet seen from the front, with the visor open to one side.
 * Read as an outline it is the SIM card: three round corners and one cut at
 * 45 degrees, the same cut every card the copilot writes has. Read as a
 * letter it is a C. The face looks out through the gap, toward the name set
 * beside it.
 *
 * Master drawing, 32 grid. A 26 x 26 square with a wall of 6 and an outer
 * radius of 6, so the wall and the corner are one measure. The cut has legs
 * of 6 as well. The visor is 14 high with an inner radius of 3. Across the
 * visor the rhythm is even: 4 of space, an eye of 4, 4 of space, an eye of 4,
 * 4 of space. The eyes are 8 high, which leaves 3 above and 3 below, and
 * their corners have a radius of 1: firm, like the 3px corners of the
 * controls the mark sits beside.
 */
const MASTER: Drawing = {
  grid: 32,
  head: "M9 3H23L29 9H12A3 3 0 0 0 9 12V20A3 3 0 0 0 12 23H29A6 6 0 0 1 23 29H9A6 6 0 0 1 3 23V9A6 6 0 0 1 9 3Z",
  eyes: [
    [13, 12, 4, 8],
    [21, 12, 4, 8],
  ],
  eyeRadius: 1,
  glance: 2,
};

/*
 * Small drawing, 16 grid, for sizes of 20 and under. It is not the master
 * scaled down: the wall is thicker for its size and every edge sits on a whole
 * pixel at 16, so a browser tab shows it sharp.
 */
const SMALL: Drawing = {
  grid: 16,
  head: "M4 1H12L15 4H5.5A1.5 1.5 0 0 0 4 5.5V10.5A1.5 1.5 0 0 0 5.5 12H15A3 3 0 0 1 12 15H4A3 3 0 0 1 1 12V4A3 3 0 0 1 4 1Z",
  eyes: [
    [7, 6, 2, 4],
    [11, 6, 2, 4],
  ],
  eyeRadius: 0.5,
  glance: 1,
};

/**
 * The brand mark. The head is cobalt and the eyes are ink, in both themes.
 * The highlighter is not used here: it has one job, which is to mark what the
 * agent says out loud.
 *
 * Decorative: the product's name is always written beside it.
 * public/favicon.svg is the small drawing with the colours written in.
 */
export function CopilotMark({ size = 32, working = false, className }: CopilotMarkProps) {
  const drawing = size <= 20 ? SMALL : MASTER;
  return (
    <svg
      viewBox={`0 0 ${drawing.grid} ${drawing.grid}`}
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={cn("mark shrink-0", className)}
      data-working={working}
      style={{ "--glance": `${drawing.glance}px` } as React.CSSProperties}
    >
      <path d={drawing.head} fill="var(--mark)" />
      <g className="mark-eyes" fill="var(--ink)">
        {drawing.eyes.map(([x, y, width, height]) => (
          <rect key={x} x={x} y={y} width={width} height={height} rx={drawing.eyeRadius} />
        ))}
      </g>
    </svg>
  );
}
