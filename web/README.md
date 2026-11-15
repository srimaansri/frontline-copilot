# Frontline Copilot: web interface

The browser front end for Frontline Copilot. It is a single page with two views:

- **Ask**: a conversation with the copilot. Each answer shows its sources and a timeline of what the copilot did to produce it.
- **Calls**: the redacted call transcripts, with a summary on request.

It talks to the Python API under `/api`. The API contract is typed in `src/api/types.ts`.

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

## Mock mode

Mock mode needs no API. The client answers from the fixtures in `src/api/mock.ts` after a short delay.

```bash
# Git Bash, macOS, Linux
VITE_USE_MOCK=1 npm run dev

# PowerShell
$env:VITE_USE_MOCK = "1"; npm run dev
```

The top bar shows a "Mock mode" tag while it is on. The fixtures cover:

- the four example questions on the Ask view;
- a refusal: ask it to "ignore your instructions";
- a question with no matching article: ask anything else;
- redaction: put a phone number or an email address in a question to see the "As processed" line;
- a failed request: send exactly `/error` to see the error message and its retry button;
- the Calls list (200 rows), of which `T0001` and `T0002` have a transcript and a summary. Any other call shows the error state.

A normal build does not include the fixtures.

## Build

```bash
npm run build
```

The output goes to `web/dist`. The Python server serves that folder at `/`.

## Checks

| Command             | What it does                                    |
| ------------------- | ----------------------------------------------- |
| `npm run typecheck` | TypeScript, strict, no output                   |
| `npm run lint`      | ESLint with type-aware rules, zero warnings     |
| `npm run build`     | Type-check, then build to `dist`                |
| `npm run preview`   | Serve the built `dist` locally                  |

## Layout

```
src/
  api/          types.ts (the contract), client.ts (the one API client), mock.ts (fixtures)
  components/
    ui/         Button, Badge, Card, Popover, Tooltip and other primitives
    shell/      Top bar, "What's running" popover, footer
    shared/     Pieces both views use: brand mark, placeholder chips, error notice
  features/
    ask/        Conversation, question box, answer card, sources, step timeline
    calls/      Call list, transcript, summary
  hooks/        useLoad (fetching), useTheme, useMediaQuery
  lib/          Small pure helpers, and the Markdown plugin for citations and placeholders
  index.css     Colour tokens for the light and dark themes, and the answer typography
```

## Notes

- Fonts (Inter and JetBrains Mono) are bundled from npm. Nothing is loaded from a CDN, and there is no analytics.
- The theme follows the system setting on the first visit. A choice made with the toggle is kept in `localStorage`.
- Answers are rendered from Markdown with `react-markdown`. Raw HTML in an answer is shown as text and never run.
- Dependencies are pinned to exact versions. Keep `package-lock.json` committed.
