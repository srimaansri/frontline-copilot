import { RetryIcon } from "@/components/icons/glyphs";
import { StatusStamp } from "@/components/icons/StatusStamp";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export interface ErrorNoticeProps {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

/**
 * A calm, inline account of something that failed, with a way to try again.
 * It is the system speaking, not the copilot, so its corners are square.
 */
export function ErrorNotice({
  message,
  onRetry,
  retryLabel = "Try again",
  className,
}: ErrorNoticeProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-3 rounded-box border border-line-strong bg-surface px-4 py-3",
        className,
      )}
    >
      <div className="flex min-w-0 flex-1 basis-56 items-start gap-3">
        <StatusStamp status="warning" size={20} className="mt-0.5" />
        <p className="text-ui leading-relaxed text-ink">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          <RetryIcon size={16} />
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
