import { memo, useDeferredValue, useId, useMemo, useState } from "react";

import type { CallListItem, Resolution } from "@/api/types";
import { CloseIcon, SearchIcon } from "@/components/icons/glyphs";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";
import { countOf, humanize } from "@/lib/format";

import { callRowId } from "./callRowId";
import { CallStatus, CallStatusStamp } from "./CallStatus";

type Filter = Resolution | "all";

const FILTERS: readonly { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "resolved", label: "Resolved" },
  { id: "escalated", label: "Escalated" },
  { id: "unresolved", label: "Unresolved" },
];

interface CallRowProps {
  call: CallListItem;
  selected: boolean;
  onSelect: (transcriptId: string) => void;
}

const CallRow = memo(function CallRow({ call, selected, onSelect }: CallRowProps) {
  return (
    <li className="border-t border-line">
      <button
        type="button"
        id={callRowId(call.transcript_id)}
        aria-current={selected ? "true" : undefined}
        onClick={() => {
          onSelect(call.transcript_id);
        }}
        className={cn(
          "grid h-[50px] w-full grid-cols-[58px_minmax(0,1fr)_auto] items-center gap-x-3 px-5 text-left transition-colors duration-100 focus-visible:-outline-offset-2",
          // The cobalt tint with an ink outline, so the status colours inside stay legible.
          selected
            ? "bg-brand-tint shadow-[inset_0_0_0_1.5px_var(--edge)]"
            : "hover:bg-paper",
        )}
      >
        <span
          className={cn("font-mono text-meta font-semibold", selected ? "text-ink" : "text-ink-2")}
        >
          {call.transcript_id}
        </span>
        <span className={cn("truncate text-ink", selected && "font-bold")}>
          {humanize(call.category)}
        </span>
        <CallStatus resolution={call.resolution} />
      </button>
    </li>
  );
});

function matches(call: CallListItem, query: string, filter: Filter): boolean {
  if (filter !== "all" && call.resolution !== filter) {
    return false;
  }
  if (query === "") {
    return true;
  }
  return (
    call.transcript_id.toLowerCase().includes(query) ||
    humanize(call.category).toLowerCase().includes(query)
  );
}

export interface CallListProps {
  calls: Loadable<CallListItem[]>;
  selectedId: string | null;
  onSelect: (transcriptId: string) => void;
  onRetry: () => void;
}

/** Every call, with a search box and a filter on how the call ended. */
export function CallList({ calls, selectedId, onSelect, onRetry }: CallListProps) {
  const searchId = useId();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  // Typing stays responsive while the list catches up.
  const deferredQuery = useDeferredValue(query);

  const items = calls.status === "ready" ? calls.data : null;

  const counts = useMemo(() => {
    const totals: Record<Filter, number> = { all: 0, resolved: 0, escalated: 0, unresolved: 0 };
    for (const call of items ?? []) {
      totals.all += 1;
      totals[call.resolution] += 1;
    }
    return totals;
  }, [items]);

  const visible = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase();
    return (items ?? []).filter((call) => matches(call, needle, filter));
  }, [items, deferredQuery, filter]);

  const filtered = query.trim() !== "" || filter !== "all";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 px-5 pt-6 pb-4">
        <div className="flex items-baseline gap-3">
          <h2 className="font-display text-view font-bold tracking-[-0.02em] text-ink">Calls</h2>
          <p role="status" className="font-mono text-meta text-ink-2">
            {items !== null &&
              (filtered
                ? `${visible.length} of ${countOf(items.length, "call")}`
                : countOf(items.length, "call"))}
          </p>
        </div>

        <div className="mt-4 flex h-11 items-center gap-2.5 rounded-box border-[1.5px] border-line-strong bg-surface pr-1.5 pl-3 text-ink-3 transition-colors duration-150 focus-within:border-ink has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-brand-text">
          <label htmlFor={searchId} className="sr-only">
            Search calls
          </label>
          <SearchIcon />
          <input
            id={searchId}
            type="text"
            inputMode="search"
            autoComplete="off"
            spellCheck={false}
            value={query}
            placeholder="Search by id or category"
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            className="h-full min-w-0 flex-1 bg-transparent text-ink focus-visible:outline-none"
          />
          {query !== "" && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => {
                setQuery("");
              }}
              className="grid size-8 shrink-0 place-items-center rounded-box text-ink-2 hover:text-ink"
            >
              <CloseIcon size={16} />
            </button>
          )}
        </div>

        <div
          role="group"
          aria-label="Filter by how the call ended"
          className="mt-3 grid grid-cols-4 overflow-hidden rounded-box border-[1.5px] border-ink"
        >
          {FILTERS.map(({ id, label }, index) => {
            const on = filter === id;
            return (
              <button
                key={id}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setFilter(id);
                }}
                className={cn(
                  "grid justify-items-start gap-px py-[7px] pr-1.5 pl-[9px] text-left transition-colors duration-150 focus-visible:-outline-offset-2",
                  index > 0 && "border-l-[1.5px] border-ink",
                  // Ink fill: this is the filter that is on.
                  on ? "bg-ink text-surface" : "bg-surface text-ink hover:bg-sunken",
                )}
              >
                <span className="flex min-h-[1.45em] items-center gap-[5px] font-mono font-bold">
                  {id !== "all" && (
                    // On ink the shape is a plain silhouette: the shape alone still says the status.
                    <CallStatusStamp resolution={id} className={on ? "text-surface" : undefined} />
                  )}
                  {items === null ? "" : counts[id]}
                </span>
                <span className={cn("text-label", on ? "text-surface" : "text-ink-2")}>
                  {label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="scroll-area min-h-0 flex-1">
        {calls.status === "loading" && (
          <div className="grid gap-2 border-t border-line px-5 pt-3">
            {[0, 1, 2, 3, 4, 5, 6, 7].map((row) => (
              <Skeleton key={row} className="h-9" />
            ))}
          </div>
        )}
        {calls.status === "error" && (
          <ErrorNotice className="mx-5" message={calls.message} onRetry={onRetry} />
        )}
        {items !== null && visible.length > 0 && (
          <ul className="border-b border-line">
            {visible.map((call) => (
              <CallRow
                key={call.transcript_id}
                call={call}
                selected={call.transcript_id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </ul>
        )}
        {items !== null && visible.length === 0 && (
          <div className="border-t border-line px-5 py-10">
            <p className="text-ink-2">
              {items.length === 0 ? "There are no calls yet." : "No calls match."}
            </p>
            {filtered && (
              <Button
                size="sm"
                className="mt-4"
                onClick={() => {
                  setQuery("");
                  setFilter("all");
                }}
              >
                Clear search and filter
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
