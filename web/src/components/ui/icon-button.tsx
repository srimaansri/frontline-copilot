import { Button, type ButtonProps } from "./button";
import { Tooltip } from "./tooltip";

export type IconButtonProps = Omit<ButtonProps, "size" | "aria-label"> & {
  /** Names the button for screen readers and is shown as its tooltip. */
  label: string;
};

/** A square button that holds only an icon. */
export function IconButton({ label, variant = "ghost", ...props }: IconButtonProps) {
  return (
    <Tooltip label={label}>
      <Button size="icon" variant={variant} aria-label={label} {...props} />
    </Tooltip>
  );
}
