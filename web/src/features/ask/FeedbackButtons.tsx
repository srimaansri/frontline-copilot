import { Check, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { api, errorMessage } from "@/api/client";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/cn";

type FeedbackState =
  | { status: "idle" }
  | { status: "saving"; helpful: boolean }
  | { status: "saved"; helpful: boolean }
  | { status: "error"; message: string };

export interface FeedbackButtonsProps {
  /** The trace the vote is recorded against. */
  traceId: string;
}

/** Thumbs up and down for one answer. One vote, then both buttons are off. */
export function FeedbackButtons({ traceId }: FeedbackButtonsProps) {
  const [state, setState] = useState<FeedbackState>({ status: "idle" });

  const vote = (helpful: boolean) => {
    setState({ status: "saving", helpful });
    api.sendFeedback({ trace_id: traceId, helpful }).then(
      () => {
        setState({ status: "saved", helpful });
      },
      (error: unknown) => {
        setState({ status: "error", message: errorMessage(error) });
      },
    );
  };

  const locked = state.status === "saving" || state.status === "saved";
  const chosen = locked ? state.helpful : null;

  return (
    <div className="flex items-center gap-1">
      <span aria-live="polite" className="mr-1 text-xs text-fg-subtle">
        {state.status === "saved" && (
          <span className="inline-flex animate-fade items-center gap-1 font-medium text-ok">
            <Check aria-hidden="true" className="size-3.5" />
            Saved
          </span>
        )}
        {state.status === "error" && <span className="text-fg-muted">{state.message}</span>}
      </span>
      <IconButton
        label="Helpful"
        aria-pressed={chosen === true}
        disabled={locked}
        onClick={() => {
          vote(true);
        }}
        className={cn("size-8", chosen === true && "bg-accent-soft text-accent-soft-fg disabled:opacity-100")}
      >
        <ThumbsUp aria-hidden="true" />
      </IconButton>
      <IconButton
        label="Not helpful"
        aria-pressed={chosen === false}
        disabled={locked}
        onClick={() => {
          vote(false);
        }}
        className={cn("size-8", chosen === false && "bg-accent-soft text-accent-soft-fg disabled:opacity-100")}
      >
        <ThumbsDown aria-hidden="true" />
      </IconButton>
    </div>
  );
}
