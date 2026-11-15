import type {
  InlineCode,
  Link,
  Paragraph,
  Parent,
  PhrasingContent,
  Root,
  RootContent,
  Strong,
} from "mdast";

import { boldKind } from "./boldKind";
import { escapeForRegExp, PLACEHOLDER_SOURCE } from "./placeholders";

/** A citation marker becomes a link to this fragment plus its number. */
export const CITATION_HREF_PREFIX = "#source-";

/** A placeholder becomes inline code carrying this class. */
export const PLACEHOLDER_CLASS = "ph";

export interface AnnotationOptions {
  /** The citation numbers that have a source. Other markers are left as text. */
  citationNumbers: readonly number[];
  /** Ticket references the answer may quote, such as "ESC-B695DE84". They are read aloud. */
  references: readonly string[];
}

const WHOLE_PLACEHOLDER = new RegExp(`^${PLACEHOLDER_SOURCE}$`);

/** A lead-in ending in a colon, then one quoted passage: a line for the agent to say. */
const SCRIPT = /^([^":\n“]{3,80}:)\s*(["“][^]+["”])$/;

/**
 * Matches a citation marker such as [1] or [1, 2] (group 1), a placeholder
 * such as <PERSON_1> (group 2), or one of the known references (group 3).
 */
function markerPattern(references: readonly string[]): RegExp {
  const parts = [`\\[(\\d+(?:\\s*,\\s*\\d+)*)\\]`, PLACEHOLDER_SOURCE];
  if (references.length > 0) {
    parts.push(`(${references.map(escapeForRegExp).join("|")})`);
  }
  return new RegExp(parts.join("|"), "g");
}

function citationLink(number: number): Link {
  return {
    type: "link",
    url: `${CITATION_HREF_PREFIX}${number}`,
    children: [{ type: "text", value: String(number) }],
  };
}

function redactionBar(name: string): InlineCode {
  return {
    type: "inlineCode",
    value: name,
    data: { hProperties: { className: [PLACEHOLDER_CLASS] } },
  };
}

/** A reference is a fact read aloud, so it is highlighted like bold text, and set in mono. */
function reference(value: string): Strong {
  return {
    type: "strong",
    children: [{ type: "text", value }],
    data: { hProperties: { className: ["ref", "fact"] } },
  };
}

/** The words of a node, without its markup. */
function textOf(node: PhrasingContent): string {
  if ("value" in node) {
    return node.value;
  }
  return "children" in node ? node.children.map(textOf).join("") : "";
}

/** True when a bold run is all there is in its paragraph, which in a list is the item's own line. */
function fillsBlock(strong: Strong, parent: Parent): boolean {
  return (
    parent.type === "paragraph" &&
    parent.children.every(
      (child) => child === strong || (child.type === "text" && child.value.trim() === ""),
    )
  );
}

/**
 * Mark a bold run with what it is, so that only facts are highlighted:
 * "fact", "label", or nothing for plain bold. A fact with no space in it, such
 * as 1-800-555-0199, is read out as one thing, so it is also marked "keep" and
 * a line never breaks inside it. A label that fills its paragraph makes the
 * paragraph a label too.
 */
function markBold(strong: Strong, parent: Parent): void {
  const text = strong.children.map(textOf).join("");
  const alone = fillsBlock(strong, parent);
  const kind = boldKind(text, alone);
  const classes: string[] = kind === "plain" ? [] : [kind];
  if (kind === "fact" && text.length <= 30 && !/\s/.test(text)) {
    classes.push("keep");
  }
  if (classes.length > 0) {
    strong.data = { ...strong.data, hProperties: { className: classes } };
  }
  if (kind === "label" && alone) {
    parent.data = { ...parent.data, hProperties: { className: ["script-label"] } };
  }
}

function classed(className: string, value: string): Paragraph {
  return {
    type: "paragraph",
    children: [{ type: "text", value }],
    data: { hProperties: { className: [className] } },
  };
}

/** Split `Lead-in: "what to say"` into a label and a script line. Null for anything else. */
function splitScript(paragraph: Paragraph): [Paragraph, Paragraph] | null {
  const only = paragraph.children.length === 1 ? paragraph.children[0] : undefined;
  if (only?.type !== "text") {
    return null;
  }
  const match = SCRIPT.exec(only.value.trim());
  const label = match?.[1];
  const line = match?.[2];
  if (label === undefined || line === undefined) {
    return null;
  }
  return [classed("script-label", label), classed("script-line", line)];
}

interface Context {
  marker: RegExp;
  /** The same without references, for text that is already bold and so already highlighted. */
  markerInBold: RegExp;
  citations: ReadonlySet<number>;
}

/** Split one run of text around its markers. Returns null when it has none. */
function annotate(value: string, context: Context, inBold: boolean): PhrasingContent[] | null {
  const parts: PhrasingContent[] = [];
  let last = 0;
  for (const match of value.matchAll(inBold ? context.markerInBold : context.marker)) {
    const [whole, numbers, placeholder, quoted] = match;
    let replacement: PhrasingContent[] | null = null;
    if (placeholder !== undefined) {
      replacement = [redactionBar(placeholder)];
    } else if (quoted !== undefined) {
      replacement = [reference(quoted)];
    } else if (numbers !== undefined) {
      const cited = numbers.split(",").map((number) => Number(number.trim()));
      if (cited.every((number) => context.citations.has(number))) {
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

function walk(parent: Parent, context: Context, inBold = false): void {
  const children: RootContent[] = [];
  for (const child of parent.children) {
    if (child.type === "text") {
      children.push(...(annotate(child.value, context, inBold) ?? [child]));
      continue;
    }
    if (child.type === "html") {
      // A placeholder with no underscore, such as <PERSON>, parses as an HTML tag.
      const name = WHOLE_PLACEHOLDER.exec(child.value.trim())?.[1];
      children.push(name === undefined ? child : redactionBar(name));
      continue;
    }
    const script = child.type === "paragraph" ? splitScript(child) : null;
    if (script !== null) {
      for (const part of script) {
        walk(part, context);
        children.push(part);
      }
      continue;
    }
    if (child.type === "strong" && !inBold) {
      markBold(child, parent);
    }
    // Text that is already a link stays one link.
    if ("children" in child && child.type !== "link" && child.type !== "linkReference") {
      walk(child, context, inBold || child.type === "strong");
    }
    children.push(child);
  }
  parent.children = children;
}

/**
 * A remark plugin for answers. It turns citation markers into links the
 * renderer shows as chips, placeholders into redaction bars, the hand-off
 * reference into a highlighted fact, and a quoted line for the customer into
 * a script line.
 */
export function remarkAnnotations(options: AnnotationOptions) {
  const context: Context = {
    marker: markerPattern(options.references),
    markerInBold: markerPattern([]),
    citations: new Set(options.citationNumbers),
  };
  return (tree: Root): void => {
    walk(tree, context);
  };
}
