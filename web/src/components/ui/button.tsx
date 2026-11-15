import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

/*
 * Every variant has four states beside rest, and none of them moves anything:
 * under the pointer, focused from the keyboard (the global cobalt ring),
 * pressed, and disabled.
 */
const buttonVariants = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 rounded-box font-semibold whitespace-nowrap",
    "transition-colors select-none",
    "disabled:pointer-events-none disabled:opacity-50",
  ],
  {
    variants: {
      variant: {
        // Cobalt fill: the one main thing to press.
        primary: "bg-brand text-on-brand hover:bg-brand-strong active:bg-brand-press",
        outline:
          "frame border-line-strong bg-surface text-ink hover:border-ink active:bg-sunken",
        quiet:
          "frame border-transparent text-ink hover:border-line-strong active:bg-sunken",
        // Ink fill means "you are here": a button showing what is on.
        on: "frame border-ink bg-ink text-surface hover:border-ink-2 hover:bg-ink-2 active:border-ink-3 active:bg-ink-3",
      },
      size: {
        sm: "h-9 px-3 text-meta",
        md: "h-10 px-3 text-ui",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "outline", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}
