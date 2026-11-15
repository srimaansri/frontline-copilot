import type { ToolInfo } from "@/api/types";

/** The label the server gives a tool, or its name if the server gave none. */
export function toolLabel(tools: readonly ToolInfo[], name: string): string {
  return tools.find((tool) => tool.name === name)?.label ?? name;
}
