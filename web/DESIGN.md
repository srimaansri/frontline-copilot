# Design: Signal and Script

This is the design system of the Frontline Copilot web interface. The tokens live in `src/index.css`, the icons in `src/components/icons/`. If this file and the code disagree, the code is wrong: fix it, or change this file in the same commit.

## The concept

A support agent works from a script, so the copilot's answer is set like one: the facts to read aloud are run over with a highlighter, and anything private is struck out with a redaction bar. Whatever the copilot wrote sits on a card with one corner cut like a SIM card, so shape alone says who is speaking. Four signal bars stand for its four stages of work, and the steps it took are drawn as a route with a station per step.

## Colour tokens

Cobalt on cool neutrals. Every neutral leans toward cobalt; there is no pure grey. The dark theme is midnight navy, designed on its own and not an inversion. Components use only these tokens (as Tailwind classes such as `bg-surface` or `text-ink-2`); Tailwind's default palette is removed.

| Token | Light | Dark | Used for |
| --- | --- | --- | --- |
| `paper` | `#F2F4FA` | `#111B3D` | App background |
| `surface` | `#FFFFFF` | `#1A2650` | Cards, bars, inputs |
| `sunken` | `#E8ECF6` | `#0C1330` | The copilot's side rail; an agent's question; a customer's turn |
| `line` | `#C9D1E3` | `#2F3E6C` | Hairlines between regions |
| `line-strong` | `#7482A8` | `#6878AA` | Control borders and the route. At least 3:1 on every background |
| `edge` | `#0F1833` | `#8E9CCB` | Outline of anything the copilot wrote |
| `ink` | `#0F1833` | `#EDF1FC` | Text; the fill that means "you are here" |
| `ink-2` | `#38425F` | `#C2CAE4` | Secondary text, labels |
| `ink-3` | `#586384` | `#98A4C8` | Hints and placeholders |
| `brand` | `#1D43D8` | `#4868F5` | Cobalt fills: the send button, the primary button, the mark |
| `brand-text` | `#1D43D8` | `#9DB1FF` | Cobalt on a surface: links, citation chips, live bars, the focus ring |
| `brand-tint` | `#E1E8FC` | `#24346E` | The selected row in the calls list |
| `on-brand` | `#FFFFFF` | `#FFFFFF` | Text and icons on a cobalt fill |
| `hi` | `#D9F23E` | `#D9F23E` | The highlighter |
| `hi-ink` | `#0F1833` | `#0F1833` | Text on the highlighter |
| `redact` | `#0F1833` | `#C2CAE4` | The redaction bar |
| `on-redact` | `#F2F4FA` | `#111B3D` | The placeholder's name on the bar |
| `ok` / `ok-tint` | `#0B6B47` / `#DDF2E6` | `#5FD3A0` / `#10382E` | Passed, resolved |
| `notice` / `notice-tint` | `#8A2F7B` / `#F6E4F1` | `#E79AD8` / `#3A1C3D` | Something was changed for you |
| `warn` / `warn-tint` | `#8A5300` / `#FBEFD3` | `#F2B950` / `#3D2E0E` | Needs a person |
| `block` / `block-tint` | `#B3261E` / `#FBE4E1` | `#FF8F85` / `#46191B` | Refused |
| `knock` | `#FFFFFF` | `#111B3D` | The glyph knocked out of a status shape |

Contrast, checked for every pair in use (WCAG AA):

- Text: `ink`, `ink-2` and `ink-3` are at least 5.0:1 on `paper`, `surface` and `sunken` in both themes.
- Cobalt: `brand-text` is at least 5.6:1 on every background it sits on; white on `brand` is 7.4:1 light and 4.6:1 dark.
- Status colours are at least 5.1:1 on `paper`, `surface`, `sunken` and `brand-tint` in both themes.
- `hi-ink` on `hi` is 13.9:1. `on-redact` on `redact` is 15.9:1 light and 10.3:1 dark.
- `line-strong` is between 3.2:1 and 4.2:1 on every background. It is used for borders and the route, never for text.

## Type

Three faces, bundled from `@fontsource-variable` packages, latin subset only (`src/fonts.css`).

| Face | Role | Why |
| --- | --- | --- |
| Bricolage Grotesque, 700 | Display: the headline, view titles, section titles, the product name. Never for anything read aloud. | A grotesque with ink traps and slightly uneven curves, drawn from printed matter. It gives a console a voice with some grain in it, like the header on a printed call script. |
| Atkinson Hyperlegible Next, 400 / 600 / 700 | Text: everything read or operated. | Drawn for low-vision readers, with look-alike characters pulled apart. Agents read fees and phone numbers aloud from it, and a 1 mistaken for an l is a wrong number given to a customer. |
| Atkinson Hyperlegible Mono, 400 / 600 / 700 | Codes and readouts, never words: placeholders, call ids, references, citation numerals, list numerals, timings, counts. | The same skeleton as the text face at a fixed width, so a reference can be read out character by character without losing your place. |

One scale. Nothing is set outside it.

| Token | Size | Used for |
| --- | --- | --- |
| `text-label` | 12.5px | Cues such as "Agent" and "Privacy", status words, tags, the footer |
| `text-meta` | 14px | Step details, readouts, hints |
| `text-ui` | 15.5px | Controls and body text of the interface. The page default |
| `text-read` | 18px | Everything read aloud: answers, questions, transcripts |
| `text-title` | 22px | Section titles, the product name, a summary's intent |
| `text-view` | 30px | View titles: "Calls", a call's category |
| `text-head` | 46px | The empty-state headline |

- Headings use `text-wrap: balance`.
- On a phone the headline drops to `text-view`, a call's category to `text-title`, and the product name to `text-read`, so the top bar fits on one row. That is the only place the display face is set below 22px.

## Motifs

Each device means one thing. Do not use a device for anything outside its row.

| Device | Means | Where it may be used |
| --- | --- | --- |
| Highlighter (`.hi`, `strong.fact` in `.answer`) | Say this out loud. | Bold facts in a copilot answer (see "Which bold is highlighted" below), and the hand-off reference in it. The eyes of the mark. Nowhere else: not buttons, headings, labels, status or selection. |
| Redaction bar (`.ph`) | A personal detail was here and was removed. | Placeholders such as `PERSON_1`, wherever redacted text is shown: "As processed" lines, transcripts, summaries, answers. No other running text is set light on ink. |
| Underline in the notice colour (`.pii`) | This detail in your question was replaced. | The agent's own question, under the words that were removed. |
| SIM chamfer (`.sim`) | The copilot wrote this. | The answer card, the pending card, the summary card and its "Summarizing" card, and the mark. People's words, buttons, inputs and error notices keep 3px corners. |
| Signal bars (`.bars`) | The copilot's own state. One bar per stage: privacy, request check, lookup, answer check. | Seeking on the pending card and while summarizing. All four steady on the "What's running" button. Still and in ink as the stage key on the empty state. Never a rating, never decoration. |
| Status shapes | Circle OK, square Notice, triangle Warning, octagon Blocked. Colour and the word repeat what the shape already says. | Steps, the tally of a run, the legend, call status and its filters, error notices, the "What's running" rows, "Saved". |
| Citation chip (`.cite`) | This claim has a source. | After a claim in an answer and in front of its source, so the eye can match them. It fills with cobalt when its source is the one in focus. |
| Ink fill | You are here; this is the one that is on. | The current view, the active filter, the theme in use, the "Sources and steps" button whose details are on show, the vote that was cast, and the tag at the end of a hand-off (where the request is now). |
| Cobalt | You can press this. | Send, the primary button, links, citation chips, the arrow on an example and on a source, the bars while live, the focus ring, and the mark. Never a status, never a background wash. The selected call is the one exception to "wash": it takes `brand-tint` with an ink outline, so the status colours inside it stay legible. |
| Route (`.route`) | What the copilot did, in order: one line, a station per step. | "What the copilot did" only. Drawn in `line-strong`; the status shapes carry the colour. |
| Solid leg / dashed leg | Solid: done by the copilot. Dashed: passed to a person. | The route and its legend. The hand-off leaves the main line at 45 degrees on a solid leg, then runs dashed to its tag, while the main line carries on to the answer checks. |
| Dashed outline | A label about the data itself: it is synthetic, or mocked. | The "Demo, synthetic data" tag, and the "Mock mode" tag and note. |
| Sunken tone | The copilot's working, as opposed to its answer. | The side rail with sources and steps, the summary rail, and the panel under an answer on a narrow screen. Also the agent's question and a customer's turn. |

Which bold is highlighted. The model uses bold for facts, for labels and for stray words, and the highlighter is only for facts. The rule is one function, `boldKind` in `src/lib/boldKind.ts`:

- **Label**, not highlighted: a bold run that is the whole of its paragraph or list item ("How to request a waiver"), or that ends with a colon ("Next step:"). It is set bold in `ink-2`. When it fills a paragraph, the paragraph takes the label style used for "What to tell the customer:".
- **Plain bold**, not highlighted: one word of four letters or fewer with no digit in it ("or", "and", "not").
- **Fact**, highlighted: every other bold run ("$5", "611", "1-800-555-0199", "one-time waiver"). A fact with no space in it never breaks across lines.

Numbered lists in an answer. The numerals are drawn in mono by a CSS counter. A list that bullets interrupt arrives as two lists, the second with a `start`; it carries on from that number, and the bullets are set in under the step they belong to, so the whole reads as one set of steps.

Shape and elevation:

- One radius, 3px (`rounded-box`), on controls and on people's words. Chips are 2px (`rounded-chip`). There are no pills and no fully rounded buttons.
- Borders and background tone carry the structure. Only popovers and tooltips cast a shadow (`shadow-pop`).
- The focus ring is cobalt, 2px, offset by 2px, for keyboard focus only.
- Motion is short and can be turned off: `prefers-reduced-motion` stops every animation and transition, and the seeking bar holds still, half filled.

## Icons

All icons are drawn for this product. There is no icon library.

- Grid: 24 by 24, built on the `Icon` base in `src/components/icons/Icon.tsx`.
- Stroke: 1.75 at 20 and 24px, 2 at 16px, 1.6 at 32px. Flat line ends, mitred joins, colour from the text.
- Corners: runs at 45 and 90 degrees. Where another set would round a corner, this one cuts it. Circles become eight-sided: the search lens, the faces, the moon, the retry loop.
- Fill: none, except the redaction bar in the privacy icon.
- Sizes: 16, 20, 24 or 32. Every icon must read at 16.
- Decorative by default (`aria-hidden`). Pass `title` only when the icon stands alone with no words beside it.
- Status stamps (`StatusStamp.tsx`) are the exception to the stroke rule: solid shapes on a 16 grid with the glyph knocked out, so that shape survives at 14px and without colour.
- The mark (`CopilotMark.tsx`) is a robot whose head is a SIM card: the top-right corner is cut, the eyes are the highlighter, and the antenna sends two signal arcs drawn with the same cut corner. `public/favicon.svg` is the same drawing with the colours written in.
- The mood faces share one eight-sided face and one pair of eyes; only the mouth changes.
