import { Search, X } from "lucide-react";
import { memo, useDeferredValue, useId, useMemo, useState } from "react";

import type { CallListItem, Resolution } from "@/api/types";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";
import { countOf, humanize } from "@/lib/format";

import { callRowId } from "./callRowId";
import { ResolutionBadge } from "./ResolutionBadge";

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
    <li>
      <button
        type="button"
        id={callRowId(call.transcript_id)}
        aria-current={selected ? "true" : undefined}
        onClick={() => {
          onSelect(call.transcript_id);
        }}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors duration-100 focus-visible:-outline-offset-2",
          selected ? "bg-accent-soft" : "hover:bg-surface-muted",
        )}
      >
        <span
          className={cn(
            "w-[3.25rem] shrink-0 font-mono text-[0.8125rem] font-medium",
            selected ? "text-accent-soft-fg" : "text-fg",
          )}
        >
          {call.transcript_id}
        </span>
        <span className="min-w-0 flex-1 truncate text-[0.9375rem] text-fg-muted">
          {humanize(call.category)}
        </span>
        <ResolutionBadge resolution={call.resolution} />
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
      <div className="shrink-0 space-y-3 border-b px-4 pt-4 pb-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-base font-semibold text-fg">Calls</h2>
          <p role="status" className="text-xs text-fg-subtle">
            {items !== null &&
              (filtered
                ? `${visible.length} of ${countOf(items.length, "call")}`
                : countOf(items.length, "call"))}
          </p>
        </div>

        <div className="relative">
          <label htmlFor={searchId} className="sr-only">
            Search calls
          </label>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-subtle"
          />
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
            className="h-10 w-full rounded-lg border border-border-strong bg-surface pr-9 pl-9 text-[0.9375rem] text-fg transition-[border-color,box-shadow] duration-150 placeholder:text-fg-subtle focus-visible:border-accent focus-visible:shadow-[0_0_0_3px_var(--accent-soft)] focus-visible:outline-none"
          />
          {query !== "" && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => {
                setQuery("");
              }}
              className="absolute top-1/2 right-1.5 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-fg-subtle hover:bg-surface-muted hover:text-fg"
            >
              <X aria-hidden="true" className="size-4" />
            </button>
          )}
        </div>

        <div role="group" aria-label="Filter by how the call ended" className="flex flex-wrap gap-1.5">
          {FILTERS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              aria-pressed={filter === id}
              onClick={() => {
                setFilter(id);
              }}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[0.8125rem] font-medium transition-colors duration-150",
                filter === id
                  ? "border-accent bg-accent text-accent-fg"
                  : "bg-surface text-fg-muted hover:border-border-strong hover:text-fg",
              )}
            >
              {label}
              {items !== null && (
                <span
                  className={cn(
                    "text-xs tabular-nums",
                    filter === id ? "text-accent-fg/90" : "text-fg-subtle",
                  )}
                >
                  {counts[id]}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="scroll-area min-h-0 flex-1 p-2">
        {calls.status === "loading" && (
          <div className="space-y-2 p-1">
            {[0, 1, 2, 3, 4, 5, 6, 7].map((row) => (
              <Skeleton key={row} className="h-10 rounded-lg" />
            ))}
          </div>
        )}
        {calls.status === "error" && (
          <ErrorNotice className="m-2" message={calls.message} onRetry={onRetry} />
        )}
        {items !== null && visible.length > 0 && (
          <ul className="space-y-0.5">
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
          <div className="px-3 py-10 text-center">
            <p className="text-[0.9375rem] text-fg-muted">
              {items.length === 0 ? "There are no calls yet." : "No calls match."}
            </p>
            {filtered && (
              <Button
                variant="outline"
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
