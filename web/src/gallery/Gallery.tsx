import type { ReactElement } from "react";

import { CopilotMark } from "@/components/icons/CopilotMark";
import { ThemeToggle } from "@/components/shell/TopBar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/cn";
import { sectionFromUrl } from "@/lib/devHooks";

import {
  AnswerFooterSection,
  AnswerSection,
  ComposerSection,
  ExamplesSection,
  QuestionSection,
  RouteSection,
  RunningSection,
  SourcesSection,
} from "./sections/ask";
import {
  AssistSection,
  CallRowsSection,
  CallsStatesSection,
  FiltersSection,
  ReplaySection,
  SearchSection,
  SummarySection,
  TranscriptSection,
  WrapUpSection,
} from "./sections/calls";
import {
  ButtonsSection,
  CitationSection,
  RedactionSection,
  SignalBarsSection,
  StatusSection,
  TagsSection,
  ThemeToggleSection,
  ViewSwitcherSection,
} from "./sections/controls";
import { IconsSection, TokensSection } from "./sections/foundations";

/** Every section, in the order it is shown. The id is what `?section=` takes. */
const SECTIONS: readonly { id: string; title: string; render: () => ReactElement }[] = [
  { id: "tokens", title: "Tokens", render: TokensSection },
  { id: "buttons", title: "Buttons", render: ButtonsSection },
  { id: "view-switcher", title: "View switcher", render: ViewSwitcherSection },
  { id: "theme-toggle", title: "Theme toggle", render: ThemeToggleSection },
  { id: "tags", title: "Tags and badges", render: TagsSection },
  { id: "status", title: "Status stamps", render: StatusSection },
  { id: "citation", title: "Citation chip", render: CitationSection },
  { id: "redaction", title: "Redaction and highlighter", render: RedactionSection },
  { id: "signal-bars", title: "Signal bars", render: SignalBarsSection },
  { id: "composer", title: "Composer", render: ComposerSection },
  { id: "question", title: "Question bubble", render: QuestionSection },
  { id: "answer", title: "Answer card", render: AnswerSection },
  { id: "answer-footer", title: "Answer footer", render: AnswerFooterSection },
  { id: "sources", title: "Source card", render: SourcesSection },
  { id: "route", title: "Steps route", render: RouteSection },
  { id: "examples", title: "Example cards", render: ExamplesSection },
  { id: "running", title: "What's running", render: RunningSection },
  { id: "call-rows", title: "Calls list row", render: CallRowsSection },
  { id: "filters", title: "Filter chips", render: FiltersSection },
  { id: "search", title: "Search field", render: SearchSection },
  { id: "transcript", title: "Transcript", render: TranscriptSection },
  { id: "summary", title: "Summary card", render: SummarySection },
  { id: "wrap-up", title: "Wrap-up", render: WrapUpSection },
  { id: "replay", title: "Replay", render: ReplaySection },
  { id: "assist", title: "Call assist", render: AssistSection },
  { id: "calls-states", title: "Calls states", render: CallsStatesSection },
  { id: "icons", title: "Icons", render: IconsSection },
];

/** A link that keeps the theme named in the URL, so a pinned theme survives a click. */
function hrefFor(section: string | null): string {
  const query = new URLSearchParams(window.location.search);
  if (section === null) {
    query.delete("section");
  } else {
    query.set("section", section);
  }
  const text = query.toString();
  return text === "" ? window.location.pathname : `${window.location.pathname}?${text}`;
}

/**
 * The component gallery: every component in every state, drawn by the real
 * component code from the mock fixtures. `?section=<id>` shows one section,
 * `?theme=light|dark` pins the theme.
 */
export function Gallery() {
  const { theme, toggleTheme } = useTheme();
  const only = sectionFromUrl();
  const shown = SECTIONS.filter((section) => only === null || section.id === only);

  return (
    <TooltipProvider>
      <div className="min-h-full bg-paper text-ink">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
            <CopilotMark size={32} />
            <h1 className="display-title">Component gallery</h1>
            <p className="text-meta text-ink-2">Cue. Recordings of the live copilot, no server.</p>
            <div className="ml-auto">
              <ThemeToggle theme={theme} onToggle={toggleTheme} />
            </div>
          </div>
          <nav aria-label="Sections" className="mx-auto max-w-7xl px-6 pb-3">
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-meta">
              <li>
                <a href={hrefFor(null)} className={cn("link", only === null && "text-ink")}>
                  All
                </a>
              </li>
              {SECTIONS.map(({ id, title }) => (
                <li key={id}>
                  <a href={hrefFor(id)} className={cn("link", only === id && "text-ink")}>
                    {title}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </header>

        <main className="mx-auto grid max-w-7xl gap-16 px-6 pt-10 pb-16">
          {shown.length === 0 && (
            <p className="text-read">
              There is no section called <span className="font-mono">{only}</span>.
            </p>
          )}
          {shown.map(({ id, render: Section }) => (
            <Section key={id} />
          ))}
        </main>
      </div>
    </TooltipProvider>
  );
}
