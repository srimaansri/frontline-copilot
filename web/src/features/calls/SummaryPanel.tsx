import {
  ExternalLink,
  Frown,
  LoaderCircle,
  Meh,
  Smile,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import type { CallSummary, Sentiment } from "@/api/types";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Loadable } from "@/hooks/useLoad";
import { humanize } from "@/lib/format";

const SENTIMENTS: Record<Sentiment, { label: string; tone: BadgeTone; icon: LucideIcon }> = {
  positive: { label: "Positive", tone: "ok", icon: Smile },
  neutral: { label: "Neutral", tone: "neutral", icon: Meh },
  negative: { label: "Negative", tone: "blocked", icon: Frown },
};

function Overline({ children }: { children: ReactNode }) {
  return (
    <h4 className="text-[0.6875rem] leading-4 font-semibold tracking-[0.08em] text-fg-subtle uppercase">
      {children}
    </h4>
  );
}

function SummaryCard({ summary }: { summary: CallSummary }) {
  const sentiment = SENTIMENTS[summary.sentiment];
  const SentimentIcon = sentiment.icon;
  return (
    <div className="mt-4 animate-rise space-y-5">
      <div>
        <Overline>Intent</Overline>
        <p className="mt-1 text-lg leading-snug font-semibold text-fg">
          <PlaceholderText text={humanize(summary.intent)} />
        </p>
        <Badge tone={sentiment.tone} className="mt-2.5">
          <SentimentIcon aria-hidden="true" />
          <span className="sr-only">Sentiment: </span>
          {sentiment.label}
        </Badge>
      </div>

      <div>
        <Overline>What happened</Overline>
        <ul className="mt-2 space-y-2">
          {summary.summary_bullets.map((bullet) => (
            <li key={bullet} className="flex gap-3 text-base leading-relaxed text-fg">
              <span aria-hidden="true" className="mt-[0.7em] size-1.5 shrink-0 rounded-full bg-accent" />
              <span className="min-w-0 break-words">
                <PlaceholderText text={bullet} />
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border bg-surface-muted px-4 py-3">
        <Overline>Next step</Overline>
        <p className="mt-1 text-base leading-relaxed font-medium text-fg">
          <PlaceholderText text={summary.next_step} />
        </p>
      </div>

      {summary.related_articles.length > 0 && (
        <div>
          <Overline>Related articles</Overline>
          <ul className="mt-2 space-y-1.5">
            {summary.related_articles.map((article) => (
              <li key={article.number}>
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex items-start gap-2 text-[0.9375rem] leading-snug font-medium text-accent underline decoration-accent/40 underline-offset-[3px] hover:decoration-accent"
                >
                  {article.title}
                  <ExternalLink aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export interface SummaryPanelProps {
  /** Undefined until a summary has been asked for. */
  summary: Loadable<CallSummary> | undefined;
  onSummarize: () => void;
}

/** A button that asks for a summary of the call, and then the summary. */
export function SummaryPanel({ summary, onSummarize }: SummaryPanelProps) {
  const loading = summary?.status === "loading";
  return (
    <section aria-label="Call summary">
      <div className="flex min-h-9 items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-fg">Summary</h3>
        {(summary === undefined || loading) && (
          <Button size="sm" className="h-9" disabled={loading} onClick={onSummarize}>
            {loading ? (
              <LoaderCircle aria-hidden="true" className="animate-spin" />
            ) : (
              <Sparkles aria-hidden="true" />
            )}
            {loading ? "Summarizing" : "Summarize"}
          </Button>
        )}
      </div>

      <div aria-live="polite">
        {summary === undefined && (
          <p className="mt-2 text-sm leading-relaxed text-fg-subtle">
            See what the call was about, the customer&apos;s mood and the next step.
          </p>
        )}
        {loading && (
          <div className="mt-5 space-y-3">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-4/5" />
          </div>
        )}
        {summary?.status === "error" && (
          <ErrorNotice className="mt-3" message={summary.message} onRetry={onSummarize} />
        )}
        {summary?.status === "ready" && <SummaryCard summary={summary.data} />}
      </div>
    </section>
  );
}
