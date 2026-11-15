import type { ReactElement, ReactNode } from "react";

import type { CallSummary, Sentiment } from "@/api/types";
import { CopilotMark } from "@/components/icons/CopilotMark";
import {
  ArticlesIcon,
  CallSummaryIcon,
  MoodNegativeIcon,
  MoodNeutralIcon,
  MoodPositiveIcon,
} from "@/components/icons/glyphs";
import type { IconProps } from "@/components/icons/Icon";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { SignalBars } from "@/components/shared/SignalBars";
import { Byline, Sim } from "@/components/shared/Sim";
import { Button } from "@/components/ui/button";
import { useCycle } from "@/hooks/useCycle";
import type { Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";
import { humanize } from "@/lib/format";

interface Mood {
  label: string;
  /** The colour repeats what the face already says. */
  tone: string;
  icon: (props: IconProps) => ReactElement;
}

const MOODS: Record<Sentiment, Mood> = {
  positive: { label: "Positive", tone: "text-ok", icon: MoodPositiveIcon },
  neutral: { label: "Neutral", tone: "text-ink-2", icon: MoodNeutralIcon },
  negative: { label: "Negative", tone: "text-warn", icon: MoodNegativeIcon },
};

function Field({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="mb-1 text-label font-bold tracking-[0.01em] text-ink-2">{term}</dt>
      <dd className="leading-normal text-ink">{children}</dd>
    </div>
  );
}

function SummaryCard({ summary }: { summary: CallSummary }) {
  const mood = MOODS[summary.sentiment];
  const MoodIcon = mood.icon;
  return (
    <Sim className="animate-rise" bodyClassName="px-5 pt-5 pb-6 sm:px-6">
      <Byline />
      <dl className="mt-4 grid gap-[18px]">
        <Field term="Intent">
          <span className="block font-display text-title font-bold tracking-[-0.01em]">
            <PlaceholderText text={humanize(summary.intent)} />
          </span>
        </Field>
        <Field term="Mood">
          <span className={cn("inline-flex items-center gap-2 font-bold", mood.tone)}>
            <MoodIcon size={24} />
            {mood.label}
          </span>
        </Field>
        <Field term="What happened">
          <ol className="grid gap-2">
            {summary.summary_bullets.map((bullet, index) => (
              <li key={bullet} className="grid grid-cols-[24px_minmax(0,1fr)]">
                <span aria-hidden="true" className="font-mono font-semibold text-ink-3">
                  {index + 1}.
                </span>
                <span className="break-words">
                  <PlaceholderText text={bullet} />
                </span>
              </li>
            ))}
          </ol>
        </Field>
        <Field term="Next step">
          <PlaceholderText text={summary.next_step} />
        </Field>
        {summary.related_articles.length > 0 && (
          <Field term="Related articles">
            <ul className="mt-0.5">
              {summary.related_articles.map((article) => (
                <li key={article.number} className="border-t border-line first:border-t-0">
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="grid grid-cols-[20px_minmax(0,1fr)] items-center gap-2.5 py-[9px] font-semibold text-brand-text underline underline-offset-[3px]"
                  >
                    <ArticlesIcon />
                    <span>
                      {article.title}
                      <span className="sr-only"> (opens in a new tab)</span>
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </Field>
        )}
      </dl>
    </Sim>
  );
}

/** The copilot's card while it writes the summary, with its signal bars seeking. */
function Summarizing() {
  const bar = useCycle(4, 900);
  return (
    <div role="status" className="flex">
      <Sim cut={16} bodyClassName="flex items-center gap-3.5 py-3.5 pr-9 pl-[18px] text-read">
        <CopilotMark size={18} />
        <SignalBars level={bar} seeking={bar} />
        Summarizing
      </Sim>
    </div>
  );
}

export interface SummaryPanelProps {
  /** Undefined until a summary has been asked for. */
  summary: Loadable<CallSummary> | undefined;
  onSummarize: () => void;
}

/** A button that asks the copilot for a summary of the call, and then the summary. */
export function SummaryPanel({ summary, onSummarize }: SummaryPanelProps) {
  return (
    <section aria-label="Call summary">
      {summary?.status !== "ready" && (
        <h3 className="font-display text-title font-bold tracking-[-0.01em] text-ink">Summary</h3>
      )}
      <div aria-live="polite">
        {summary === undefined && (
          <>
            <p className="mt-2 text-ink-2">
              See what the call was about, the customer&apos;s mood and the next step.
            </p>
            <Button variant="primary" className="mt-4" onClick={onSummarize}>
              <CallSummaryIcon />
              Summarize
            </Button>
          </>
        )}
        {summary?.status === "loading" && (
          <div className="mt-4">
            <Summarizing />
          </div>
        )}
        {summary?.status === "error" && (
          <ErrorNotice className="mt-4" message={summary.message} onRetry={onSummarize} />
        )}
        {summary?.status === "ready" && <SummaryCard summary={summary.data} />}
      </div>
    </section>
  );
}
