import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

/** A bordered surface. Borders carry the structure here, not shadows. */
export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("rounded-xl border bg-surface", className)} {...props} />;
}
