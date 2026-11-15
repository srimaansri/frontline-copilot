import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

const badgeVariants = cva(
  [
    "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
    "[&_svg]:size-3.5 [&_svg]:shrink-0",
  ],
  {
    variants: {
      tone: {
        neutral: "border border-border bg-surface-muted text-fg-muted",
        accent: "bg-accent-soft text-accent-soft-fg",
        ok: "bg-ok-soft text-ok",
        notice: "bg-notice-soft text-notice",
        warning: "bg-warning-soft text-warning",
        blocked: "bg-blocked-soft text-blocked",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export type BadgeProps = ComponentProps<"span"> & { tone?: BadgeTone };

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
