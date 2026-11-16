import type { ReactNode } from "react";

import { api, USE_MOCK } from "@/api/client";
import type { Meta } from "@/api/types";
import { StatusLabel } from "@/components/icons/StatusStamp";
import { SignalBars } from "@/components/shared/SignalBars";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useLoad, type Loadable } from "@/hooks/useLoad";

const loadHealth = (signal: AbortSignal) => api.getHealth(signal);

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-line py-2 first:border-t-0">
      <dt className="shrink-0 text-meta text-ink-2">{label}</dt>
      <dd className="min-w-0 text-right text-meta font-semibold break-words text-ink">
        {children}
      </dd>
    </div>
  );
}

/** A code or a readout, never a word: set in mono. */
function Code({ children }: { children: ReactNode }) {
  return <span className="font-mono font-semibold">{children}</span>;
}

/** Asks the server whether it is up. Mounted only while the popover is open. */
function ServiceRow() {
  const { state } = useLoad(loadHealth);
  return (
    <Row label="Service">
      {state.status === "loading" && <span className="font-normal text-ink-3">Checking</span>}
      {state.status === "ready" &&
        (state.data.status === "ok" ? (
          <StatusLabel status="ok">Responding</StatusLabel>
        ) : (
          <StatusLabel status="warning">{state.data.status}</StatusLabel>
        ))}
      {state.status === "error" && <StatusLabel status="blocked">Not responding</StatusLabel>}
    </Row>
  );
}

export interface RunningDetailsProps {
  meta: Loadable<Meta>;
}

/** The content of the "What's running" popover: a title and one row per setting. */
export function RunningDetails({ meta }: RunningDetailsProps) {
  return (
    <>
      <h2 className="display-title">What&apos;s running</h2>
      {USE_MOCK && (
        <p className="mt-3 border border-dashed border-line-strong px-2 py-1 text-label leading-snug font-semibold text-ink-2">
          {meta.status === "ready" && meta.data.recorded
            ? `Recorded answers. Every answer here was produced by the live copilot on ${meta.data.recorded.at.slice(0, 10)}, at commit ${meta.data.recorded.git_sha.slice(0, 7)}, and is replayed by this page. Nothing you type is sent anywhere.`
            : "Recorded answers. This page replays what the live copilot returned. Nothing you type is sent anywhere."}
        </p>
      )}
      <div className="mt-2">
        {meta.status === "ready" && (
          <dl>
            <Row label="Model">
              <Code>{meta.data.model}</Code>
            </Row>
            <Row label="Prompt version">
              <Code>{meta.data.prompt_version}</Code>
            </Row>
            <Row label="Search">
              <span className="inline-flex flex-wrap justify-end gap-x-3 gap-y-1">
                <span>
                  <span className="font-normal text-ink-2">chunks </span>
                  <Code>{meta.data.search.chunk_config}</Code>
                </span>
                <span>
                  <span className="font-normal text-ink-2">query </span>
                  <Code>{meta.data.search.query_type}</Code>
                </span>
                <span>
                  <span className="font-normal text-ink-2">top </span>
                  <Code>{meta.data.search.top_k}</Code>
                </span>
              </span>
            </Row>
            <Row label="Tracing">
              {meta.data.tracing ? (
                <StatusLabel status="ok">On</StatusLabel>
              ) : (
                <span className="text-ink-2">Off</span>
              )}
            </Row>
            <ServiceRow />
          </dl>
        )}
        {meta.status === "loading" && (
          <div className="grid gap-3 py-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        )}
        {meta.status === "error" && (
          <p className="py-2 text-meta leading-relaxed text-ink-2">{meta.message}</p>
        )}
      </div>
    </>
  );
}

export interface RunningPopoverProps {
  meta: Loadable<Meta>;
}

/** What is behind the answers: the model, the prompt, the search setting and tracing. */
export function RunningPopover({ meta }: RunningPopoverProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="quiet" className="h-9 px-2 sm:h-10 xl:px-3" aria-label="What's running">
          <SignalBars level={4} size="sm" />
          <span className="hidden xl:inline">What&apos;s running</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent aria-label="What's running">
        <RunningDetails meta={meta} />
      </PopoverContent>
    </Popover>
  );
}
