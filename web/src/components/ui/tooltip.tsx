import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ComponentProps, ReactNode } from "react";

export function TooltipProvider(props: ComponentProps<typeof TooltipPrimitive.Provider>) {
  return <TooltipPrimitive.Provider delayDuration={350} {...props} />;
}

export interface TooltipProps {
  /** The words shown on hover and on keyboard focus. */
  label: string;
  /** One element that can take a ref, such as a button. */
  children: ReactNode;
}

export function Tooltip({ label, children }: TooltipProps) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          collisionPadding={8}
          className="z-50 animate-fade rounded-md bg-fg px-2.5 py-1.5 text-xs font-medium text-bg"
        >
          {label}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
