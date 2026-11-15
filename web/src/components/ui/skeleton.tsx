import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

/** A quiet block that stands in for content on its way. Hidden from screen readers. */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-surface-muted", className)}
      {...props}
    />
  );
}
