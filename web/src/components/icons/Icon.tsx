import type { ReactNode, SVGProps } from "react";

import { cn } from "@/lib/cn";

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "children" | "viewBox"> {
  /** Width and height in pixels: 16, 20 (the default), 24 or 32. */
  size?: number;
  /** Names the icon for screen readers. Without it the icon is decorative. */
  title?: string;
}

/** A little heavier when small, a little lighter when large, so the weight looks even. */
function strokeFor(size: number): number {
  if (size <= 16) {
    return 2;
  }
  return size >= 32 ? 1.6 : 1.75;
}

/**
 * The base every icon is drawn on, so the set stays in one hand: a 24 grid,
 * one stroke weight, flat line ends, mitred joins, and corners cut at 45
 * degrees where another set would round them. Colour comes from the text.
 */
export function Icon({
  size = 20,
  title,
  className,
  children,
  ...props
}: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeFor(size)}
      strokeLinecap="butt"
      strokeLinejoin="miter"
      role={title === undefined ? undefined : "img"}
      aria-hidden={title === undefined ? true : undefined}
      focusable="false"
      className={cn("shrink-0", className)}
      {...props}
    >
      {title !== undefined && <title>{title}</title>}
      {children}
    </svg>
  );
}
