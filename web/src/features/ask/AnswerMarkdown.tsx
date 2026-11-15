import { createContext, useContext, useMemo, type ComponentProps } from "react";
import Markdown, { type Components, type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Citation } from "@/api/types";
import { RedactionBar } from "@/components/shared/PlaceholderText";
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
      data-active={active}
      onClick={() => context?.onCite(citation.number)}
      className="cite mx-0.5"
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
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

function AnswerCode({ className, children }: ComponentProps<"code">) {
  if (className === PLACEHOLDER_CLASS && typeof children === "string") {
    return <RedactionBar name={children} />;
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

/**
 * A numbered list. Its numerals are drawn by a CSS counter, so that they can be
 * set in mono. A list that carries on after an interruption arrives with a
 * `start`, and the counter has to be told, or it would begin again at 1.
 */
function AnswerOrderedList({ start, className, children }: ComponentProps<"ol">) {
  const style = start === undefined ? undefined : { counterReset: `step ${start - 1}` };
  return (
    <ol start={start} className={className} style={style}>
      {children}
    </ol>
  );
}

const COMPONENTS: Components = {
  a: AnswerLink,
  code: AnswerCode,
  ol: AnswerOrderedList,
  table: AnswerTable,
};

export interface AnswerMarkdownProps {
  /** The answer as Markdown. Raw HTML in it is shown as text, never run. */
  markdown: string;
  citations: readonly Citation[];
  /** Ticket references the answer may quote. They are highlighted as facts to read aloud. */
  references: readonly string[];
  /** The citation whose source is highlighted, if any. */
  activeCitation: number | null;
  onCite: (number: number) => void;
}

/**
 * An answer, set like a call script. Bold text is run over with the
 * highlighter, citation markers such as [1] become chips that point at their
 * source, and placeholders become redaction bars.
 */
export function AnswerMarkdown({
  markdown,
  citations,
  references,
  activeCitation,
  onCite,
}: AnswerMarkdownProps) {
  // Parsing Markdown is the costly part, so it is redone only when the answer changes.
  const rendered = useMemo(() => {
    const remarkPlugins: NonNullable<Options["remarkPlugins"]> = [
      remarkGfm,
      [
        remarkAnnotations,
        { citationNumbers: citations.map((citation) => citation.number), references },
      ],
    ];
    return (
      <Markdown remarkPlugins={remarkPlugins} components={COMPONENTS}>
        {markdown}
      </Markdown>
    );
  }, [markdown, citations, references]);
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
