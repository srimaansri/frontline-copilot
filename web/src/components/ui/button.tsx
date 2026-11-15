import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap",
    "transition-colors duration-150 select-none",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:size-4 [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-fg hover:bg-accent-hover",
        outline:
          "border border-border-strong bg-surface text-fg hover:border-fg-subtle hover:bg-surface-muted",
        ghost: "text-fg-muted hover:bg-surface-muted hover:text-fg",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-[0.9375rem]",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}
