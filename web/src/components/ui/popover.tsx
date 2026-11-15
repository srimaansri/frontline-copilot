import * as PopoverPrimitive from "@radix-ui/react-popover";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Popover(props: ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root {...props} />;
}

export function PopoverTrigger(props: ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger {...props} />;
}

const PANEL =
  "w-84 max-w-[calc(100vw-1.5rem)] rounded-box frame border-ink bg-surface p-5 text-ink shadow-pop";

/** A popover's panel on its own, not floating. The gallery shows popover content in it. */
export function PopoverPanel({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn(PANEL, className)} {...props} />;
}

export function PopoverContent({
  className,
  align = "end",
  sideOffset = 8,
  collisionPadding = 12,
  ...props
}: ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn("z-50 animate-pop", PANEL, className)}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}
