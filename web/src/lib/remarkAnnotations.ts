import type { InlineCode, Link, Parent, PhrasingContent, Root, RootContent } from "mdast";

import { PLACEHOLDER_SOURCE } from "./placeholders";

/** A citation marker becomes a link to this fragment plus its number. */
export const CITATION_HREF_PREFIX = "#source-";

/** A placeholder becomes inline code carrying this class. */
export const PLACEHOLDER_CLASS = "placeholder-chip";

export interface AnnotationOptions {
  /** The citation numbers that have a source. Other markers are left as text. */
  citationNumbers: readonly number[];
}

// A citation marker, such as [1] or [1, 2], or a placeholder such as <PERSON_1>.
const MARKER = new RegExp(`\\[(\\d+(?:\\s*,\\s*\\d+)*)\\]|${PLACEHOLDER_SOURCE}`, "g");
const WHOLE_PLACEHOLDER = new RegExp(`^${PLACEHOLDER_SOURCE}$`);

function citationLink(number: number): Link {
  return {
    type: "link",
    url: `${CITATION_HREF_PREFIX}${number}`,
    children: [{ type: "text", value: String(number) }],
  };
}

function placeholderChip(name: string): InlineCode {
  return {
    type: "inlineCode",
    value: name,
    data: { hProperties: { className: [PLACEHOLDER_CLASS] } },
  };
}

/** Split one run of text around its markers. Returns null when it has none. */
function annotate(value: string, known: ReadonlySet<number>): PhrasingContent[] | null {
  const parts: PhrasingContent[] = [];
  let last = 0;
  for (const match of value.matchAll(MARKER)) {
    const [whole, numbers, placeholder] = match;
    let replacement: PhrasingContent[] | null = null;
    if (placeholder !== undefined) {
      replacement = [placeholderChip(placeholder)];
    } else if (numbers !== undefined) {
      const cited = numbers.split(",").map((number) => Number(number.trim()));
      if (cited.every((number) => known.has(number))) {
        replacement = cited.map(citationLink);
      }
    }
    if (replacement === null) {
      continue;
    }
    if (match.index > last) {
      parts.push({ type: "text", value: value.slice(last, match.index) });
    }
    parts.push(...replacement);
    last = match.index + whole.length;
  }
  if (parts.length === 0) {
    return null;
  }
  if (last < value.length) {
    parts.push({ type: "text", value: value.slice(last) });
  }
  return parts;
}

function walk(parent: Parent, known: ReadonlySet<number>): void {
  const children: RootContent[] = [];
  for (const child of parent.children) {
    if (child.type === "text") {
      children.push(...(annotate(child.value, known) ?? [child]));
      continue;
    }
    if (child.type === "html") {
      // A placeholder with no underscore, such as <PERSON>, parses as an HTML tag.
      const name = WHOLE_PLACEHOLDER.exec(child.value.trim())?.[1];
      children.push(name === undefined ? child : placeholderChip(name));
      continue;
    }
    // Text that is already a link stays one link.
    if ("children" in child && child.type !== "link" && child.type !== "linkReference") {
      walk(child, known);
    }
    children.push(child);
  }
  parent.children = children;
}

/**
 * A remark plugin for answers. It turns citation markers into links the
 * renderer shows as chips, and placeholders into inline code it shows as chips.
 */
export function remarkAnnotations(options: AnnotationOptions) {
  const known = new Set(options.citationNumbers);
  return (tree: Root): void => {
    walk(tree, known);
  };
}
