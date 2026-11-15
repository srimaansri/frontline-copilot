/**
 * Redacted text carries placeholders such as <PERSON_1> or <PHONE_NUMBER_2>
 * where a personal detail used to be. These helpers find them so they can be
 * shown as redaction bars.
 */

/** One placeholder, capturing its name without the angle brackets. */
export const PLACEHOLDER_SOURCE = "<([A-Z][A-Z0-9_]*)>";

export type TextPart = { kind: "text"; value: string } | { kind: "placeholder"; name: string };

/** Text as it is to be matched by a regular expression, with nothing special in it. */
export function escapeForRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

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

export type QuestionPart = { kind: "text"; value: string } | { kind: "removed"; value: string };

/**
 * Find, in a question as it was typed, the personal details that were removed
 * from it. The redacted text is the same question with a placeholder where each
 * detail was, so the words between the placeholders locate the details.
 *
 * Returns null when nothing was removed, or when the two texts do not line up.
 */
export function findRemovedDetails(question: string, redacted: string): QuestionPart[] | null {
  const parts = splitPlaceholders(redacted);
  if (!parts.some((part) => part.kind === "placeholder")) {
    return null;
  }
  const pattern = parts
    .map((part) => (part.kind === "placeholder" ? "([^]+?)" : escapeForRegExp(part.value)))
    .join("");
  const match = new RegExp(`^${pattern}$`).exec(question);
  if (match === null) {
    return null;
  }
  let group = 0;
  return parts.map((part): QuestionPart => {
    if (part.kind === "text") {
      return part;
    }
    group += 1;
    return { kind: "removed", value: match[group] ?? "" };
  });
}
