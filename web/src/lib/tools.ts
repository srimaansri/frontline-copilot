import type { ToolInfo } from "@/api/types";

/** The tool that opens a hand-off to a person. Its step is drawn as a branch off the route. */
export const HANDOFF_TOOL = "escalate_to_human";

/** The label the server gives a tool, or its name if the server gave none. */
export function toolLabel(tools: readonly ToolInfo[], name: string): string {
  return tools.find((tool) => tool.name === name)?.label ?? name;
}
