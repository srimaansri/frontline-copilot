import { splitPlaceholders } from "@/lib/placeholders";

export interface RedactionBarProps {
  /** The placeholder's name without angle brackets, such as PHONE_NUMBER_1. */
  name: string;
}

/**
 * A redaction bar: a personal detail was here and was removed. It is the only
 * place where running text is set light on ink.
 */
export function RedactionBar({ name }: RedactionBarProps) {
  return (
    <code className="ph" title="A personal detail was removed here">
      {name}
    </code>
  );
}

export interface PlaceholderTextProps {
  text: string;
}

/** Redacted text, with each placeholder such as <PERSON_1> shown as a redaction bar. */
export function PlaceholderText({ text }: PlaceholderTextProps) {
  return (
    <>
      {splitPlaceholders(text).map((part, index) =>
        part.kind === "placeholder" ? (
          // The parts of one text never reorder, so the position is a stable key.
          <RedactionBar key={index} name={part.name} />
        ) : (
          part.value
        ),
      )}
    </>
  );
}
