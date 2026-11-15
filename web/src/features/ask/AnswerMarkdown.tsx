import { createContext, useContext, useMemo, type ComponentProps } from "react";
import Markdown, { type Components, type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Citation } from "@/api/types";
import { PlaceholderChip } from "@/components/shared/PlaceholderText";
import { cn } from "@/lib/cn";
import {
  CITATION_HREF_PREFIX,
  PLACEHOLDER_CLASS,
  remarkAnnotations,
} from "@/lib/remarkAnnotations";

interface CitationContextValue {
  citations: readonly Citation[];
  activeCitation: number | null;
  onCite: (number: number) => void;
}

/**
 * What the citation chips need. It travels by context so the renderers below
 * can stay the same functions from one render to the next.
 */
const CitationContext = createContext<CitationContextValue | null>(null);

function CitationChip({ citation }: { citation: Citation }) {
  const context = useContext(CitationContext);
  const active = context?.activeCitation === citation.number;
  return (
    <button
      type="button"
      aria-label={`Show source ${citation.number}: ${citation.title}`}
      aria-pressed={active}
      onClick={() => context?.onCite(citation.number)}
      className={cn(
        "mx-px inline-flex h-[1.9em] min-w-[1.9em] -translate-y-[0.12em] items-center justify-center rounded-full px-[0.5em]",
        "align-baseline text-[0.66em] leading-none font-semibold tabular-nums transition-colors duration-150",
        active
          ? "bg-accent text-accent-fg"
          : "bg-accent-soft text-accent-soft-fg hover:bg-accent hover:text-accent-fg",
      )}
    >
      {citation.number}
    </button>
  );
}

function AnswerLink({ href, children }: ComponentProps<"a">) {
  const context = useContext(CitationContext);
  if (href?.startsWith(CITATION_HREF_PREFIX)) {
    const number = Number(href.slice(CITATION_HREF_PREFIX.length));
    const citation = context?.citations.find((candidate) => candidate.number === number);
    if (citation) {
      return <CitationChip citation={citation} />;
    }
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-accent underline decoration-accent/40 underline-offset-[3px] hover:decoration-accent"
    >
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

function AnswerCode({ className, children }: ComponentProps<"code">) {
  if (className === PLACEHOLDER_CLASS && typeof children === "string") {
    return <PlaceholderChip name={children} />;
  }
  return <code className={className}>{children}</code>;
}

function AnswerTable({ children }: ComponentProps<"table">) {
  return (
    <div className="table-scroll">
      <table>{children}</table>
    </div>
  );
}

const COMPONENTS: Components = {
  a: AnswerLink,
  code: AnswerCode,
  table: AnswerTable,
};

export interface AnswerMarkdownProps {
  /** The answer as Markdown. Raw HTML in it is shown as text, never run. */
  markdown: string;
  citations: readonly Citation[];
  /** The citation whose source is highlighted, if any. */
  activeCitation: number | null;
  onCite: (number: number) => void;
}

/**
 * An answer, rendered from Markdown. Citation markers such as [1] become chips
 * that point at their source, and placeholders become chips too.
 */
export function AnswerMarkdown({
  markdown,
  citations,
  activeCitation,
  onCite,
}: AnswerMarkdownProps) {
  // Parsing Markdown is the costly part, so it is redone only when the answer changes.
  const rendered = useMemo(() => {
    const remarkPlugins: NonNullable<Options["remarkPlugins"]> = [
      remarkGfm,
      [remarkAnnotations, { citationNumbers: citations.map((citation) => citation.number) }],
    ];
    return (
      <Markdown remarkPlugins={remarkPlugins} components={COMPONENTS}>
        {markdown}
      </Markdown>
    );
  }, [markdown, citations]);
  const context = useMemo<CitationContextValue>(
    () => ({ citations, activeCitation, onCite }),
    [citations, activeCitation, onCite],
  );
  return (
    <CitationContext value={context}>
      <div className="answer">{rendered}</div>
    </CitationContext>
  );
}
