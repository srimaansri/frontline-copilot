import { useEffect, useRef } from "react";

import type { Citation } from "@/api/types";
import { ExternalLinkIcon } from "@/components/icons/glyphs";
import { cn } from "@/lib/cn";
import { hostOf } from "@/lib/format";

/**
 * The source a citation chip pointed at. `tick` starts at 1 and goes up on
 * every click, and each new value moves focus to the source. A `tick` of 0
 * highlights the source without moving focus; the component gallery uses it.
 */
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
    if (highlightTick !== null && highlightTick > 0) {
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
          "grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 rounded-box border bg-surface px-4 py-3 text-ink transition-[border-color,background-color,box-shadow]",
          highlighted
            ? "edge-ink active:bg-sunken"
            : "border-line-strong hover:edge-ink active:bg-sunken",
        )}
      >
        {/* The same square as the chip in the answer, so the eye can match them. */}
        <span aria-hidden="true" className="cite" data-active={highlighted}>
          {citation.number}
        </span>
        <span className="min-w-0">
          <span className="sr-only">Source {citation.number}: </span>
          <span className="block font-bold">{citation.title}</span>
          <span className="block truncate font-mono text-meta text-ink-2">
            {hostOf(citation.url)}
          </span>
        </span>
        <ExternalLinkIcon className="text-brand-text" />
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
    return <p className="text-ink-2">This answer cites no sources.</p>;
  }
  return (
    <ul className="grid gap-2">
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
