import * as PopoverPrimitive from "@radix-ui/react-popover";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Popover(props: ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root {...props} />;
}

export function PopoverTrigger(props: ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger {...props} />;
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
        className={cn(
          "z-50 w-80 max-w-[calc(100vw-1.5rem)] rounded-lg border bg-surface p-4 text-fg",
          "origin-(--radix-popover-content-transform-origin) animate-pop shadow-lg shadow-black/10",
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}
