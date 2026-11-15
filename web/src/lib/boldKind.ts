/**
 * What a bold run in a copilot answer is.
 *
 * - "fact": something the agent reads out, such as "$5" or "one-time waiver". Highlighted.
 * - "label": a heading-like lead-in, such as "How to request a waiver". Bold, not highlighted.
 * - "plain": a stray emphasised word, such as "or". Bold, not highlighted.
 */
export type BoldKind = "fact" | "label" | "plain";

/** A stray word is at most this many letters long. */
const SHORT_WORD_LETTERS = 4;

/**
 * Decide whether a bold run is a fact to say out loud. The highlighter means
 * "say this", so it must not land on a label or on a stray word. Model answers
 * use bold for all three.
 *
 * @param text The words of the bold run.
 * @param wholeBlock True when the run is all there is in its paragraph or list item.
 */
export function boldKind(text: string, wholeBlock: boolean): BoldKind {
  const words = text.trim();
  // A run that stands alone, or that ends in a colon, introduces what follows.
  if (wholeBlock || words.endsWith(":")) {
    return "label";
  }
  // One short word with no digit in it, such as "or", "and" or "not", is emphasis, not a fact.
  const letters = words.replace(/[^\p{L}]/gu, "").length;
  if (!/\d/.test(words) && !/\s/.test(words) && letters <= SHORT_WORD_LETTERS) {
    return "plain";
  }
  return "fact";
}
