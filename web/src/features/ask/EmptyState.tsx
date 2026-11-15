import type { ExampleQuestion, Meta, ToolInfo } from "@/api/types";
import { CopilotMark } from "@/components/icons/CopilotMark";
import { SendIcon } from "@/components/icons/glyphs";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { SignalBars } from "@/components/shared/SignalBars";
import { ToolIcon } from "@/components/shared/ToolIcon";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { toolLabel } from "@/lib/tools";

/** The four stages every request passes, in order. One signal bar each. */
const STAGES = ["Privacy", "Request check", "Lookup", "Answer check"] as const;

/**
 * How an answer is made: the four signal bars, each named for its stage.
 * It explains the bars the agent will see filling while the copilot works.
 */
function StageKey() {
  return (
    <div className="mt-9 max-w-[27rem] border-t border-line-strong pt-4">
      <h3 className="text-label font-bold tracking-[0.01em] text-ink-2">
        Every question passes four stages
      </h3>
      <div className="mt-3 flex items-center gap-5">
        <SignalBars level={4} tone="ink" className="h-9 gap-1 *:w-2" />
        <ol className="grid grid-flow-col grid-rows-2 gap-x-7 gap-y-1 text-meta text-ink-2">
          {STAGES.map((stage, index) => (
            <li key={stage} className="flex items-baseline gap-1.5 whitespace-nowrap">
              <span className="font-mono font-semibold text-ink-3">{index + 1}</span>
              {stage}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

interface ExampleCardProps {
  example: ExampleQuestion;
  tools: readonly ToolInfo[];
  onPick: (question: string) => void;
}

/** An example set like a line in a script: the cue on the left, the line to say on the right. */
function ExampleCard({ example, tools, onPick }: ExampleCardProps) {
  return (
    <li>
      <button
        type="button"
        onClick={() => {
          onPick(example.question);
        }}
        className="group grid w-full grid-cols-[minmax(0,1fr)_20px] items-stretch rounded-box border border-line-strong bg-surface pr-[18px] text-left transition-shadow duration-150 hover:border-ink hover:shadow-[inset_0_0_0_0.5px_var(--ink)] sm:grid-cols-[204px_minmax(0,1fr)_20px]"
      >
        <span className="col-span-2 -mr-[18px] flex items-center gap-2.5 border-b border-line px-4 py-2 text-label font-bold tracking-[0.01em] text-ink-2 sm:col-span-1 sm:mr-0 sm:border-r sm:border-b-0 sm:py-0 sm:pr-3">
          <ToolIcon name={example.tool} size={24} className="text-ink" />
          {toolLabel(tools, example.tool)}
        </span>
        <span className="py-3.5 pr-4 pl-4 sm:pl-[18px]">
          <span className="block text-read leading-[1.35] font-semibold text-ink">
            {example.question}
          </span>
          <span className="mt-[3px] block text-meta text-ink-3">{example.hint}</span>
        </span>
        <SendIcon className="self-center text-brand-text" />
      </button>
    </li>
  );
}

export interface EmptyStateProps {
  meta: Loadable<Meta>;
  onRetryMeta: () => void;
  onPick: (question: string) => void;
}

/** What the Ask view shows before the first question: a headline and four examples. */
export function EmptyState({ meta, onRetryMeta, onPick }: EmptyStateProps) {
  return (
    <div className="mx-auto grid w-full max-w-[86rem] items-start gap-x-[72px] gap-y-10 px-4 pt-10 pb-8 sm:px-6 lg:px-12 xl:grid-cols-[480px_minmax(0,1fr)] xl:px-[72px] xl:pt-[72px]">
      <div>
        <CopilotMark size={44} className="mb-5" />
        <h2 className="font-display text-view font-bold tracking-[-0.025em] text-ink sm:text-head">
          What does the customer need?
        </h2>
        <p className="mt-5 max-w-[27rem] text-read text-ink-2">
          Ask a support question, look up a plan, or summarize a call. Every answer shows its
          sources and the steps behind it.
        </p>
        <StageKey />
      </div>

      <div>
        <h3 className="sr-only">Try an example</h3>
        {meta.status === "ready" && (
          <ul className="grid gap-2.5">
            {meta.data.examples.map((example) => (
              <ExampleCard
                key={example.question}
                example={example}
                tools={meta.data.tools}
                onPick={onPick}
              />
            ))}
          </ul>
        )}
        {meta.status === "loading" && (
          <div className="grid gap-2.5">
            <Skeleton className="h-[78px]" />
            <Skeleton className="h-[78px]" />
            <Skeleton className="h-[78px]" />
            <Skeleton className="h-[78px]" />
          </div>
        )}
        {meta.status === "error" && <ErrorNotice message={meta.message} onRetry={onRetryMeta} />}
      </div>
    </div>
  );
}
