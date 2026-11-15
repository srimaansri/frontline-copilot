import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { api, errorMessage } from "@/api/client";
import type { CallListItem, CallSummary } from "@/api/types";
import { BackIcon, CallsIcon, PrivacyIcon } from "@/components/icons/glyphs";
import { IconButton } from "@/components/ui/icon-button";
import { useLoad, type Loadable } from "@/hooks/useLoad";
import { EXTRA_WIDE_SCREEN, useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/cn";
import { humanize } from "@/lib/format";

import { CallList } from "./CallList";
import { callRowId } from "./callRowId";
import { CallStatus } from "./CallStatus";
import { SummaryPanel } from "./SummaryPanel";
import { TranscriptPanel } from "./TranscriptPanel";

const loadCalls = (signal: AbortSignal) => api.listCalls(signal);

interface CallDetailProps {
  call: CallListItem;
  summary: Loadable<CallSummary> | undefined;
  onSummarize: (transcriptId: string) => void;
  onBack: () => void;
}

/** One call: its transcript, and its summary beside it or, on smaller screens, above it. */
function CallDetail({ call, summary, onSummarize, onBack }: CallDetailProps) {
  const { transcript_id: transcriptId } = call;
  const threeColumns = useMediaQuery(EXTRA_WIDE_SCREEN);
  const backButton = useRef<HTMLButtonElement>(null);
  const load = useCallback(
    (signal: AbortSignal) => api.getCall(transcriptId, signal),
    [transcriptId],
  );
  const { state: transcript, reload } = useLoad(load);

  // On a narrow screen the list is replaced by this view, so focus follows.
  // On a wide screen the button is not shown and focus stays in the list.
  useEffect(() => {
    backButton.current?.focus();
  }, []);

  const summaryPanel = (
    <SummaryPanel
      summary={summary}
      onSummarize={() => {
        onSummarize(transcriptId);
      }}
    />
  );

  return (
    <>
      <header className="shrink-0 border-b border-line px-4 pt-5 pb-[18px] sm:px-8 sm:pt-6">
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2">
          <IconButton ref={backButton} label="Back to calls" className="lg:hidden" onClick={onBack}>
            <BackIcon />
          </IconButton>
          <h2 className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3.5">
            <span className="font-mono text-read font-semibold text-ink-2 sm:text-title">
              {transcriptId}
            </span>
            <span className="font-display text-title font-bold tracking-[-0.02em] break-words text-ink sm:text-view">
              {humanize(call.category)}
            </span>
          </h2>
          <CallStatus resolution={call.resolution} />
        </div>
        <p className="mt-2.5 flex gap-2 text-meta text-ink-2">
          <PrivacyIcon size={16} className="mt-0.5" />
          Personal details were replaced with placeholders before this was saved.
        </p>
      </header>

      <div className="scroll-area flex min-h-0 flex-1 flex-col xl:flex-row xl:overflow-hidden">
        {!threeColumns && (
          <div className="shrink-0 border-b border-line bg-sunken px-4 py-5 sm:px-8">
            {summaryPanel}
          </div>
        )}
        <div className="min-w-0 flex-1 xl:scroll-area">
          <TranscriptPanel transcript={transcript} onRetry={reload} />
        </div>
        {threeColumns && (
          // The copilot's side rail, on the sunken tone.
          <aside className="scroll-area w-[25.25rem] shrink-0 border-l border-line bg-sunken p-6">
            {summaryPanel}
          </aside>
        )}
      </div>
    </>
  );
}

function NothingSelected() {
  return (
    <div className="px-8 pt-16">
      <CallsIcon size={32} className="text-ink-3" />
      <p className="mt-4 font-display text-title font-bold tracking-[-0.01em] text-ink">
        Choose a call to read it
      </p>
      <p className="mt-2 max-w-sm text-ink-2">
        Each transcript can be summarized: what the call was about, the customer&apos;s mood and the
        next step.
      </p>
    </div>
  );
}

/**
 * The Calls view: the list of calls, the transcript of the chosen one and its
 * summary. On a narrow screen the list and the call take turns.
 */
export function CallsView() {
  const { state: calls, reload } = useLoad(loadCalls);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<Record<string, Loadable<CallSummary>>>({});

  const summarize = useCallback((transcriptId: string) => {
    const store = (summary: Loadable<CallSummary>) => {
      setSummaries((current) => ({ ...current, [transcriptId]: summary }));
    };
    store({ status: "loading" });
    api.summarizeCall(transcriptId).then(
      (data) => {
        store({ status: "ready", data });
      },
      (error: unknown) => {
        store({ status: "error", message: errorMessage(error) });
      },
    );
  }, []);

  const back = () => {
    const returnTo = selectedId;
    // The list has to be on screen again before one of its rows can take focus.
    flushSync(() => {
      setSelectedId(null);
    });
    if (returnTo !== null) {
      document.getElementById(callRowId(returnTo))?.focus();
    }
  };

  const selected =
    calls.status === "ready"
      ? (calls.data.find((call) => call.transcript_id === selectedId) ?? null)
      : null;

  return (
    <div className="flex h-full min-h-0">
      <h1 className="sr-only">Calls</h1>
      <div
        className={cn(
          "w-full shrink-0 flex-col border-r border-line bg-surface lg:flex lg:w-[22rem] xl:w-[24.25rem]",
          selected ? "hidden" : "flex",
        )}
      >
        <CallList calls={calls} selectedId={selectedId} onSelect={setSelectedId} onRetry={reload} />
      </div>
      <section
        aria-label="Call"
        className={cn("min-w-0 flex-1 flex-col lg:flex", selected ? "flex" : "hidden")}
      >
        {selected ? (
          <CallDetail
            key={selected.transcript_id}
            call={selected}
            summary={summaries[selected.transcript_id]}
            onSummarize={summarize}
            onBack={back}
          />
        ) : (
          <NothingSelected />
        )}
      </section>
    </div>
  );
}
