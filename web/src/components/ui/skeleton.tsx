import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export type SkeletonProps = ComponentProps<"div"> & {
  /**
   * Hold still. For a placeholder that sits beside the copilot's working card:
   * the signal bars are already the one thing on the screen that says "working".
   */
  still?: boolean;
};

/** A quiet block that stands in for content on its way. Hidden from screen readers. */
export function Skeleton({ still = false, className, ...props }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn("rounded-box bg-line/70", !still && "animate-pulse", className)}
      {...props}
    />
  );
}
