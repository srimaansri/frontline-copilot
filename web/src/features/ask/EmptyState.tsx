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
    <div className="mt-8 max-w-md border-t border-line-strong pt-4">
      <h3 className="cue">Every question passes four stages</h3>
      <div className="mt-3 flex items-center gap-5">
        <SignalBars level={4} tone="ink" size="lg" />
        <ol className="grid grid-flow-col grid-rows-2 gap-x-8 gap-y-1 text-meta text-ink-2">
          {STAGES.map((stage, index) => (
            <li key={stage} className="flex items-baseline gap-2 whitespace-nowrap">
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

/**
 * An example set like a line in a script: the cue on the left, the line to
 * say on the right. The cue and the question sit on one baseline.
 */
function ExampleCard({ example, tools, onPick }: ExampleCardProps) {
  return (
    <li className="grid sm:col-span-3 sm:grid-cols-subgrid">
      <button
        type="button"
        onClick={() => {
          onPick(example.question);
        }}
        className="grid grid-cols-[minmax(0,1fr)_auto] content-center items-baseline overflow-hidden rounded-box border border-line-strong bg-surface text-left transition-[border-color,background-color,box-shadow] hover:edge-ink active:bg-sunken sm:col-span-3 sm:grid-cols-subgrid"
      >
        <span className="col-span-2 flex items-baseline gap-3 border-b border-line px-4 py-2 leading-6 cue sm:col-span-1 sm:border-b-0 sm:py-0">
          <ToolIcon name={example.tool} size={24} className="self-center text-ink" />
          {toolLabel(tools, example.tool)}
        </span>
        {/* The rule between cue and line runs the full height of the card, whatever the row's own height. */}
        <span className="relative px-4 py-3 sm:before:absolute sm:before:-inset-y-40 sm:before:left-0 sm:before:border-l sm:before:border-line">
          <span className="block text-read leading-snug font-semibold text-ink">
            {example.question}
          </span>
          <span className="mt-0.5 block text-meta text-ink-3">{example.hint}</span>
        </span>
        <SendIcon className="mr-4 self-center text-brand-text" />
      </button>
    </li>
  );
}

export interface ExampleListProps {
  examples: readonly ExampleQuestion[];
  tools: readonly ToolInfo[];
  onPick: (question: string) => void;
}

/**
 * The example questions. From tablet width up the cards share one grid, so
 * the cue column is exactly as wide as the longest cue, and every card is as
 * tall as the tallest: they are one set of parallel choices, and equal rows
 * let the eye run down the questions without the rhythm changing. On a phone
 * each card stacks its cue over its question and is as tall as its content.
 */
export function ExampleList({ examples, tools, onPick }: ExampleListProps) {
  return (
    <ul className="grid gap-3 sm:auto-rows-fr sm:grid-cols-[auto_minmax(0,1fr)_auto]">
      {examples.map((example) => (
        <ExampleCard key={example.question} example={example} tools={tools} onPick={onPick} />
      ))}
    </ul>
  );
}

export interface EmptyStateProps {
  meta: Loadable<Meta>;
  onRetryMeta: () => void;
  onPick: (question: string) => void;
}

/**
 * What the Ask view shows before the first question: a headline and four
 * examples. The block sits a little above the middle of the space over the
 * question box, so the page is not top-heavy on a tall window, and it never
 * drifts further than a fixed distance from the top bar.
 */
export function EmptyState({ meta, onRetryMeta, onPick }: EmptyStateProps) {
  return (
    <div className="flex min-h-full flex-col">
      <div aria-hidden="true" className="max-h-32 min-h-10 flex-1" />
      <div className="mx-auto grid w-full max-w-7xl items-start gap-x-18 gap-y-10 px-4 sm:px-6 lg:px-12 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] xl:px-18">
        <div>
          {/* The drawing has 3 units of air on its left; pulled back so the head lines up with the headline. */}
          <CopilotMark size={64} className="mb-6 -ml-1.5" />
          <h2 className="display-view text-ink sm:display-head">What does the customer need?</h2>
          <p className="mt-5 max-w-md text-read text-ink-2">
            Ask a support question, look up a plan, or summarize a call. Every answer shows its
            sources and the steps behind it.
          </p>
          <StageKey />
        </div>

        <div>
          <h3 className="sr-only">Try an example</h3>
          {meta.status === "ready" && (
            <ExampleList examples={meta.data.examples} tools={meta.data.tools} onPick={onPick} />
          )}
          {meta.status === "loading" && (
            <div className="grid gap-3">
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </div>
          )}
          {meta.status === "error" && <ErrorNotice message={meta.message} onRetry={onRetryMeta} />}
        </div>
      </div>
      <div aria-hidden="true" className="min-h-8 flex-[1.5]" />
    </div>
  );
}
