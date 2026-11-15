import type { ToolInfo } from "@/api/types";
import { toolLabel } from "@/lib/tools";

import { ToolIcon } from "./ToolIcon";

export interface ToolBadgeProps {
  /** The tool's name, such as search_kb. */
  name: string;
  /** The tools the server described, for the label. */
  tools: readonly ToolInfo[];
}

/** A tool the copilot used for an answer: its icon and the label the server gives it. */
export function ToolBadge({ name, tools }: ToolBadgeProps) {
  return (
    <span className="inline-flex h-7 items-center gap-2 rounded-box border border-line-strong bg-surface pr-3 pl-2 text-meta font-semibold text-ink-2">
      <ToolIcon name={name} size={16} />
      {toolLabel(tools, name)}
    </span>
  );
}
