import { cn } from "@/lib/cn";
import { splitPlaceholders } from "@/lib/placeholders";

export interface PlaceholderChipProps {
  /** The placeholder's name without angle brackets, such as PHONE_NUMBER_1. */
  name: string;
  className?: string;
}

/** A placeholder that stands where a personal detail was removed. */
export function PlaceholderChip({ name, className }: PlaceholderChipProps) {
  return (
    <code
      title="A placeholder for a personal detail"
      className={cn(
        "placeholder-chip mx-0.5 inline-block rounded-sm border bg-surface-muted px-1.5 py-px align-baseline",
        "font-mono text-[0.76em] leading-normal font-medium whitespace-nowrap text-fg-muted",
        className,
      )}
    >
      {name}
    </code>
  );
}

export interface PlaceholderTextProps {
  text: string;
  /** Extra classes for each chip, for example on a coloured background. */
  chipClassName?: string;
}

/** Redacted text, with each placeholder such as <PERSON_1> shown as a chip. */
export function PlaceholderText({ text, chipClassName }: PlaceholderTextProps) {
  return (
    <>
      {splitPlaceholders(text).map((part, index) =>
        part.kind === "placeholder" ? (
          // The parts of one text never reorder, so the position is a stable key.
          <PlaceholderChip key={index} name={part.name} className={chipClassName} />
        ) : (
          part.value
        ),
      )}
    </>
  );
}
