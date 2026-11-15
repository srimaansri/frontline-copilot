import type { Resolution } from "@/api/types";
import { Badge, type BadgeTone } from "@/components/ui/badge";

const RESOLUTIONS: Record<Resolution, { label: string; tone: BadgeTone }> = {
  resolved: { label: "Resolved", tone: "ok" },
  escalated: { label: "Escalated", tone: "warning" },
  unresolved: { label: "Unresolved", tone: "neutral" },
};

export interface ResolutionBadgeProps {
  resolution: Resolution;
}

/** How a call ended. */
export function ResolutionBadge({ resolution }: ResolutionBadgeProps) {
  const { label, tone } = RESOLUTIONS[resolution];
  return <Badge tone={tone}>{label}</Badge>;
}
