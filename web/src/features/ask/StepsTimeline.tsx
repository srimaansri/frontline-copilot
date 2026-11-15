import { Check, Info, OctagonX, TriangleAlert, type LucideIcon } from "lucide-react";

import type { Step, StepStage, StepStatus, ToolInfo } from "@/api/types";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { toolLabel } from "@/lib/tools";

interface StatusStyle {
  icon: LucideIcon;
  /** The node on the rail. */
  node: string;
  /** Said to screen readers, and shown as a badge unless the step is plain "ok". */
  label: string;
  badge: BadgeTone;
}

const STATUS_STYLES: Record<StepStatus, StatusStyle> = {
  ok: { icon: Check, node: "border-ok/25 bg-ok-soft text-ok", label: "OK", badge: "ok" },
  notice: {
    icon: Info,
    node: "border-notice/30 bg-notice-soft text-notice",
    label: "Notice",
    badge: "notice",
  },
  warning: {
    icon: TriangleAlert,
    node: "border-warning/35 bg-warning-soft text-warning",
    label: "Warning",
    badge: "warning",
  },
  blocked: {
    icon: OctagonX,
    node: "border-blocked/35 bg-blocked-soft text-blocked",
    label: "Blocked",
    badge: "blocked",
  },
};

const STAGE_LABELS: Record<StepStage, string> = {
  redaction: "Privacy",
  input_check: "Request check",
  tool: "Lookup",
  output_check: "Answer check",
};

/** The small heading over a step: its tool's label, or the name of its stage. */
function headingOf(step: Step, tools: readonly ToolInfo[]): string {
  return step.tool === null ? STAGE_LABELS[step.stage] : toolLabel(tools, step.tool);
}

export interface StepsTimelineProps {
  steps: readonly Step[];
  tools: readonly ToolInfo[];
}

/**
 * What the copilot did to produce one answer, top to bottom in the order it
 * happened. Each step has a node on a rail, coloured by how it went.
 */
export function StepsTimeline({ steps, tools }: StepsTimelineProps) {
  return (
    <ol className="relative">
      {steps.map((step, index) => {
        const style = STATUS_STYLES[step.status];
        const Icon = style.icon;
        const heading = headingOf(step, tools);
        const previous = steps[index - 1];
        const repeatsHeading = previous !== undefined && headingOf(previous, tools) === heading;
        const last = index === steps.length - 1;
        return (
          <li
            // Steps arrive in a fixed order and are never reordered.
            key={index}
            className="relative flex animate-rise gap-3.5 pb-6 last:pb-0"
            style={{ animationDelay: `${index * 55}ms` }}
          >
            {!last && (
              <span
                aria-hidden="true"
                className="absolute top-9 bottom-1 left-[15px] w-0.5 rounded-full bg-border"
              />
            )}
            <span
              aria-hidden="true"
              className={cn(
                "relative flex size-8 shrink-0 items-center justify-center rounded-full border",
                style.node,
              )}
            >
              <Icon className="size-4" strokeWidth={2.25} />
            </span>
            <div className="min-w-0 flex-1 pt-px">
              <p
                className={cn(
                  "text-[0.6875rem] leading-4 font-semibold tracking-[0.08em] text-fg-subtle uppercase",
                  repeatsHeading && "sr-only",
                )}
              >
                {heading}
              </p>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="text-[0.9375rem] leading-snug font-medium text-fg">{step.title}</p>
                {step.status === "ok" ? (
                  <span className="sr-only">({style.label})</span>
                ) : (
                  <Badge tone={style.badge} className="px-2 py-0 text-[0.6875rem] leading-5">
                    {style.label}
                  </Badge>
                )}
              </div>
              {step.detail !== "" && (
                <p className="mt-1 text-sm leading-relaxed text-fg-muted">{step.detail}</p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
