import { ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";

import type { Citation } from "@/api/types";
import { cn } from "@/lib/cn";
import { hostOf } from "@/lib/format";

/** The source a citation chip pointed at. `tick` changes on every click. */
export interface SourceHighlight {
  number: number;
  tick: number;
}

interface SourceCardProps {
  citation: Citation;
  /** Set when a citation chip for this source was clicked; changes on each click. */
  highlightTick: number | null;
}

function SourceCard({ citation, highlightTick }: SourceCardProps) {
  const link = useRef<HTMLAnchorElement>(null);

  // Following a citation moves focus to its source, and scrolls it into view.
  useEffect(() => {
    if (highlightTick !== null) {
      link.current?.focus();
    }
  }, [highlightTick]);

  const highlighted = highlightTick !== null;
  return (
    <li>
      <a
        ref={link}
        href={citation.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-current={highlighted ? "true" : undefined}
        className={cn(
          "group flex items-start gap-3 rounded-lg border p-3 transition-colors duration-200",
          highlighted
            ? "border-accent bg-accent-soft"
            : "bg-surface hover:border-border-strong hover:bg-surface-muted",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "mt-px flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums transition-colors duration-200",
            highlighted ? "bg-accent text-accent-fg" : "bg-accent-soft text-accent-soft-fg",
          )}
        >
          {citation.number}
        </span>
        <span className="min-w-0 flex-1">
          <span className="sr-only">Source {citation.number}: </span>
          <span className="block text-[0.9375rem] leading-snug font-medium text-fg">
            {citation.title}
          </span>
          <span className="mt-0.5 block truncate text-[0.8125rem] text-fg-subtle">
            {hostOf(citation.url)}
          </span>
        </span>
        <ExternalLink
          aria-hidden="true"
          className="mt-1 size-4 shrink-0 text-fg-subtle transition-colors group-hover:text-fg"
        />
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    </li>
  );
}

export interface SourceListProps {
  citations: readonly Citation[];
  highlight: SourceHighlight | null;
}

/** The sources an answer cites, as cards that open the article in a new tab. */
export function SourceList({ citations, highlight }: SourceListProps) {
  if (citations.length === 0) {
    return <p className="text-sm leading-relaxed text-fg-subtle">This answer cites no sources.</p>;
  }
  return (
    <ul className="space-y-2">
      {citations.map((citation) => (
        <SourceCard
          key={citation.number}
          citation={citation}
          highlightTick={highlight?.number === citation.number ? highlight.tick : null}
        />
      ))}
    </ul>
  );
}
