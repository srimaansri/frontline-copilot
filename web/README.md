# Cue: the Frontline Copilot web interface

The browser front end for Frontline Copilot. In the interface the copilot has a name, Cue. It is a single page with two views:

- **Ask**: a conversation with the copilot. Each answer shows its sources and the route of steps the copilot took to produce it.
- **Calls**: the redacted call transcripts, with a summary on request.

It talks to the Python API under `/api`. The API contract is typed in `src/api/types.ts`. The look is described in [`DESIGN.md`](DESIGN.md).

## Requirements

Node 20.19 or newer (22.12 or newer on the 22 line), and npm.

## Run it

```bash
cd web
npm install
npm run dev
```

The dev server proxies `/api` to `http://127.0.0.1:8000`, so start the API first:

```bash
uvicorn api.main:app --port 8000
```

## The demo build (mock mode)

The demo build needs no API. It replays recordings of the live copilot: `src/api/recorded.json` holds what the real API returned for a fixed list of questions and calls, and `src/api/mock.ts` looks a question up in it and returns the recording unchanged. No answer is written by hand.

```bash
npm run dev:mock
```

That is `vite --mode mock`, which loads `.env.mock`. No environment variable has to be set. The top bar shows a "Recorded answers" tag on a wide window, the line under the question box says so at any width, and the "What's running" popover gives the date and commit of the recording.

To make a new recording, from the repository root, with the workspace signed in and the work committed:

```bash
python -m eval.record_demo
```

It asks the real application every question the demo offers (the interface's examples, the evaluation set and a few everyday messages), runs hand-offs as dry runs so no ticket is written, and stamps the file with the date and the commit. Try `--limit 3` first; it writes nothing.

What the demo shows:

- a recorded answer for any question in the recording, matched by its letters and digits, so "Hello!" finds "hello";
- for any other question, a note that there is no recording, with some questions that have one. It is marked as a note from the page and is not the copilot's "no article matched" answer, because the live copilot would search for it;
- a wait as long as the live answer took, up to eight seconds, and the recorded time under the answer;
- no rating buttons, because a recording has no trace to attach a rating to;
- hand-offs that were dry runs: the reference in a recorded hand-off was made up for that answer and no ticket was written;
- a failed request: send exactly `/error` to see the error message and its retry button;
- a request that never answers: send exactly `/pending`;
- the Calls list (200 rows). The calls named in `eval/record_demo.py` have a transcript and a summary. Any other call shows the error state, which names the calls that are recorded.

A normal build does not include the recording.

## Reviewing the look

Two tools make a review repeatable. Both exist only in the dev server and in the mock build. A normal build has neither, and the app never links to the gallery.

### The component gallery

```bash
npm run dev:mock
```

Then open `http://localhost:5173/gallery.html`. It draws every component in every state with the real component code, from the mock fixtures.

- `?theme=light` or `?theme=dark` pins the theme, whatever is stored or set in the system, and writes nothing to storage.
- `?section=<id>` shows one section. For example `http://localhost:5173/gallery.html?theme=dark&section=route`.

The section ids: `tokens`, `buttons`, `view-switcher`, `theme-toggle`, `tags`, `status`, `citation`, `redaction`, `signal-bars`, `composer`, `question`, `answer`, `answer-footer`, `sources`, `route`, `examples`, `running`, `call-rows`, `filters`, `search`, `transcript`, `summary`, `calls-states`, `icons`.

A hover, a focus ring or a press is shown in a still picture by writing `data-force="hover"`, `"focus"` or `"pressed"` on the element. Every such style in the app answers to that attribute as well as to the real state.

### Demo states of the app

In the demo build the app opens directly on a recorded state, with no delay, so that two screenshots of the same URL are the same:

| URL | Opens on |
| --- | --- |
| `http://localhost:5173/?demo=empty` | The Ask view before any question |
| `http://localhost:5173/?demo=cited` | A cited answer, with its sources and steps |
| `http://localhost:5173/?demo=waiver` | The waiver-steps answer, as the live model wrote it |
| `http://localhost:5173/?demo=handoff` | A hand-off with personal details removed |
| `http://localhost:5173/?demo=refusal` | A refusal |
| `http://localhost:5173/?demo=error` | A failed question, with its retry button |
| `http://localhost:5173/?demo=pending` | A question still waiting for its answer |
| `http://localhost:5173/?demo=calls` | The Calls view with a call open |
| `http://localhost:5173/?demo=calls-summary` | The same, with its summary |

Add `&theme=light` or `&theme=dark` to pin the theme.

## Build

```bash
npm run build
```

The output goes to `web/dist`. The Python server serves that folder at `/`.

`npm run build:mock` builds the mock version instead, with the gallery at `/gallery.html`. It writes to the same `dist` folder, so run `npm run build` again before the Python server is to serve the real app.

## Checks

| Command                  | What it does                                                        |
| ------------------------ | ------------------------------------------------------------------- |
| `npm run typecheck`      | TypeScript, strict, no output                                       |
| `npm run lint`           | `lint:code`, then `check:contrast`                                  |
| `npm run lint:code`      | ESLint with type-aware rules, zero warnings                         |
| `npm run check:contrast` | Measures every colour pair in use against WCAG 2.1 AA, both themes  |
| `npm run build`          | Type-check, then build to `dist`                                    |
| `npm run build:mock`     | The same in mock mode, with the gallery                             |
| `npm run preview`        | Serve the built `dist` locally                                      |

The contrast check reads the colour tokens from `src/index.css`. The pairs it measures are listed, with where each is used, in `scripts/contrast-pairs.mjs`. Add a pair there when a component puts one token on another for the first time.

## Layout

```
gallery.html    The component gallery's page (dev server and mock build only)
scripts/        check-contrast.mjs and the table of colour pairs it measures
src/
  api/          types.ts (the contract), client.ts (the one API client), mock.ts (fixtures)
  components/
    icons/      The icon set, the status stamps and the brand mark, all drawn for this product
    ui/         Button, Popover, Tooltip and other primitives
    shell/      Top bar, "What's running" popover, footer
    shared/     Pieces both views use: the SIM card, signal bars, redaction bars, error notice
  features/
    ask/        Conversation, question box, answer card, sources, the route of steps
    calls/      Call list, transcript, summary
  gallery/      The gallery: its sections, its fixtures, and the wrapper that pins a state
  hooks/        useLoad (fetching), useTheme, useMediaQuery, useCycle
  lib/          Small pure helpers, the Markdown plugin, and devHooks.ts (the query hooks above)
  fonts.css     The three typefaces, latin subset only
  index.css     Colour, type, spacing and motion tokens for both themes, and the motif styles
```

## Notes

- Fonts (Schibsted Grotesk, Atkinson Hyperlegible Next and Atkinson Hyperlegible Mono) are bundled from npm. Nothing is loaded from a CDN, and there is no analytics.
- The theme follows the system setting on the first visit. A choice made with the toggle is kept in `localStorage`.
- Answers are rendered from Markdown with `react-markdown`. Raw HTML in an answer is shown as text and never run.
- Dependencies are pinned to exact versions. Keep `package-lock.json` committed.
