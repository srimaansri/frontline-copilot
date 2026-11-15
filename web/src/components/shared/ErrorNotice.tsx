import { CircleAlert, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export interface ErrorNoticeProps {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

/** A calm, inline account of something that failed, with a way to try again. */
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
        "flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border bg-surface px-4 py-3",
        className,
      )}
    >
      <div className="flex min-w-0 flex-1 basis-56 items-start gap-3">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-warning" />
        <p className="text-[0.9375rem] leading-relaxed text-fg-muted">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCw aria-hidden="true" />
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
