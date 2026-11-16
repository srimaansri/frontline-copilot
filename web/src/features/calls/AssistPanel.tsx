import type { ReactNode } from "react";

import type {
  AssistArticle,
  AssistHandOff,
  AssistNextStep,
  AssistReminder,
  AssistState,
} from "@/api/types";
import { ArticlesIcon, HandoffIcon } from "@/components/icons/glyphs";
import { StatusLabel, StatusStamp } from "@/components/icons/StatusStamp";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { SignalBars } from "@/components/shared/SignalBars";
import { Byline, Sim } from "@/components/shared/Sim";

/** A turn as people count them: the first turn is turn 1. */
function turnNumber(turn: number): number {
  return turn + 1;
}

/**
 * When a part of the panel came up. At the turn it comes up it carries the
 * notice shape and the word "New"; after that, only the turn it dates from.
 */
function Since({ turn, isNew }: { turn: number; isNew: boolean }) {
  if (isNew) {
    return <StatusLabel status="notice">New at turn {turnNumber(turn)}</StatusLabel>;
  }
  return (
    <span className="text-label whitespace-nowrap text-ink-3">
      since turn <span className="font-mono">{turnNumber(turn)}</span>
    </span>
  );
}

/** The head of one part of the panel: what it is, and when it came up. */
function PartHead({ children, turn, isNew }: { children: ReactNode; turn: number; isNew: boolean }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <h4 className="cue">{children}</h4>
      <Since turn={turn} isNew={isNew} />
    </div>
  );
}

function Identity({ checkedAt, isNew }: { checkedAt: number | null; isNew: boolean }) {
  if (checkedAt === null) {
    return (
      <p className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <StatusLabel status="warning">Identity not checked yet</StatusLabel>
        <span className="text-label text-ink-3">No identity question answered so far</span>
      </p>
    );
  }
  return (
    <p className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <StatusLabel status="ok">Identity checked</StatusLabel>
      <Since turn={checkedAt} isNew={isNew} />
    </p>
  );
}

function Reminders({ reminders, at }: { reminders: AssistReminder[]; at: number }) {
  return (
    <ul className="mt-3 grid gap-3">
      {reminders.map((reminder) => (
        <li
          key={`${reminder.rule}:${reminder.turn}`}
          className="animate-rise grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 rounded-box border border-line-strong bg-surface px-4 py-3"
        >
          <StatusStamp status="warning" size={20} className="mt-0.5" />
          <div>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <p className="font-semibold text-ink">{reminder.title}</p>
              <Since turn={reminder.turn} isNew={reminder.turn === at} />
            </div>
            <p className="mt-1 text-meta text-ink-2">{reminder.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** The customer asked for a change to their account. A hint: nothing is drafted or sent. */
function HandOffHint({ hint, isNew }: { hint: AssistHandOff; isNew: boolean }) {
  return (
    <section
      aria-label="Account request"
      className="animate-rise rounded-box border border-warn bg-warn-tint px-4 py-3 text-ink"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="flex items-center gap-3 font-semibold">
          <HandoffIcon className="text-warn" />
          The customer asked for a change to their account
        </p>
        <Since turn={hint.turn} isNew={isNew} />
      </div>
      <p className="mt-2 text-ui">
        Cue cannot see or change an account. If the change is not yours to make, hand it to{" "}
        {hint.team}.
      </p>
    </section>
  );
}

interface NextStepProps {
  step: AssistNextStep | null;
  /** Why there is no step, when one was written and held back or could not be written. */
  problem: string | null;
  article: AssistArticle;
  isNew: boolean;
}

/** What the agent could say next. The copilot wrote it, so it sits on the cut-corner card. */
function NextStepCard({ step, problem, article, isNew }: NextStepProps) {
  if (step === null) {
    return (
      <p className="flex gap-3 text-meta text-ink-2">
        {problem !== null && <StatusStamp status="warning" className="mt-0.5" />}
        {problem ?? "Cue found nothing in this article to say next."}
      </p>
    );
  }
  return (
    <Sim cut={16} className="animate-rise" bodyClassName="px-4 pt-4 pb-5">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 pr-4">
        <Byline />
        <Since turn={step.since_turn} isNew={isNew} />
      </div>
      <h4 className="mt-3 cue">Suggested next step</h4>
      <p className="mt-1 text-read break-words text-ink">
        <PlaceholderText text={step.text} />
      </p>
      {step.unsupported.length > 0 && (
        <p className="mt-3 flex gap-3 text-meta text-ink-2">
          <StatusStamp status="notice" className="mt-0.5" />A figure here is in neither the article
          nor the call. Check it before you say it.
        </p>
      )}
      <p className="mt-3 text-label text-ink-3">Written from &ldquo;{article.title}&rdquo;</p>
    </Sim>
  );
}

/** The help article on show: its title as a link, and the passage that matters. */
function ArticleCard({ article, isNew }: { article: AssistArticle; isNew: boolean }) {
  return (
    <section
      aria-label="Help article"
      className="animate-rise rounded-box border border-line-strong bg-surface px-4 pt-3 pb-4"
    >
      <PartHead turn={article.since_turn} isNew={isNew}>
        Help article
      </PartHead>
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="link mt-2 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-3 font-semibold"
      >
        <ArticlesIcon />
        <span>
          {article.title}
          <span className="sr-only"> (opens in a new tab)</span>
        </span>
      </a>
      {article.heading !== null && <p className="mt-3 cue">{article.heading}</p>}
      <p className="mt-1 text-ui leading-relaxed break-words whitespace-pre-line text-ink">
        {article.passage}
      </p>
    </section>
  );
}

function Counted({ count, one, many }: { count: number; one: string; many: string }) {
  return (
    <>
      <span className="font-mono">{count}</span> {count === 1 ? one : many}
    </>
  );
}

type ProgressProps = Pick<AssistPanelProps, "state" | "turn" | "total" | "pending">;

/**
 * How far the panel has read, with the signal bars: seeking while the turn on
 * show is being read, all four once the panel is up to date with it, and two
 * when it is behind because a turn could not be read. It says nothing when
 * there is nothing read and nothing on its way.
 */
function Progress({ state, turn, total, pending }: ProgressProps) {
  if (state === null && !pending) {
    return null;
  }
  const upToDate = !pending && state?.turn === turn;
  let words = "Reading turn";
  if (!pending) {
    words = upToDate ? "Up to date at turn" : "Read as far as turn";
  }
  return (
    <p role="status" className="mt-2 flex items-center gap-3 text-meta text-ink-2">
      <SignalBars size="sm" level={upToDate ? 4 : 2} seeking={pending ? 2 : undefined} />
      <span>
        {words}{" "}
        <span className="font-mono">{turnNumber(pending ? turn : (state?.turn ?? turn))}</span> of{" "}
        <span className="font-mono">{total}</span>
      </span>
    </p>
  );
}

export interface AssistPanelProps {
  /** The newest state there is for the turns on show. Null until the first one arrives. */
  state: AssistState | null;
  /** The turn on show, counted from 0, and how many turns the call has. */
  turn: number;
  total: number;
  /** True while the turn on show has been asked about and not answered. */
  pending: boolean;
  /** Why there is nothing newer to show, when the last request failed. */
  problem: string | null;
  onRetry?: () => void;
}

/**
 * Call assist beside a replayed call: whether the customer's identity has been
 * checked, what the rules found, a hint to hand off, a suggested next step and
 * the help article it was written from. Nobody asks for any of it: it follows
 * the call, and each part says at which turn it came up.
 *
 * One thing here says "working": the signal bars in the head, which seek while
 * the turn on show is being read and stand full when the panel is up to date.
 */
export function AssistPanel({ state, turn, total, pending, problem, onRetry }: AssistPanelProps) {
  const changed = new Set(state?.changed ?? []);
  return (
    <section aria-label="Call assist">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h3 className="display-title text-ink">Call assist</h3>
        <span className="rounded-box border border-dashed border-line-strong px-2 py-0.5 text-label font-semibold text-ink-2">
          Replay of a recorded call
        </span>
      </div>
      <Progress state={state} turn={turn} total={total} pending={pending} />

      {problem !== null && <ErrorNotice className="mt-4" message={problem} onRetry={onRetry} />}

      {state !== null && (
        <div aria-live="polite" className="mt-5 grid gap-5">
          <section aria-label="Reminders">
            <Identity checkedAt={state.identity_checked_at} isNew={changed.has("identity")} />
            {state.reminders.length > 0 && (
              <Reminders reminders={state.reminders} at={state.turn} />
            )}
          </section>

          {state.hand_off !== null && (
            <HandOffHint
              key={state.hand_off.turn}
              hint={state.hand_off}
              isNew={changed.has("hand_off")}
            />
          )}

          {state.article === null ? (
            <p className="text-ink-2">
              No help article yet. Cue looks for one each time the customer says something, and
              shows it here without being asked.
            </p>
          ) : (
            <>
              {/* A new article is a new card: it arrives once, and the old one is gone. */}
              <NextStepCard
                key={`step:${state.article.url}:${state.article.since_turn}`}
                step={state.next_step}
                problem={state.step_problem}
                article={state.article}
                isNew={changed.has("next_step")}
              />
              <ArticleCard
                key={`article:${state.article.url}:${state.article.since_turn}`}
                article={state.article}
                isNew={changed.has("article")}
              />
            </>
          )}

          <p className="text-label text-ink-3">
            This call so far:{" "}
            <Counted count={state.cost.searches} one="search" many="searches" />,{" "}
            <Counted count={state.cost.model_calls} one="model call" many="model calls" />. A model
            is called only when the article changes.
          </p>
        </div>
      )}
    </section>
  );
}
