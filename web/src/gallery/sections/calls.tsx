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
import type { WrapUpState } from "@/features/calls/useWrapUps";
import { formFrom } from "@/features/calls/wrapUpForm";
import { WrapUpPanel } from "@/features/calls/WrapUpPanel";

import {
  CALL_COUNTS,
  CALL_ROWS,
  ERROR_MESSAGE,
  FIRST_CALL,
  noop,
  SAVED_WRAP_UP,
  summaryWith,
  TRANSCRIPT,
  WRAP_UP,
  WRAP_UP_IS_RECORDED,
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

const WRAP_UP_FORM = formFrom(WRAP_UP);

/** A draft the agent is working on, with whatever the specimen changes. */
function draftState(changes: Partial<Extract<WrapUpState, { status: "draft" }>> = {}): WrapUpState {
  return {
    status: "draft",
    draft: WRAP_UP,
    start: WRAP_UP_FORM,
    startedFrom: "copilot",
    form: WRAP_UP_FORM,
    saving: false,
    problem: null,
    ...changes,
  };
}

function WrapUpSpecimen({ state }: { state: WrapUpState | undefined }) {
  return (
    <WrapUpPanel state={state} onDraft={noop} onChange={noop} onSave={noop} onReopen={noop} />
  );
}

export function WrapUpSection() {
  const source = WRAP_UP_IS_RECORDED
    ? "The draft is the live copilot's, from the recording."
    : "The draft shown was written for the gallery: the recording has no wrap-up yet.";
  return (
    <GallerySection
      id="wrap-up"
      title="Wrap-up"
      note={`After-call work: the copilot drafts the record, the agent checks and saves it. The form keeps soft-square corners, because it is the agent's to act on. Each part says whose words are in it. ${source}`}
    >
      <Row label="before it is asked for" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={undefined} />
      </Row>
      <Row label="button: hover" on="sunken" className="max-w-100">
        <Force state="hover" target="button">
          <WrapUpSpecimen state={undefined} />
        </Force>
      </Row>
      <Row label="drafting" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={{ status: "loading" }} />
      </Row>
      <Row label="the copilot's draft, not saved" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={draftState()} />
      </Row>
      <Row label="notes focused" on="sunken" className="max-w-100">
        <Force state="focus" target=".field" nth={2}>
          <WrapUpSpecimen state={draftState()} />
        </Force>
      </Row>
      <Row label="changed by the agent" on="sunken" className="max-w-100">
        <WrapUpSpecimen
          state={draftState({
            form: {
              ...WRAP_UP_FORM,
              disposition: "unresolved",
              notes: `${WRAP_UP_FORM.notes}\nThe customer asked for a call back after 5 pm.`,
              owner: "agent",
              action: "Call the customer back after 5 pm.",
            },
          })}
        />
      </Row>
      <Row label="nothing left to do, nothing promised" on="sunken" className="max-w-100">
        <WrapUpSpecimen
          state={draftState({
            form: { ...WRAP_UP_FORM, disposition: "resolved", promises: "", owner: "none", action: "" },
          })}
        />
      </Row>
      <Row label="cannot be saved yet" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={draftState({ form: { ...WRAP_UP_FORM, notes: "" } })} />
      </Row>
      <Row label="saving" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={draftState({ saving: true })} />
      </Row>
      <Row label="the save failed" on="sunken" className="max-w-100">
        <WrapUpSpecimen
          state={draftState({
            problem:
              "The wrap-up could not be saved. Your changes are still here. Please try again.",
          })}
        />
      </Row>
      <Row label="saved" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={{ status: "saved", draft: WRAP_UP, saved: SAVED_WRAP_UP }} />
      </Row>
      <Row label="saved, nothing left to do" on="sunken" className="max-w-100">
        <WrapUpSpecimen
          state={{
            status: "saved",
            draft: WRAP_UP,
            saved: {
              ...SAVED_WRAP_UP,
              disposition: "resolved",
              promises: [],
              follow_up: null,
              sentiment: "positive",
            },
          }}
        />
      </Row>
      <Row label="changing a saved wrap-up" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={draftState({ startedFrom: "saved" })} />
      </Row>
      <Row label="the draft could not be made" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={{ status: "error", message: ERROR_MESSAGE }} />
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
