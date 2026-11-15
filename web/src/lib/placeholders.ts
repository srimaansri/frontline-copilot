/**
 * Redacted text carries placeholders such as <PERSON_1> or <PHONE_NUMBER_2>
 * where a personal detail used to be. These helpers find them so they can be
 * shown as chips.
 */

/** One placeholder, capturing its name without the angle brackets. */
export const PLACEHOLDER_SOURCE = "<([A-Z][A-Z0-9_]*)>";

export type TextPart = { kind: "text"; value: string } | { kind: "placeholder"; name: string };

/** Split text into plain runs and placeholders, in order. */
export function splitPlaceholders(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(new RegExp(PLACEHOLDER_SOURCE, "g"))) {
    const name = match[1];
    if (name === undefined) {
      continue;
    }
    if (match.index > last) {
      parts.push({ kind: "text", value: text.slice(last, match.index) });
    }
    parts.push({ kind: "placeholder", name });
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push({ kind: "text", value: text.slice(last) });
  }
  return parts;
}
