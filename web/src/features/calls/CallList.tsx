import { memo, useDeferredValue, useId, useMemo, useState } from "react";

import type { CallListItem, Resolution } from "@/api/types";
import { CloseIcon, FlagIcon, SearchIcon } from "@/components/icons/glyphs";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";
import { DEMO_FLAGGED_ONLY } from "@/lib/devHooks";
import { countOf, humanize } from "@/lib/format";

import { callRowId } from "./callRowId";
import { CallStatus, CallStatusStamp } from "./CallStatus";
import { isChecked, rulesFired, ruleTitle } from "./findingRules";

export type CallFilter = Resolution | "all";

const FILTERS: readonly { id: CallFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "resolved", label: "Resolved" },
  { id: "escalated", label: "Escalated" },
  { id: "unresolved", label: "Unresolved" },
];

export interface CallRowProps {
  call: CallListItem;
  selected: boolean;
  onSelect: (transcriptId: string) => void;
}

/**
 * One call in the list: its id, its category, a flag if the rule check fired on
 * it, and how it ended.
 */
export const CallRow = memo(function CallRow({ call, selected, onSelect }: CallRowProps) {
  const flagged = rulesFired(call) > 0;
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
          "grid h-12 w-full grid-cols-[--spacing(14)_minmax(0,1fr)_auto] items-center gap-x-3 px-5 text-left transition-colors focus-visible:-outline-offset-2",
          // The cobalt tint with an ink outline, so the status colours inside stay legible.
          // A pressed row already takes the tint it will have once it is selected.
          selected ? "bg-brand-tint edge-inset" : "hover:bg-sunken active:bg-brand-tint",
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
        <span className="flex items-center gap-3">
          {flagged && (
            // The flag, not a status shape: the shapes say how a call ended.
            <span className="text-warn">
              <FlagIcon size={16} />
              <span className="sr-only">
                Flagged by the rule check: {(call.findings ?? []).map(ruleTitle).join("; ")}.
              </span>
            </span>
          )}
          <CallStatus resolution={call.resolution} />
        </span>
      </button>
    </li>
  );
});

export interface SearchFieldProps {
  value: string;
  onChange: (value: string) => void;
  /** What the field searches, for screen readers. */
  label: string;
  placeholder: string;
}

/** A search box with a button that clears it. */
export function SearchField({ value, onChange, label, placeholder }: SearchFieldProps) {
  const inputId = useId();
  return (
    <div className="field flex h-11 items-center gap-3 pr-1 pl-3 text-ink-3">
      <label htmlFor={inputId} className="sr-only">
        {label}
      </label>
      <SearchIcon />
      <input
        id={inputId}
        type="text"
        inputMode="search"
        autoComplete="off"
        spellCheck={false}
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="h-full min-w-0 flex-1 bg-transparent text-ink"
      />
      {value !== "" && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => {
            onChange("");
          }}
          className="grid size-8 shrink-0 place-items-center rounded-box text-ink-2 transition-colors hover:text-ink active:bg-sunken"
        >
          <CloseIcon size={16} />
        </button>
      )}
    </div>
  );
}

export interface ResolutionFilterProps {
  value: CallFilter;
  onChange: (value: CallFilter) => void;
  /** How many calls each filter would show. Null while the calls are loading. */
  counts: Record<CallFilter, number> | null;
}

/** Four filters on how a call ended, each with its count. The one that is on is filled with ink. */
export function ResolutionFilter({ value, onChange, counts }: ResolutionFilterProps) {
  return (
    <div
      role="group"
      aria-label="Filter by how the call ended"
      className="grid grid-cols-4 overflow-hidden rounded-box frame border-ink"
    >
      {FILTERS.map(({ id, label }, index) => {
        const on = value === id;
        return (
          <button
            key={id}
            type="button"
            aria-pressed={on}
            onClick={() => {
              onChange(id);
            }}
            className={cn(
              "grid justify-items-start gap-0.5 py-2 pr-1 pl-2 text-left transition-colors focus-visible:-outline-offset-2",
              index > 0 && "border-l-(length:--control-border) border-ink",
              on ? "bg-ink text-surface" : "bg-surface text-ink hover:bg-sunken active:bg-line",
            )}
          >
            <span className="flex min-h-6 items-center gap-1 font-mono font-bold">
              {id !== "all" && (
                // On ink the shape is a plain silhouette: the shape alone still says the status.
                <CallStatusStamp resolution={id} className={on ? "text-surface" : undefined} />
              )}
              {counts === null ? "" : counts[id]}
            </span>
            <span className={cn("text-label", on ? "text-surface" : "text-ink-2")}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

export interface FlaggedFilterProps {
  on: boolean;
  onChange: (on: boolean) => void;
  /** How many calls the rule check fired on. Null while the calls are loading. */
  count: number | null;
  /** False when no call in the list has been through the rule check. */
  checked: boolean;
}

/**
 * A switch that keeps only the calls the rule check fired on. It works with the
 * filter on how a call ended, not in place of it. When no call has been checked
 * there is nothing to filter on, and it says so, as a label about the data.
 */
export function FlaggedFilter({ on, onChange, count, checked }: FlaggedFilterProps) {
  if (count !== null && !checked) {
    return (
      <p className="rounded-box border border-dashed border-line-strong px-2 py-2 text-label font-semibold text-ink-2">
        No rule check has run on these calls, so none is flagged.
      </p>
    );
  }
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => {
        onChange(!on);
      }}
      className={cn(
        "flex w-full items-center gap-3 rounded-box frame border-ink px-2 py-2 text-left transition-colors",
        on ? "bg-ink text-surface" : "bg-surface text-ink hover:bg-sunken active:bg-line",
      )}
    >
      <span className="flex min-h-6 items-center gap-1 font-mono font-bold">
        {/* On ink the flag is a plain silhouette, as the status shapes are. */}
        <FlagIcon size={16} className={on ? undefined : "text-warn"} />
        {count ?? ""}
      </span>
      <span className={cn("text-label", on ? "text-surface" : "text-ink-2")}>
        Flagged by the rule check
      </span>
    </button>
  );
}

function matches(
  call: CallListItem,
  query: string,
  filter: CallFilter,
  flaggedOnly: boolean,
): boolean {
  if (filter !== "all" && call.resolution !== filter) {
    return false;
  }
  if (flaggedOnly && rulesFired(call) === 0) {
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

/**
 * Every call, with a search box, a filter on how the call ended, and a switch
 * that keeps only the calls the rule check flagged.
 */
export function CallList({ calls, selectedId, onSelect, onRetry }: CallListProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<CallFilter>("all");
  // In mock mode `?demo=calls-findings` opens with the switch already on.
  const [flaggedOnly, setFlaggedOnly] = useState(DEMO_FLAGGED_ONLY);
  // Typing stays responsive while the list catches up.
  const deferredQuery = useDeferredValue(query);

  const items = calls.status === "ready" ? calls.data : null;

  const flaggedCount = useMemo(
    () => (items === null ? null : items.filter((call) => rulesFired(call) > 0).length),
    [items],
  );
  const anyChecked = useMemo(() => (items ?? []).some(isChecked), [items]);
  // With no rule check to filter on, the switch is not shown and must not hide every call.
  const onlyFlagged = flaggedOnly && anyChecked;

  const counts = useMemo(() => {
    if (items === null) {
      return null;
    }
    const totals: Record<CallFilter, number> = { all: 0, resolved: 0, escalated: 0, unresolved: 0 };
    for (const call of items) {
      totals.all += 1;
      totals[call.resolution] += 1;
    }
    return totals;
  }, [items]);

  const visible = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase();
    return (items ?? []).filter((call) => matches(call, needle, filter, onlyFlagged));
  }, [items, deferredQuery, filter, onlyFlagged]);

  const filtered = query.trim() !== "" || filter !== "all" || onlyFlagged;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 px-5 pt-6 pb-4">
        <div className="flex items-baseline gap-3">
          <h2 className="display-view text-ink">Calls</h2>
          <p role="status" className="font-mono text-meta text-ink-2">
            {items !== null &&
              (filtered
                ? `${visible.length} of ${countOf(items.length, "call")}`
                : countOf(items.length, "call"))}
          </p>
        </div>
        <div className="mt-4">
          <SearchField
            value={query}
            onChange={setQuery}
            label="Search calls"
            placeholder="Search by id or category"
          />
        </div>
        <div className="mt-3">
          <ResolutionFilter value={filter} onChange={setFilter} counts={counts} />
        </div>
        <div className="mt-2">
          <FlaggedFilter
            on={onlyFlagged}
            onChange={setFlaggedOnly}
            count={flaggedCount}
            checked={anyChecked}
          />
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
          <div className="border-t border-line px-5 pt-3">
            <ErrorNotice message={calls.message} onRetry={onRetry} />
          </div>
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
                  setFlaggedOnly(false);
                }}
              >
                Clear search and filters
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
