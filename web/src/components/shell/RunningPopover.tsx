import { Activity } from "lucide-react";
import type { ReactNode } from "react";

import { api, USE_MOCK } from "@/api/client";
import type { Meta } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useLoad, type Loadable } from "@/hooks/useLoad";
import { cn } from "@/lib/cn";

const loadHealth = (signal: AbortSignal) => api.getHealth(signal);

type DotTone = "on" | "off" | "bad";

const DOT_CLASSES: Record<DotTone, string> = {
  on: "bg-ok",
  off: "bg-fg-subtle",
  bad: "bg-blocked",
};

function StatusDot({ tone }: { tone: DotTone }) {
  return <span aria-hidden="true" className={cn("size-2 rounded-full", DOT_CLASSES[tone])} />;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <dt className="shrink-0 text-sm text-fg-subtle">{label}</dt>
      <dd className="min-w-0 text-right text-sm font-medium break-words text-fg">{children}</dd>
    </div>
  );
}

function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[0.8125rem]">{children}</span>;
}

/** Asks the server whether it is up. Mounted only while the popover is open. */
function ServiceRow() {
  const { state } = useLoad(loadHealth);
  return (
    <Row label="Service">
      {state.status === "loading" && <span className="text-fg-subtle">Checking</span>}
      {state.status === "ready" && (
        <span className="inline-flex items-center gap-2">
          <StatusDot tone={state.data.status === "ok" ? "on" : "bad"} />
          {state.data.status === "ok" ? "Responding" : state.data.status}
        </span>
      )}
      {state.status === "error" && (
        <span className="inline-flex items-center gap-2">
          <StatusDot tone="bad" />
          Not responding
        </span>
      )}
    </Row>
  );
}

function Details({ meta }: { meta: Meta }) {
  return (
    <dl className="divide-y">
      <Row label="Model">
        <Mono>{meta.model}</Mono>
      </Row>
      <Row label="Prompt version">
        <Mono>{meta.prompt_version}</Mono>
      </Row>
      <Row label="Search">
        <span className="inline-flex flex-wrap justify-end gap-x-3 gap-y-1">
          <span>
            <span className="font-normal text-fg-subtle">chunks </span>
            <Mono>{meta.search.chunk_config}</Mono>
          </span>
          <span>
            <span className="font-normal text-fg-subtle">query </span>
            <Mono>{meta.search.query_type}</Mono>
          </span>
          <span>
            <span className="font-normal text-fg-subtle">top </span>
            <Mono>{meta.search.top_k}</Mono>
          </span>
        </span>
      </Row>
      <Row label="Tracing">
        <span className="inline-flex items-center gap-2">
          <StatusDot tone={meta.tracing ? "on" : "off"} />
          {meta.tracing ? "On" : "Off"}
        </span>
      </Row>
      <ServiceRow />
    </dl>
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
        <Button variant="ghost" size="sm" className="h-9 px-2.5" aria-label="What's running">
          <Activity aria-hidden="true" />
          <span className="hidden lg:inline">What&apos;s running</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent aria-label="What's running">
        <h2 className="text-sm font-semibold text-fg">What&apos;s running</h2>
        {USE_MOCK && (
          <p className="mt-2 rounded-md bg-warning-soft px-3 py-2 text-[0.8125rem] leading-snug text-warning">
            Mock mode. These values and every answer come from built-in fixtures, not from a
            server.
          </p>
        )}
        <div className="mt-1.5">
          {meta.status === "ready" && <Details meta={meta.data} />}
          {meta.status === "loading" && (
            <div className="space-y-3 py-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-4/5" />
              <Skeleton className="h-4 w-3/5" />
            </div>
          )}
          {meta.status === "error" && (
            <p className="py-2 text-sm leading-relaxed text-fg-muted">{meta.message}</p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
