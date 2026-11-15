import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 rounded-box font-semibold whitespace-nowrap",
    "transition-colors duration-150 select-none",
    "disabled:pointer-events-none disabled:opacity-50",
  ],
  {
    variants: {
      variant: {
        // Cobalt fill: the one main thing to press.
        primary: "bg-brand text-on-brand hover:brightness-110",
        outline: "border-[1.5px] border-line-strong bg-surface text-ink hover:border-ink",
        quiet: "border-[1.5px] border-transparent text-ink hover:border-line-strong",
        // Ink fill means "you are here": a button showing what is on.
        on: "border-[1.5px] border-ink bg-ink text-surface",
      },
      size: {
        sm: "h-8 pr-3 pl-2.5 text-meta",
        md: "h-10 pr-3.5 pl-3 text-ui",
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
