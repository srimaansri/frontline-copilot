import type { ReactElement } from "react";

import type { ToolName } from "@/api/types";
import {
  ArticlesIcon,
  CallSummaryIcon,
  GenericToolIcon,
  HandoffIcon,
  PlansIcon,
} from "@/components/icons/glyphs";
import type { IconProps } from "@/components/icons/Icon";

const TOOL_ICONS: Record<ToolName, (props: IconProps) => ReactElement> = {
  search_kb: ArticlesIcon,
  get_plan_details: PlansIcon,
  summarize_call: CallSummaryIcon,
  escalate_to_human: HandoffIcon,
};

function isToolName(name: string): name is ToolName {
  return name in TOOL_ICONS;
}

export type ToolIconProps = IconProps & {
  /** The tool's name, such as search_kb. An unknown tool gets a plain icon. */
  name: string;
};

/** The icon that stands for a tool. Decorative: the tool's label is always beside it. */
export function ToolIcon({ name, ...props }: ToolIconProps) {
  const Glyph = isToolName(name) ? TOOL_ICONS[name] : GenericToolIcon;
  return <Glyph {...props} />;
}
