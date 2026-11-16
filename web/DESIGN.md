# Design: Signal and Script

This is the design system of Cue, the Frontline Copilot web interface. The tokens live in `src/index.css`, the icons in `src/components/icons/`. If this file and the code disagree, the code is wrong: fix it, or change this file in the same commit.

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
| `brand` | `#1D43D8` | `#4868F5` | Cobalt fills: the send button, the primary button |
| `brand-strong` | `#1838BF` | `#3D5CE8` | A cobalt fill under the pointer |
| `brand-press` | `#142F9F` | `#3350D2` | A cobalt fill while pressed |
| `brand-text` | `#1D43D8` | `#9DB1FF` | Cobalt on a surface: links, citation chips, live bars, the focus ring |
| `brand-tint` | `#E1E8FC` | `#24346E` | The selected row in the calls list |
| `mark` | `#1D43D8` | `#6480FF` | The head of the brand mark. Lighter than the fill in the dark theme, so the mark holds on the bar (4.2:1) |
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

Contrast is checked by a script, not by eye. `npm run check:contrast` (also run by `npm run lint`) reads the two token blocks out of `src/index.css`, measures every foreground and background pair listed in `scripts/contrast-pairs.mjs` in both themes, and fails if one is under WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text, icons, control borders and focus rings. When a component puts one token on another for the first time, add the pair to that table. The pairs with the least room today:

- `line-strong` on `sunken`, light: 3.2:1 (needs 3). It is used for borders and the route, never for text.
- `on-brand` on `brand`, dark: 4.6:1 (needs 4.5).
- `ink-3` on `sunken`, light: 5.0:1 (needs 4.5).

## Type

Three faces, bundled from `@fontsource-variable` packages, latin subset only (`src/fonts.css`).

| Face | Role | Why |
| --- | --- | --- |
| Schibsted Grotesk, 700 | Display: the headline, view titles, section titles, the product name. Never for anything read aloud. | A sturdy grotesque drawn for a news publisher's headlines. Its wide, even letters have the proportions of the mark, so the name sits beside the mark as one piece, and it is calm enough to leave the character to the mark and the highlighter. |
| Atkinson Hyperlegible Next, 400 / 600 / 700 | Text: everything read or operated. | Drawn for low-vision readers, with look-alike characters pulled apart. Agents read fees and phone numbers aloud from it, and a 1 mistaken for an l is a wrong number given to a customer. Its zero is always slashed; there is no plain one. That is accepted on purpose: every figure on these screens is one somebody may read out. |
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
- Display type is set with three classes and nowhere else: `display-title` (700, tracking -0.012em), `display-view` (700, -0.018em) and `display-head` (700, -0.024em). The face has no optical-size axis, so the tracking does that work: the larger the size, the tighter it is set.
- The faces were chosen by comparison, not by habit: eight sets on the real screens, then the three jobs taken apart. The sheets and the reasons are in [design/type](../design/type).
- On a phone the headline drops to `text-view`, a call's category to `text-title`, and the product name to `text-read`, so the top bar fits on one row. That is the only place the display face is set below 22px.

## Motifs

Each device means one thing. Do not use a device for anything outside its row.

| Device | Means | Where it may be used |
| --- | --- | --- |
| Highlighter (`.hi`, `strong.fact` in `.answer`) | Say this out loud. | Bold facts in a copilot answer (see "Which bold is highlighted" below), and the hand-off reference in it. Nowhere else: not buttons, headings, labels, status or selection. |
| Redaction bar (`.ph`) | A personal detail was here and was removed. | Placeholders such as `PERSON_1`, wherever redacted text is shown: "As processed" lines, transcripts, summaries, answers. No other running text is set light on ink. |
| Underline in the notice colour (`.pii`) | This detail in your question was replaced. | The agent's own question, under the words that were removed. |
| SIM chamfer (`.sim`) | The copilot wrote this. | The answer card, the pending card, the summary card and its "Summarizing" card, the "Drafting the wrap-up" card, the suggested next step in call assist, and the mark. People's words, buttons, inputs and error notices keep 3px corners. So do the two drafts an agent acts on, a hand-off and a wrap-up, and everything in call assist that the copilot did not write: the help article, which is a source, and the reminders and the hint to hand off, which come from rules. |
| Signal bars (`.bars`) | The copilot's own state. One bar per stage: privacy, request check, lookup, answer check. | Seeking on the pending card, while summarizing and while drafting a wrap-up, and in the head of the call assist panel while the turn on show is being read. All four steady on the "What's running" button and in that head once the panel is up to date; two, still, when a turn could not be read and the panel is behind. Still and in ink as the stage key on the empty state. Never a rating, never decoration. |
| Status shapes | Circle OK, square Notice, triangle Warning, octagon Blocked. Colour and the word repeat what the shape already says. | Steps, the tally of a run, the legend, call status and its filters, error notices, the "What's running" rows, "Saved" on a wrap-up, and how the call ended in a saved wrap-up. In call assist: the identity check (triangle until an identity question is answered, circle after), each reminder from the rules (triangle), and the square with "New at turn 4" on a part that came up at the turn on show. |
| Citation chip (`.cite`) | This claim has a source. | After a claim in an answer and in front of its source, so the eye can match them. Outlined at rest, tinted under the pointer, filled with cobalt when its source is the one in focus. |
| Ink fill | You are here; this is the one that is on. | The current view, the active filter, the theme in use, the "Sources and steps" button whose details are on show, the vote that was cast, the tag at the end of a hand-off (where the request is now), and "Replay with assist" while the call is in its replay. |
| Cobalt | You can press this. | Send, the primary button, links, citation chips, the arrow on an example and on a source, the bars while live, the focus ring, and the mark. Never a status, never a background wash. The selected call is the one exception to "wash": it takes `brand-tint` with an ink outline, so the status colours inside it stay legible. |
| Route (`.route`) | What the copilot did, in order: one line, a station per step. | "What the copilot did" only. Drawn in `line-strong`; the status shapes carry the colour. |
| Solid leg / dashed leg | Solid: done by the copilot. Dashed: passed to a person. | The route and its legend. The hand-off leaves the main line at 45 degrees on a solid leg, then runs dashed to its tag, while the main line carries on to the answer checks. |
| Dashed outline | A label about the data itself: it is synthetic, replayed, or not stored yet. | The "Demo, synthetic data" tag, the "Recorded answers" tag and note, "Not sent yet" on a hand-off draft, "Not saved yet" on a wrap-up draft, and "Replay of a recorded call" on the call assist panel. |
| Sunken tone | The copilot's working, as opposed to its answer. | The side rail with sources and steps, the summary rail, the call assist panel, and the panel under an answer on a narrow screen. Also the agent's question and a customer's turn. |

Which bold is highlighted. The model uses bold for facts, for labels and for stray words, and the highlighter is only for facts. The rule is one function, `boldKind` in `src/lib/boldKind.ts`:

- **Label**, not highlighted: a bold run that is the whole of its paragraph or list item ("How to request a waiver"), or that ends with a colon ("Next step:"). It is set bold in `ink-2`. When it fills a paragraph, the paragraph takes the label style used for "What to tell the customer:".
- **Plain bold**, not highlighted: one word of four letters or fewer with no digit in it ("or", "and", "not").
- **Fact**, highlighted: every other bold run ("$5", "611", "1-800-555-0199", "one-time waiver"). A fact with no space in it never breaks across lines.

Numbered lists in an answer. The numerals are drawn in mono by a CSS counter. A list that bullets interrupt arrives as two lists, the second with a `start`; it carries on from that number, and the bullets are set in under the step they belong to, so the whole reads as one set of steps.

## Spacing, shape and motion

Spacing is one scale on a 4px base (`--spacing`): `p-4` is 16px, `gap-6` is 24px. Use whole steps, plus the half step `0.5` (2px) for optical nudges. There are no one-off pixel values in the components.

- Steps in use: 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 18.
- Control heights sit on the same grid: 28 (tool badge), 36 (small button, icon button, view switcher), 40 (button), 44 (search box, send button, one line of the question box), 48 (list row).
- Widths of text columns come from Tailwind's container scale (`max-w-md`, `max-w-2xl`, `max-w-3xl`, `max-w-5xl`, `max-w-7xl`). Rails are `w-88`, `w-96`, `w-100` and `w-110`.
- Two things are sized in em, so that they follow the text they sit in: the padding of the highlighter and of the redaction bar.
- A drawn glyph keeps its own geometry: the widths of the signal bars, the 6px list bullet, the 28px sidestep of the hand-off branch.
- Running text is set with `text-wrap: pretty`, and headings with `balance`, so a paragraph does not end on one short word.
- On a touch screen the hint under the question box drops its keyboard sentence. A phone has no Shift+Enter, and the fixed parts of the screen should leave the answer as much room as they can.

Shape and elevation:

- One radius, 3px (`rounded-box`), on controls and on people's words. Chips are 2px (`rounded-chip`). There are no pills and no fully rounded buttons.
- A control's border is 1.5px (`frame`); a hairline between regions is 1px.
- The SIM cut is 24px, 20px on a phone, and 16px on the small working card.
- Borders and background tone carry the structure. Only popovers and tooltips cast a shadow (`shadow-pop`).

Motion:

- One duration and one easing for every change of state: 120ms, `cubic-bezier(0.2, 0.7, 0.2, 1)` (`--speed`, `--ease`). Every `transition-*` class uses them; no component names a duration.
- Something arriving on the page takes 200ms (`--speed-enter`). The steps of a route arrive 50ms apart (`--stagger`).
- While the copilot works, the eyes of the mark glance out through the visor and back, once every 2.4 seconds.
- Something arrives once. The two views are both kept laid out, and the one not on show is made invisible and inert, because an element that returns from `display: none` plays its entrance again.
- A change of theme is one event: no control eases its own colours while it happens, and where the browser supports view transitions the whole page cross-fades in 200ms.
- A hand-off draft sits under the answer, outside the card with the cut corner: it is the agent's to act on, not something the copilot said. It carries a dashed "Not sent yet" tag until the agent opens it, and it never opens itself.
- A wrap-up draft sits under the summary on the same rail, and follows the hand-off draft: soft-square corners, a dashed "Not saved yet" tag, and nothing stored until the agent presses "Save wrap-up". The copilot filled the form in, so each part says whose words are in it: "Cue's draft" in `ink-3` until the agent changes that part, then "Changed by you" in `ink`. The boxes for notes and promises hold one item to a line and grow with their text, so the whole draft can be checked without scrolling inside a box. Once saved, the form is replaced by the record as it was stored, under the OK shape and the word "Saved", with any personal detail the agent typed shown as a redaction bar.
- The first button on the rail is the primary one ("Summarize"). "Wrap up" under it is an outline button, and "Save wrap-up" is the primary button of its own form, so no region has two cobalt fills at rest. In a replay the rail has no button, and "Play" is the one cobalt fill of the call.
- A replayed call starts stopped and nothing arrives until "Play" is pressed. Then each turn stays on screen for as long as it takes to read (0.9 seconds and 40ms a character, never under 1.5 or over 5.5 seconds), and the next one arrives once, like anything else. The newest turn is put in view at once, not scrolled to. Where the replay is in the call is a readout ("Turn 4 of 16"), not a bar that fills.
- Call assist says what changed in words, not by moving. A part that came up at the turn on show carries the notice square and "New at turn 4"; from the next turn it says "since turn 4". Every turn of a replayed call carries its number in mono, so the two can be matched. A new article and a new next step each arrive once as a card; a part that did not change is not redrawn.
- In a replay the call and the assist panel are both on screen at every width, because the point is to watch one follow the other: side by side from 1280px, and one above the other at half the height each below that, each scrolling by itself. On a phone the call header leaves out its note on redaction to make the room.
- The words on the working card are the stage the server says is running, sent as each one starts ("Searching the help articles", "Writing the answer"). They change when the work does, never on a timer. Before the first event, and against a server that sends none, the card says only "Working on it".
- One thing on a screen says "working": the signal bars. A placeholder that sits beside the working card holds still (`<Skeleton still>`); a placeholder that is the only sign of loading pulses.
- Nothing moves for decoration. The highlighter is not drawn in when an answer arrives: an agent sees hundreds of answers a day, and the facts have to be readable the moment the card is.
- `prefers-reduced-motion` stops every animation and transition, and the seeking bar holds still, half filled. The eyes of the mark hold still. A replay is the same in every other way: turns and cards appear without their entrance, and the call still moves on only while "Play" is on, which the agent pressed and can pause.

## States

Every control has four states beside rest. None of them changes the size of anything: borders keep their width, and heavier outlines are drawn inside the box.

| Control | Under the pointer | Pressed | Disabled |
| --- | --- | --- | --- |
| Primary button, send | `brand-strong` fill | `brand-press` fill | 50% opacity |
| Outline button, icon button, theme toggle | border turns to ink | `sunken` fill | 50% opacity |
| Quiet button | a `line-strong` border appears | `sunken` fill | 50% opacity |
| Ink-filled button (something that is on) | `ink-2` fill | `ink-3` fill | 50% opacity; the vote that was cast stays at full strength |
| View switcher, filter chip (not the current one) | `sunken` fill | `line` fill | |
| Calls list row | `sunken` fill | `brand-tint` fill, as it will have once selected | |
| Example card, source card | outline in ink, half a pixel heavier (`edge-ink`) | `sunken` fill | |
| Citation chip | `brand-tint` fill | `brand-press` fill | |
| Link | underline thickens to 2px | text turns to ink | |
| Question box, search box | border turns to ink | | sending is off while an answer is on its way; typing still works |
| A box or a choice in a draft (hand-off, wrap-up) | border turns to ink | | off while the draft is being sent or saved |

Focus from the keyboard is the same everywhere: a cobalt ring, 2px, set off by 2px (drawn inside a control that sits flush in a row). A text field is the one exception in form: its border turns cobalt and grows outward to 3px, as one line with no gap, because the box is the field.

To show a transient state in a still picture, write `data-force="hover"`, `"focus"` or `"pressed"` on the element. The `hover:`, `focus-visible:` and `active:` variants and the hand-written rules in `index.css` all answer to it. The component gallery does this with its `Force` wrapper.

## Reviewing: the gallery and the demo states

- `npm run dev:mock`, then open `/gallery.html`: every component in every state, drawn by the real component code from the mock fixtures. `?section=<id>` shows one section and `?theme=light|dark` pins the theme. `README.md` lists the section ids.
- In mock mode the app opens on a fixture state with `?demo=<name>`: `empty`, `cited`, `waiver`, `handoff`, `refusal`, `error`, `pending`, `calls`, `calls-summary`, `calls-assist` (a call in its replay, with the whole call on show).
- The gallery and these query hooks exist only in the dev server and in `npm run build:mock`. A normal build has neither.

## Icons

All icons are drawn for this product. There is no icon library.

- Grid: 24 by 24, built on the `Icon` base in `src/components/icons/Icon.tsx`.
- Stroke: 1.75 at 20 and 24px, 2 at 16px, 1.6 at 32px. Flat line ends, mitred joins, colour from the text.
- Corners: runs at 45 and 90 degrees. Where another set would round a corner, this one cuts it. Circles become eight-sided: the search lens, the faces, the moon, the retry loop.
- Fill: none, except the redaction bar in the privacy icon.
- Sizes: 16, 20, 24 or 32. Every icon must read at 16.
- Decorative by default (`aria-hidden`). Pass `title` only when the icon stands alone with no words beside it.
- Status stamps (`StatusStamp.tsx`) are the exception to the stroke rule: solid shapes on a 16 grid with the glyph knocked out, so that shape survives small and without colour. They are drawn at 16px beside text, 20px in a notice and 24px on the route.
- The mark (`CopilotMark.tsx`) is described under "The mark" below.
- The mood faces share one eight-sided face and one pair of eyes; only the mouth changes.

## The mark

The mark is a helmet seen from the front, with its visor open to one side. It was chosen from twelve candidates in three families; the sheets and the reasons are in [design/marks](../design/marks).

It has three readings, and each one is true of the product:

- **A face.** Two eyes behind a visor. They look out through the gap, so in the top bar the mark looks at its own name.
- **A SIM card.** Three round corners and one cut at 45 degrees: the cut every card the copilot writes has.
- **A letter C.**

Construction (`src/components/icons/CopilotMark.tsx`):

- Master drawing, 32 grid. A 26 by 26 square with a wall of 6, an outer radius of 6 and a cut with legs of 6: one measure. The visor is 14 high with an inner radius of 3.
- Across the visor the rhythm is even: 4 of space, an eye of 4, 4 of space, an eye of 4, 4 of space. The eyes are 8 high, with 3 above and 3 below. Their corners have a radius of 1, as firm as the 3px corners of the controls beside the mark.
- Small drawing, 16 grid, used at 20px and under. It is drawn again, not scaled down: the wall is thicker for its size, and every edge is on a whole pixel at 16. `public/favicon.svg` is this drawing.
- Sizes in use: 16 beside the copilot's name on a card, 32 in the top bar, 64 on the empty screen. At 16, 32 and 64 every edge of the drawing lands on a whole pixel.

Colour:

- The head is `mark` and the eyes are `ink`, in both themes. Two colours, and it holds in one.
- The eyes are not the highlighter. The highlighter has one job.

Rules:

- The mark is never shown without its eyes, and never without the cut. Without them it is only a blocky C, which other products also use.
- It is decorative (`aria-hidden`): the product's name is always written beside it.
- It moves in one case only: while the copilot is working, the eyes glance toward the gap and back (`working`).
- It was not checked against registered trademarks. This is a portfolio demo; a real product would need that search.
