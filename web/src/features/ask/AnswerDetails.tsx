import type { ReactNode } from "react";

import type { AskResponse, ToolInfo } from "@/api/types";
import { countOf } from "@/lib/format";

import { SourceList, type SourceHighlight } from "./SourceList";
import { StepsTimeline } from "./StepsTimeline";

interface SectionProps {
  title: string;
  /** A short count shown beside the title. */
  aside?: string;
  children: ReactNode;
}

function Section({ title, aside, children }: SectionProps) {
  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-fg">{title}</h3>
        {aside !== undefined && <span className="text-xs text-fg-subtle">{aside}</span>}
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

/** The sources of one answer and the steps that produced it. */
export function AnswerDetails({ response, tools, highlight }: AnswerDetailsProps) {
  const { citations, steps } = response;
  return (
    <div className="space-y-8">
      <Section
        title="Sources"
        aside={citations.length > 0 ? countOf(citations.length, "source") : undefined}
      >
        <SourceList citations={citations} highlight={highlight} />
      </Section>
      <Section title="What the copilot did" aside={countOf(steps.length, "step")}>
        <StepsTimeline steps={steps} tools={tools} />
      </Section>
    </div>
  );
}
