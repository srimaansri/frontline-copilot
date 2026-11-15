import {
  BookOpenText,
  Headset,
  PhoneCall,
  ReceiptText,
  Wrench,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";

import type { ToolName } from "@/api/types";

const TOOL_ICONS: Record<ToolName, LucideIcon> = {
  search_kb: BookOpenText,
  get_plan_details: ReceiptText,
  summarize_call: PhoneCall,
  escalate_to_human: Headset,
};

function isToolName(name: string): name is ToolName {
  return name in TOOL_ICONS;
}

export type ToolIconProps = LucideProps & {
  /** The tool's name, such as search_kb. An unknown tool gets a plain icon. */
  name: string;
};

/** The icon that stands for a tool. Decorative: the tool's label is always beside it. */
export function ToolIcon({ name, ...props }: ToolIconProps) {
  const Icon = isToolName(name) ? TOOL_ICONS[name] : Wrench;
  return <Icon aria-hidden="true" {...props} />;
}
