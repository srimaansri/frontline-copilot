import type { ReactNode } from "react";

import type { AskResponse, Step, StepStatus, ToolInfo } from "@/api/types";
import { StatusStamp } from "@/components/icons/StatusStamp";
import { countOf } from "@/lib/format";

import { SourceList, type SourceHighlight } from "./SourceList";
import { StepsRoute } from "./StepsRoute";

const STATUS_WORDS: readonly { status: StepStatus; word: string }[] = [
  { status: "blocked", word: "blocked" },
  { status: "warning", word: "warning" },
  { status: "notice", word: "notice" },
  { status: "ok", word: "OK" },
];

/** "1 warning, 1 notice, 2 OK": the run in words, worst first. */
function describeRun(steps: readonly Step[]): string {
  return STATUS_WORDS.map(({ status, word }) => {
    const count = steps.filter((step) => step.status === status).length;
    return count > 0 ? `${count} ${word}` : null;
  })
    .filter((part) => part !== null)
    .join(", ");
}

/** A row of status shapes, one per step: the whole run at a glance, before its detail. */
function Tally({ steps }: { steps: readonly Step[] }) {
  return (
    <span role="img" aria-label={describeRun(steps)} className="inline-flex items-center gap-1">
      {steps.map((step, index) => (
        // Steps arrive in a fixed order and are never reordered.
        <StatusStamp key={index} status={step.status} />
      ))}
    </span>
  );
}

interface SectionProps {
  title: string;
  /** A count in mono, and anything else that sums the section up. */
  aside?: ReactNode;
  children: ReactNode;
}

function Section({ title, aside, children }: SectionProps) {
  return (
    <section className="border-line-strong not-first:mt-8 not-first:border-t not-first:pt-6">
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="display-title text-ink">{title}</h3>
        {aside !== undefined && (
          <span className="ml-auto inline-flex items-center gap-3 font-mono text-meta text-ink-2">
            {aside}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

export interface AnswerDetailsProps {
  response: AskResponse;
  tools: readonly ToolInfo[];
  highlight: SourceHighlight | null;
}

/** The sources of one answer and the route of steps that produced it. */
export function AnswerDetails({ response, tools, highlight }: AnswerDetailsProps) {
  const { citations, steps } = response;
  return (
    <div>
      <Section
        title="Sources"
        aside={citations.length > 0 ? countOf(citations.length, "source") : undefined}
      >
        <SourceList citations={citations} highlight={highlight} />
      </Section>
      <Section
        title="What Cue did"
        aside={
          <>
            {countOf(steps.length, "step")}
            <Tally steps={steps} />
          </>
        }
      >
        <StepsRoute steps={steps} tools={tools} />
      </Section>
    </div>
  );
}
