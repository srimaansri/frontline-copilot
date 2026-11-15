import { cn } from "@/lib/cn";

import { Button, type ButtonProps } from "./button";
import { Tooltip } from "./tooltip";

export type IconButtonProps = Omit<ButtonProps, "size" | "aria-label"> & {
  /** Names the button for screen readers and is shown as its tooltip. */
  label: string;
};

/** A square button that holds only an icon. */
export function IconButton({ label, variant = "outline", className, ...props }: IconButtonProps) {
  return (
    <Tooltip label={label}>
      <Button
        size="icon"
        variant={variant}
        aria-label={label}
        className={cn(variant === "outline" && "text-ink-2 hover:text-ink", className)}
        {...props}
      />
    </Tooltip>
  );
}
