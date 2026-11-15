/**
 * Checks the colour tokens against WCAG 2.1 AA.
 *
 * Reads the light and dark token blocks out of src/index.css, measures every
 * pair listed in contrast-pairs.mjs, prints a table, and exits with status 1
 * if any pair is under its ratio.
 *
 *   npm run check:contrast
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { PAIRS } from "./contrast-pairs.mjs";

const STYLESHEET = fileURLToPath(new URL("../src/index.css", import.meta.url));

/** The ratio each kind of pair has to reach. */
const REQUIRED = { body: 4.5, large: 3, ui: 3 };

/** The block that declares each theme is the one that sets its `color-scheme`. */
const THEMES = [
  { name: "light", selector: ":root", scheme: "light" },
  { name: "dark", selector: ".dark", scheme: "dark" },
];

/**
 * The colour tokens of one theme, by name without the leading dashes.
 * @returns {Map<string, string>}
 */
function readTokens(css, { name, selector, scheme }) {
  const blocks = css.matchAll(new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")}\\s*\\{([^}]*)\\}`, "g"));
  for (const [, body] of blocks) {
    if (new RegExp(`color-scheme:\\s*${scheme}\\b`).test(body)) {
      const tokens = new Map();
      for (const [, token, hex] of body.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b/g)) {
        tokens.set(token, hex.toLowerCase());
      }
      return tokens;
    }
  }
  throw new Error(`No ${name} token block (${selector} with color-scheme: ${scheme}) in ${STYLESHEET}`);
}

/** Relative luminance of an sRGB colour, as WCAG 2.1 defines it. */
function luminance(hex) {
  const channels = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);
  const [red, green, blue] = channels.map((value) =>
    value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(foreground, background) {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

const css = readFileSync(STYLESHEET, "utf8");
const rows = [];
let failures = 0;

for (const theme of THEMES) {
  const tokens = readTokens(css, theme);
  for (const [foreground, background, kind, where] of PAIRS) {
    const fg = tokens.get(foreground);
    const bg = tokens.get(background);
    if (fg === undefined || bg === undefined) {
      throw new Error(`The ${theme.name} theme has no token "${fg === undefined ? foreground : background}".`);
    }
    const ratio = contrast(fg, bg);
    const passes = ratio >= REQUIRED[kind];
    failures += passes ? 0 : 1;
    rows.push({ theme: theme.name, foreground, background, kind, ratio, passes, where });
  }
}

const width = (key) => Math.max(key.length, ...rows.map((row) => String(row[key]).length));
const columns = ["theme", "foreground", "background", "kind"];
const header = [...columns.map((key) => key.padEnd(width(key))), "ratio  ", "needs", "    ", "where"];
console.log(header.join("  "));
for (const row of rows) {
  console.log(
    [
      ...columns.map((key) => String(row[key]).padEnd(width(key))),
      `${row.ratio.toFixed(2).padStart(5)}:1`,
      `${REQUIRED[row.kind]}:1`.padEnd(5),
      row.passes ? "ok  " : "FAIL",
      row.where,
    ].join("  "),
  );
}

console.log("");
if (failures > 0) {
  console.error(`${failures} of ${rows.length} pairs are under their ratio.`);
  process.exit(1);
}
console.log(`All ${rows.length} pairs pass (${PAIRS.length} pairs in ${THEMES.length} themes).`);
