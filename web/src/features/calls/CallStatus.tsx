import type { Resolution, StepStatus } from "@/api/types";
import { StatusLabel, StatusStamp } from "@/components/icons/StatusStamp";

/** How a call ended, as a status: its shape, its colour and its word. */
const RESOLUTIONS: Record<Resolution, { label: string; status: StepStatus }> = {
  resolved: { label: "Resolved", status: "ok" },
  escalated: { label: "Escalated", status: "notice" },
  unresolved: { label: "Unresolved", status: "warning" },
};

export interface CallStatusProps {
  resolution: Resolution;
  className?: string;
}

/** The shape and the word for how a call ended. */
export function CallStatus({ resolution, className }: CallStatusProps) {
  const { label, status } = RESOLUTIONS[resolution];
  return (
    <StatusLabel status={status} className={className}>
      {label}
    </StatusLabel>
  );
}

/** Only the shape, where the word is written elsewhere. */
export function CallStatusStamp({ resolution, className }: CallStatusProps) {
  return <StatusStamp status={RESOLUTIONS[resolution].status} className={className} />;
}
