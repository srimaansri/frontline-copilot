import { useState } from "react";

import { api, errorMessage } from "@/api/client";
import { ThumbDownIcon, ThumbUpIcon } from "@/components/icons/glyphs";
import { StatusLabel } from "@/components/icons/StatusStamp";
import { IconButton } from "@/components/ui/icon-button";

export type FeedbackState =
  | { status: "idle" }
  | { status: "saving"; helpful: boolean }
  | { status: "saved"; helpful: boolean }
  | { status: "error"; message: string };

export interface FeedbackButtonsProps {
  /** The trace the vote is recorded against. */
  traceId: string;
  /** The state to start in. Only the component gallery sets it, to show each state. */
  initialState?: FeedbackState;
}

/** Thumbs up and down for one answer. One vote, then both buttons are off. */
export function FeedbackButtons({ traceId, initialState }: FeedbackButtonsProps) {
  const [state, setState] = useState<FeedbackState>(initialState ?? { status: "idle" });

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
    <div className="flex items-center gap-2">
      <span aria-live="polite" className="text-meta">
        {state.status === "saved" && (
          <StatusLabel status="ok" className="animate-fade">
            Saved
          </StatusLabel>
        )}
        {state.status === "error" && <span className="text-ink-2">{state.message}</span>}
      </span>
      <IconButton
        label="Helpful"
        // Ink fill: this is the vote that was cast.
        variant={chosen === true ? "on" : "outline"}
        aria-pressed={chosen === true}
        disabled={locked}
        className={chosen === true ? "disabled:opacity-100" : undefined}
        onClick={() => {
          vote(true);
        }}
      >
        <ThumbUpIcon />
      </IconButton>
      <IconButton
        label="Not helpful"
        variant={chosen === false ? "on" : "outline"}
        aria-pressed={chosen === false}
        disabled={locked}
        className={chosen === false ? "disabled:opacity-100" : undefined}
        onClick={() => {
          vote(false);
        }}
      >
        <ThumbDownIcon />
      </IconButton>
    </div>
  );
}
