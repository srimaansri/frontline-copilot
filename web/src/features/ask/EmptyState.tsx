import { ArrowUpRight } from "lucide-react";

import type { ExampleQuestion, Meta } from "@/api/types";
import { BrandMark } from "@/components/shared/BrandMark";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { ToolIcon } from "@/components/shared/ToolIcon";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";

interface ExampleCardProps {
  example: ExampleQuestion;
  onPick: (question: string) => void;
}

function ExampleCard({ example, onPick }: ExampleCardProps) {
  return (
    <li className="flex">
      <button
        type="button"
        onClick={() => {
          onPick(example.question);
        }}
        className="group flex w-full items-start gap-3.5 rounded-xl border bg-surface p-4 text-left transition-colors duration-150 hover:border-accent/60 hover:bg-accent-soft/40"
      >
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-soft-fg"
        >
          <ToolIcon name={example.tool} className="size-[1.125rem]" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-base leading-snug font-medium text-fg">
            {example.question}
          </span>
          <span className="mt-1.5 block text-sm leading-snug text-fg-subtle">{example.hint}</span>
        </span>
        <ArrowUpRight
          aria-hidden="true"
          className="mt-0.5 size-4 shrink-0 text-fg-subtle opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
        />
      </button>
    </li>
  );
}

export interface EmptyStateProps {
  meta: Loadable<Meta>;
  onRetryMeta: () => void;
  onPick: (question: string) => void;
}

/** What the Ask view shows before the first question: a welcome and four examples. */
export function EmptyState({ meta, onRetryMeta, onPick }: EmptyStateProps) {
  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
      <BrandMark className="size-12 rounded-xl" />
      <h2 className="mt-6 text-[1.75rem] leading-tight font-semibold tracking-tight text-fg sm:text-[2rem]">
        What does the customer need?
      </h2>
      <p className="mt-3 max-w-xl text-lg leading-relaxed text-fg-muted">
        Ask a support question, look up a plan, or summarize a call. Every answer shows its sources
        and the steps behind it.
      </p>

      <div className="mt-9">
        <h3 className="text-sm font-semibold text-fg-subtle">Try an example</h3>
        {meta.status === "ready" && (
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {meta.data.examples.map((example) => (
              <ExampleCard key={example.question} example={example} onPick={onPick} />
            ))}
          </ul>
        )}
        {meta.status === "loading" && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-[5.5rem] rounded-xl" />
            <Skeleton className="h-[5.5rem] rounded-xl" />
            <Skeleton className="h-[5.5rem] rounded-xl" />
            <Skeleton className="h-[5.5rem] rounded-xl" />
          </div>
        )}
        {meta.status === "error" && (
          <ErrorNotice className="mt-3" message={meta.message} onRetry={onRetryMeta} />
        )}
      </div>
    </div>
  );
}
