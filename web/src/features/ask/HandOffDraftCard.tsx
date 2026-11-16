import { useEffect, useId, useRef, useState } from "react";

import { api, errorMessage, isAbortError } from "@/api/client";
import type { HandOffDraft, HandOffTicket, Urgency } from "@/api/types";
import { HandoffIcon } from "@/components/icons/glyphs";
import { Button } from "@/components/ui/button";

/** Who picks up each kind of hand-off. The server's list, in the words the agent reads. */
const TEAMS: readonly { category: string; label: string }[] = [
  { category: "billing", label: "The billing team" },
  { category: "plan_change", label: "The account team, for a plan change" },
  { category: "account_access", label: "The account security team" },
  { category: "device", label: "The device support team" },
  { category: "cancellation", label: "The account team, for a cancellation" },
  { category: "other", label: "A support specialist" },
];

const URGENCIES: readonly { value: Urgency; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
];

/** The longest reason the server accepts. */
const MAX_REASON_CHARS = 500;

type Stage =
  | { name: "draft" }
  | { name: "opening" }
  | { name: "failed"; message: string }
  | { name: "declined" }
  | { name: "open"; ticket: HandOffTicket };

export interface HandOffDraftCardProps {
  /** The hand-off the copilot drafted. Personal details in its reason are already replaced. */
  draft: HandOffDraft;
  /** A stage to show at once. Only the component gallery sets it. */
  initialTicket?: HandOffTicket;
}

/**
 * A hand-off waiting for the agent's decision. The copilot only drafts it:
 * nothing is sent until the agent has read it, changed what is wrong, and
 * pressed "Open the hand-off". The agent can also decide not to send it.
 *
 * It sits under the answer, outside the card with the cut corner, because it
 * is the agent's to act on and not something the copilot said.
 */
export function HandOffDraftCard({ draft, initialTicket }: HandOffDraftCardProps) {
  const [reason, setReason] = useState(draft.reason);
  const [category, setCategory] = useState(draft.category);
  const [urgency, setUrgency] = useState<Urgency>(draft.urgency);
  const [stage, setStage] = useState<Stage>(
    initialTicket ? { name: "open", ticket: initialTicket } : { name: "draft" },
  );
  const controller = useRef<AbortController | null>(null);
  const reasonId = useId();
  const teamId = useId();
  const urgencyId = useId();

  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );

  const open = () => {
    const current = new AbortController();
    controller.current = current;
    setStage({ name: "opening" });
    api.openHandOff({ reason: reason.trim(), category, urgency }, current.signal).then(
      (ticket) => {
        setStage({ name: "open", ticket });
      },
      (error: unknown) => {
        if (!isAbortError(error)) {
          setStage({ name: "failed", message: errorMessage(error) });
        }
      },
    );
  };

  if (stage.name === "open") {
    const { ticket } = stage;
    return (
      <section
        aria-label="Hand-off to a person"
        className="mt-2 animate-rise rounded-box border border-warn bg-warn-tint px-4 py-4 text-ink"
      >
        <p className="flex items-center gap-3 font-semibold">
          <HandoffIcon className="text-warn" />
          {ticket.recorded ? "The hand-off is open." : "The ticket could not be written."}
          <span className="font-mono">{ticket.ticket_id}</span>
        </p>
        <p className="mt-3 text-label font-semibold text-ink-2">What to tell the customer</p>
        <p className="mt-1 border-l-2 border-warn pl-3 text-read">
          {/* The reference is read out letter by letter, so it is never broken across lines. */}
          {ticket.agent_script.split(ticket.ticket_id).map((part, index) => (
            <span key={index}>
              {index > 0 && (
                <span className="font-mono font-semibold whitespace-nowrap">{ticket.ticket_id}</span>
              )}
              {part}
            </span>
          ))}
        </p>
      </section>
    );
  }

  if (stage.name === "declined") {
    return (
      <section
        aria-label="Hand-off to a person"
        className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-box border border-line-strong bg-surface px-4 py-3 text-ink"
      >
        <p className="min-w-0 flex-1 basis-56 text-ui">
          Not opened. Nothing was sent to anyone.
        </p>
        <Button
          size="sm"
          onClick={() => {
            setStage({ name: "draft" });
          }}
        >
          Open it after all
        </Button>
      </section>
    );
  }

  const busy = stage.name === "opening";
  return (
    <section
      aria-label="Hand-off to a person"
      className="mt-2 rounded-box border border-warn bg-warn-tint px-4 py-4 text-ink"
    >
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-semibold">
        <HandoffIcon className="text-warn" />
        This needs a person.
        <span className="rounded-box border border-dashed border-line-strong px-2 py-0.5 text-label font-semibold text-ink-2">
          Not sent yet
        </span>
      </p>
      <p className="mt-2 text-ui text-ink-2">
        Check the hand-off, change what is wrong, then open it. Personal details were replaced
        before it was drafted.
      </p>

      <label htmlFor={reasonId} className="mt-4 block text-label font-semibold text-ink-2">
        What is needed
      </label>
      <div className="field mt-1 bg-surface px-3 py-2">
        <textarea
          id={reasonId}
          rows={2}
          value={reason}
          maxLength={MAX_REASON_CHARS}
          disabled={busy}
          onChange={(event) => {
            setReason(event.target.value);
          }}
          className="scrollbar-quiet block w-full resize-y bg-transparent text-ui text-ink"
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-56">
          <label htmlFor={teamId} className="block text-label font-semibold text-ink-2">
            Goes to
          </label>
          <div className="field mt-1 bg-surface px-2">
            <select
              id={teamId}
              value={category}
              disabled={busy}
              onChange={(event) => {
                setCategory(event.target.value);
              }}
              className="h-10 w-full bg-transparent text-ui text-ink"
            >
              {TEAMS.map((team) => (
                <option key={team.category} value={team.category}>
                  {team.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="basis-32">
          <label htmlFor={urgencyId} className="block text-label font-semibold text-ink-2">
            Urgency
          </label>
          <div className="field mt-1 bg-surface px-2">
            <select
              id={urgencyId}
              value={urgency}
              disabled={busy}
              onChange={(event) => {
                const chosen = URGENCIES.find((item) => item.value === event.target.value);
                setUrgency(chosen?.value ?? "normal");
              }}
              className="h-10 w-full bg-transparent text-ui text-ink"
            >
              {URGENCIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {stage.name === "failed" && (
        <p role="alert" className="mt-3 text-ui font-semibold text-ink">
          {stage.message}
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        <Button variant="primary" disabled={busy || reason.trim() === ""} onClick={open}>
          {busy ? "Opening the hand-off" : "Open the hand-off"}
        </Button>
        <Button
          variant="quiet"
          disabled={busy}
          onClick={() => {
            setStage({ name: "declined" });
          }}
        >
          Don&apos;t open it
        </Button>
      </div>
    </section>
  );
}
