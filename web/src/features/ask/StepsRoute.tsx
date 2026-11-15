import type { ReactElement } from "react";

import type { Step, StepStage, StepStatus, ToolInfo } from "@/api/types";
import {
  AnswerCheckIcon,
  GenericToolIcon,
  HandoffIcon,
  PrivacyIcon,
  RequestCheckIcon,
} from "@/components/icons/glyphs";
import type { IconProps } from "@/components/icons/Icon";
import { StatusStamp, StatusWord } from "@/components/icons/StatusStamp";
import { ToolIcon } from "@/components/shared/ToolIcon";
import { cn } from "@/lib/cn";
import { HANDOFF_TOOL, toolLabel } from "@/lib/tools";

/** The four stages every request passes, in order. The third is whichever tool ran. */
const STAGES: Record<StepStage, { label: string; icon: (props: IconProps) => ReactElement }> = {
  redaction: { label: "Privacy", icon: PrivacyIcon },
  input_check: { label: "Request check", icon: RequestCheckIcon },
  tool: { label: "Lookup", icon: GenericToolIcon },
  output_check: { label: "Answer check", icon: AnswerCheckIcon },
};

const LEGEND_STATUSES: readonly { status: StepStatus; word: string }[] = [
  { status: "ok", word: "OK" },
  { status: "notice", word: "Notice" },
  { status: "warning", word: "Warning" },
  { status: "blocked", word: "Blocked" },
];

/** True for the step that passes the request to a person. */
function isHandOff(step: Step): boolean {
  return step.stage === "tool" && step.tool === HANDOFF_TOOL;
}

function StageCue({ step, tools }: { step: Step; tools: readonly ToolInfo[] }) {
  const stage = STAGES[step.stage];
  const Glyph = stage.icon;
  return (
    <p className="flex min-h-6 items-center gap-2 cue">
      {step.tool === null ? <Glyph size={16} /> : <ToolIcon name={step.tool} size={16} />}
      {step.tool === null ? stage.label : toolLabel(tools, step.tool)}
    </p>
  );
}

interface StationProps {
  step: Step;
  tools: readonly ToolInfo[];
  index: number;
}

function Station({ step, tools, index }: StationProps) {
  const branch = isHandOff(step);
  return (
    <li
      className="stn animate-rise"
      data-branch={branch}
      style={{ animationDelay: `calc(var(--stagger) * ${index})` }}
    >
      {branch && (
        // The line leaves the copilot at 45 degrees. This leg is still the copilot's: solid.
        <svg className="stn-diag" viewBox="0 0 52 28" aria-hidden="true" focusable="false">
          <path d="M12 0L40 28" />
        </svg>
      )}
      <div className="stn-row">
        <span className="stn-stamp">
          <StatusStamp status={step.status} size={24} className="relative z-[1]" />
          {/* From here the request is with a person: dashed, down to the tag. */}
          {branch && <span aria-hidden="true" className="stn-leg" />}
        </span>
        {/* On the branch, the space under the text is where the dashed leg runs down to the tag. */}
        <div className={cn("min-w-0", branch && "pb-3")}>
          <StageCue step={step} tools={tools} />
          <p className="mt-0.5 font-bold text-ink">{step.title}</p>
          {step.detail !== "" && <p className="mt-0.5 text-meta text-ink-2">{step.detail}</p>}
        </div>
        <StatusWord status={step.status} className="leading-6" />
      </div>
      {branch && (
        <p className="stn-tag">
          <HandoffIcon size={16} />
          Handed to a person
          {step.reference !== null && step.reference !== "" && (
            <span className="font-mono font-semibold">{step.reference}</span>
          )}
        </p>
      )}
    </li>
  );
}

/** The key to the route: the four status shapes and the two kinds of leg. */
export function RouteLegend() {
  return (
    <div className="border-t border-line pt-3 text-label text-ink-2">
      <h4 className="cue">Legend</h4>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
        {LEGEND_STATUSES.map(({ status, word }) => (
          <li key={status} className="flex items-center gap-2">
            <StatusStamp status={status} />
            {word}
          </li>
        ))}
      </ul>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="legend-line" />
          Done by Cue
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="legend-line" data-leg="dashed" />
          Passed to a person
        </li>
      </ul>
    </div>
  );
}

export interface StepsRouteProps {
  steps: readonly Step[];
  tools: readonly ToolInfo[];
}

/**
 * What the copilot did to produce one answer, drawn as a route: one line, a
 * station for every step, top to bottom in the order it happened. A hand-off
 * branches off the line and ends on a tag that says a person has the request,
 * while the main line carries on to the answer checks.
 */
export function StepsRoute({ steps, tools }: StepsRouteProps) {
  return (
    <>
      <ol className="route">
        {steps.map((step, index) => (
          // Steps arrive in a fixed order and are never reordered.
          <Station key={index} step={step} tools={tools} index={index} />
        ))}
      </ol>
      <div className="mt-6">
        <RouteLegend />
      </div>
    </>
  );
}
