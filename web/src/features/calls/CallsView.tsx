import { ArrowLeft, PhoneCall } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { api, errorMessage } from "@/api/client";
import type { CallListItem, CallSummary } from "@/api/types";
import { IconButton } from "@/components/ui/icon-button";
import { useLoad, type Loadable } from "@/hooks/useLoad";
import { EXTRA_WIDE_SCREEN, useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/cn";
import { humanize } from "@/lib/format";

import { CallList } from "./CallList";
import { callRowId } from "./callRowId";
import { ResolutionBadge } from "./ResolutionBadge";
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
      <header className="flex shrink-0 items-center gap-2 border-b bg-surface px-4 py-3 sm:px-6">
        <IconButton ref={backButton} label="Back to calls" className="-ml-2 lg:hidden" onClick={onBack}>
          <ArrowLeft aria-hidden="true" />
        </IconButton>
        <h2 className="flex min-w-0 flex-1 items-baseline gap-2.5 text-base font-semibold text-fg">
          <span className="font-mono text-[0.9375rem]">{transcriptId}</span>
          <span className="truncate font-normal text-fg-muted">{humanize(call.category)}</span>
        </h2>
        <ResolutionBadge resolution={call.resolution} />
      </header>

      <div className="scroll-area flex min-h-0 flex-1 flex-col xl:flex-row xl:overflow-hidden">
        {!threeColumns && (
          <div className="shrink-0 border-b bg-surface px-4 py-4 sm:px-6">{summaryPanel}</div>
        )}
        <div className="min-w-0 flex-1 xl:scroll-area">
          <TranscriptPanel transcript={transcript} onRetry={reload} />
        </div>
        {threeColumns && (
          <aside className="scroll-area w-[24rem] shrink-0 border-l bg-surface px-6 py-5">
            {summaryPanel}
          </aside>
        )}
      </div>
    </>
  );
}

function NothingSelected() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <span
        aria-hidden="true"
        className="flex size-12 items-center justify-center rounded-xl bg-surface-muted text-fg-subtle"
      >
        <PhoneCall className="size-5" />
      </span>
      <p className="mt-4 text-lg font-medium text-fg">Choose a call to read it</p>
      <p className="mt-1.5 max-w-sm text-[0.9375rem] leading-relaxed text-fg-muted">
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
          "w-full shrink-0 flex-col border-r bg-surface lg:flex lg:w-[21rem]",
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
