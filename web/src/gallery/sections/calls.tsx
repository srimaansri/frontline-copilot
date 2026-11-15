import type { ReactNode } from "react";

import {
  CallList,
  CallRow,
  ResolutionFilter,
  SearchField,
  type CallFilter,
} from "@/features/calls/CallList";
import { CallHeader, NothingSelected } from "@/features/calls/CallsView";
import { SummaryPanel } from "@/features/calls/SummaryPanel";
import { TranscriptPanel } from "@/features/calls/TranscriptPanel";

import {
  CALL_COUNTS,
  CALL_ROWS,
  ERROR_MESSAGE,
  FIRST_CALL,
  noop,
  summaryWith,
  TRANSCRIPT,
} from "../fixtures";
import { Force, GallerySection, Row } from "../kit";

/** The list column of the Calls view, at its real width and on its real surface. */
function ListColumn({ children }: { children: ReactNode }) {
  return <div className="w-full max-w-96 border border-line bg-surface">{children}</div>;
}

function Rows({ selectedId = null }: { selectedId?: string | null }) {
  return (
    <ul className="border-b border-line">
      {CALL_ROWS.map((call) => (
        <CallRow
          key={call.transcript_id}
          call={call}
          selected={call.transcript_id === selectedId}
          onSelect={noop}
        />
      ))}
    </ul>
  );
}

export function CallRowsSection() {
  return (
    <GallerySection
      id="call-rows"
      title="Calls list row"
      note="One row per call, with each of the three endings. The selected row takes the cobalt tint with an ink outline, so the status colours stay legible."
    >
      <Row label="rest: resolved, escalated, unresolved">
        <ListColumn>
          <Rows />
        </ListColumn>
      </Row>
      <Row label="1 hover · 2 pressed · 3 focus">
        <ListColumn>
          <Force state="hover" nth={0}>
            <Force state="pressed" nth={1}>
              <Force state="focus" nth={2}>
                <Rows />
              </Force>
            </Force>
          </Force>
        </ListColumn>
      </Row>
      {CALL_ROWS.map((call) => (
        <Row key={call.transcript_id} label={`selected: ${call.resolution}`}>
          <ListColumn>
            <Rows selectedId={call.transcript_id} />
          </ListColumn>
        </Row>
      ))}
    </GallerySection>
  );
}

function FilterSpecimen({ value, loaded = true }: { value: CallFilter; loaded?: boolean }) {
  return (
    <div className="w-full max-w-88 bg-surface">
      <ResolutionFilter value={value} onChange={noop} counts={loaded ? CALL_COUNTS : null} />
    </div>
  );
}

export function FiltersSection() {
  return (
    <GallerySection
      id="filters"
      title="Filter chips"
      note="Four filters with their counts. The one that is on is filled with ink, and its status shape becomes a plain silhouette."
    >
      <Row label="All is on">
        <FilterSpecimen value="all" />
      </Row>
      <Row label="Resolved is on">
        <FilterSpecimen value="resolved" />
      </Row>
      <Row label="Escalated is on">
        <FilterSpecimen value="escalated" />
      </Row>
      <Row label="Unresolved is on">
        <FilterSpecimen value="unresolved" />
      </Row>
      <Row label="2 hover · 3 pressed · 4 focus">
        <Force state="hover" nth={1}>
          <Force state="pressed" nth={2}>
            <Force state="focus" nth={3}>
              <FilterSpecimen value="all" />
            </Force>
          </Force>
        </Force>
      </Row>
      <Row label="while the calls load">
        <FilterSpecimen value="all" loaded={false} />
      </Row>
    </GallerySection>
  );
}

function SearchSpecimen({ value = "" }: { value?: string }) {
  return (
    <div className="w-full max-w-88">
      <SearchField
        value={value}
        onChange={noop}
        label="Search calls"
        placeholder="Search by id or category"
      />
    </div>
  );
}

export function SearchSection() {
  return (
    <GallerySection
      id="search"
      title="Search field"
      note="The same field as the question box: one cobalt ring on focus."
    >
      <Row label="empty" on="surface">
        <SearchSpecimen />
      </Row>
      <Row label="hover" on="surface">
        <Force state="hover" target=".field">
          <SearchSpecimen />
        </Force>
      </Row>
      <Row label="focused" on="surface">
        <Force state="focus" target=".field">
          <SearchSpecimen />
        </Force>
      </Row>
      <Row label="with text" on="surface">
        <SearchSpecimen value="billing" />
      </Row>
      <Row label="clear under the pointer" on="surface">
        <Force state="hover" target="button">
          <SearchSpecimen value="billing" />
        </Force>
      </Row>
      <Row label="clear pressed" on="surface">
        <Force state="pressed" target="button">
          <SearchSpecimen value="billing" />
        </Force>
      </Row>
    </GallerySection>
  );
}

export function TranscriptSection() {
  return (
    <GallerySection
      id="transcript"
      title="Transcript bubbles"
      note="The agent on the left on the surface, the customer on the right on the sunken tone. Placeholders are redaction bars."
    >
      <Row label="a call">
        <div className="max-w-3xl">
          <TranscriptPanel transcript={{ status: "ready", data: TRANSCRIPT }} onRetry={noop} />
        </div>
      </Row>
      <Row label="loading">
        <div className="max-w-3xl">
          <TranscriptPanel transcript={{ status: "loading" }} onRetry={noop} />
        </div>
      </Row>
      <Row label="error">
        <div className="max-w-3xl">
          <TranscriptPanel
            transcript={{
              status: "error",
              message: "No transcript was found with the id T0003.",
            }}
            onRetry={noop}
          />
        </div>
      </Row>
    </GallerySection>
  );
}

export function SummarySection() {
  return (
    <GallerySection
      id="summary"
      title="Summary card"
      note="What the copilot wrote about a call, on the cut-corner card, with each mood."
    >
      <Row label="before it is asked for" on="sunken" className="max-w-100">
        <SummaryPanel summary={undefined} onSummarize={noop} />
      </Row>
      <Row label="summarizing" on="sunken" className="max-w-100">
        <SummaryPanel summary={{ status: "loading" }} onSummarize={noop} />
      </Row>
      {(["positive", "neutral", "negative"] as const).map((mood) => (
        <Row key={mood} label={`mood: ${mood}`} on="sunken" className="max-w-100">
          <SummaryPanel summary={{ status: "ready", data: summaryWith(mood) }} onSummarize={noop} />
        </Row>
      ))}
      <Row label="error" on="sunken" className="max-w-100">
        <SummaryPanel
          summary={{ status: "error", message: ERROR_MESSAGE }}
          onSummarize={noop}
        />
      </Row>
    </GallerySection>
  );
}

export function CallsStatesSection() {
  return (
    <GallerySection
      id="calls-states"
      title="Calls view: empty and error states"
      note="What the Calls view shows before a call is chosen, while the list loads, and when it cannot be loaded."
    >
      <Row label="no call chosen">
        <NothingSelected />
      </Row>
      <Row label="call header">
        <div className="max-w-3xl">
          <CallHeader call={FIRST_CALL} />
        </div>
      </Row>
      <Row label="list loading">
        <div className="h-96 w-full max-w-96 border border-line bg-surface">
          <CallList calls={{ status: "loading" }} selectedId={null} onSelect={noop} onRetry={noop} />
        </div>
      </Row>
      <Row label="list error">
        <div className="h-80 w-full max-w-96 border border-line bg-surface">
          <CallList
            calls={{
              status: "error",
              message: "The service could not be reached. Check the connection and try again.",
            }}
            selectedId={null}
            onSelect={noop}
            onRetry={noop}
          />
        </div>
      </Row>
      <Row label="no calls">
        <div className="h-80 w-full max-w-96 border border-line bg-surface">
          <CallList
            calls={{ status: "ready", data: [] }}
            selectedId={null}
            onSelect={noop}
            onRetry={noop}
          />
        </div>
      </Row>
    </GallerySection>
  );
}
