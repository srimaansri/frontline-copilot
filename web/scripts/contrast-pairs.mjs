/**
 * Every foreground/background pair of colour tokens the components use.
 * check-contrast.mjs measures each one in both themes.
 *
 * Kinds, with the WCAG 2.1 AA ratio each has to reach:
 *   "body"  4.5:1  text below 18.66px bold or 24px regular
 *   "large" 3:1    larger text
 *   "ui"    3:1    icons, status shapes, control borders, focus rings
 *
 * When a component starts to put one token on another, add the pair here.
 * Left out on purpose:
 *   - `line` hairlines between rows and regions: they separate, they do not
 *     mark a control, and nothing depends on seeing them.
 *   - the highlighter band against the card: the fact under it is also bold.
 *   - skeleton blocks, and anything at 50% opacity because it is disabled.
 */

/** @typedef {"body" | "large" | "ui"} Kind */
/** @typedef {[foreground: string, background: string, kind: Kind, where: string]} Pair */

/** @type {Pair[]} */
export const PAIRS = [
  // --- Text in ink ---------------------------------------------------------------------------
  ["ink", "paper", "body", "Text on the page: call titles, empty states"],
  ["ink", "surface", "body", "Answers, list rows, buttons, popover"],
  ["ink", "sunken", "body", "Agent's question, customer's turn, step titles on the rail"],
  ["ink", "brand-tint", "body", "Selected call row"],
  ["ink", "warn-tint", "body", "Hand-off banner"],

  // --- Secondary text ------------------------------------------------------------------------
  ["ink-2", "paper", "body", "Lede, cues, response time, call caption, stage key"],
  ["ink-2", "surface", "body", "Cues, tool badges, popover labels, data tags"],
  ["ink-2", "sunken", "body", "Step details, cues and legend on the rail"],

  // --- Hints ---------------------------------------------------------------------------------
  ["ink-3", "paper", "body", "Footer, hint under the question box, stage numerals"],
  ["ink-3", "surface", "body", "Placeholder text, example hints, list numerals"],
  ["ink-3", "sunken", "body", "Example hint while its card is pressed"],

  // --- Under the pointer and while pressed: sunken, then line ----------------------------------
  ["ink", "line", "body", "View switcher and filter chip while pressed"],
  ["ink-2", "line", "body", "Filter chip label while pressed"],
  ["ok", "line", "ui", "Status shape in a filter chip while pressed"],
  ["notice", "line", "ui", "Status shape in a filter chip while pressed"],
  ["warn", "line", "ui", "Status shape in a filter chip while pressed"],

  // --- Cobalt --------------------------------------------------------------------------------
  ["brand-text", "surface", "body", "Links, citation numerals, arrows on cards"],
  ["brand-text", "brand-tint", "body", "Citation chip under the pointer"],
  ["brand-text", "paper", "ui", "Focus ring on the page; field focus ring"],
  ["brand-text", "sunken", "ui", "Focus ring on the rail"],
  ["on-brand", "brand", "body", "Primary button, send button, selected citation chip"],
  ["on-brand", "brand-strong", "body", "Primary button under the pointer"],
  ["on-brand", "brand-press", "body", "Primary button and citation chip while pressed"],
  ["mark", "surface", "ui", "The mark in the top bar and on a card"],
  ["mark", "paper", "ui", "The mark on the empty state"],
  ["mark", "sunken", "ui", "The mark on the rail"],

  // --- Ink fill: "you are here" ---------------------------------------------------------------
  ["surface", "ink", "body", "Current view, active filter, hand-off tag, tooltip"],
  ["surface", "ink-2", "body", "An ink-filled button under the pointer"],
  ["surface", "ink-3", "body", "An ink-filled button while pressed"],

  // --- The two pen marks ---------------------------------------------------------------------
  ["hi-ink", "hi", "body", "Highlighted facts in an answer"],
  ["on-redact", "redact", "body", "Redaction bar"],

  // --- Status: words and shapes in the status colour --------------------------------------------
  ["ok", "paper", "body", "Call status in the call header, Saved"],
  ["ok", "surface", "body", "Call status in the list, popover rows, Positive mood, Saved on a wrap-up"],
  ["ok", "sunken", "body", "Step status on the rail"],
  ["ok", "brand-tint", "body", "Call status in the selected row"],
  ["notice", "paper", "body", "Call status in the call header; privacy icon by a question"],
  ["notice", "surface", "body", "Call status in the list"],
  ["notice", "sunken", "body", "Step status on the rail"],
  ["notice", "brand-tint", "body", "Call status in the selected row"],
  ["warn", "paper", "body", "Call status in the call header; border of the hand-off banner"],
  ["warn", "surface", "body", "Call status in the list, Negative mood, error notice"],
  ["warn", "sunken", "body", "Step status on the rail"],
  ["warn", "brand-tint", "body", "Call status in the selected row"],
  ["warn", "warn-tint", "ui", "Icon in the hand-off banner"],
  ["block", "surface", "body", "Not responding, in the popover"],
  ["block", "sunken", "body", "Step status on the rail"],
  ["knock", "ok", "ui", "Glyph knocked out of the OK circle"],
  ["knock", "notice", "ui", "Glyph knocked out of the Notice square"],
  ["knock", "warn", "ui", "Glyph knocked out of the Warning triangle"],
  ["knock", "block", "ui", "Glyph knocked out of the Blocked octagon"],

  // --- Boundaries ----------------------------------------------------------------------------
  ["line-strong", "paper", "ui", "Control borders on the page; dashed data tags"],
  ["line-strong", "surface", "ui", "Control borders, unfilled signal bars"],
  ["line-strong", "sunken", "ui", "The route and its legs on the rail"],
  ["edge", "paper", "ui", "Outline of the answer card"],
  ["edge", "sunken", "ui", "Outline of the summary card on the rail"],
  ["edge", "brand-tint", "ui", "Outline of the selected call row"],
];
