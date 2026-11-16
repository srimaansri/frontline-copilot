import type { ReactNode } from "react";

import {
  CallList,
  CallRow,
  FlaggedFilter,
  ResolutionFilter,
  SearchField,
  type CallFilter,
} from "@/features/calls/CallList";
import { CallHeader, NothingSelected } from "@/features/calls/CallsView";
import { FindingsPanel } from "@/features/calls/FindingsPanel";
import { SummaryPanel } from "@/features/calls/SummaryPanel";
import { TranscriptPanel } from "@/features/calls/TranscriptPanel";
import type { WrapUpState } from "@/features/calls/useWrapUps";
import { formFrom } from "@/features/calls/wrapUpForm";
import { WrapUpPanel } from "@/features/calls/WrapUpPanel";

import {
  CALL_COUNTS,
  CALL_ROWS,
  ERROR_MESSAGE,
  FINDINGS,
  FINDINGS_ARE_RECORDED,
  FIRST_CALL,
  FLAGGED_CALL_ROW,
  FLAGGED_COUNT,
  FLAGGED_TRANSCRIPT,
  NO_FINDINGS,
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
      note="One row per call, with each of the three endings. The selected row takes the cobalt tint with an ink outline, so the status colours stay legible. A call the rule check fired on carries a flag, which is not a status shape: the shapes say how a call ended."
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
      <Row label="flagged by the rule check">
        <ListColumn>
          <ul className="border-b border-line">
            <CallRow call={FLAGGED_CALL_ROW} selected={false} onSelect={noop} />
          </ul>
        </ListColumn>
      </Row>
      <Row label="flagged: hover">
        <ListColumn>
          <Force state="hover">
            <ul className="border-b border-line">
              <CallRow call={FLAGGED_CALL_ROW} selected={false} onSelect={noop} />
            </ul>
          </Force>
        </ListColumn>
      </Row>
      <Row label="flagged and selected">
        <ListColumn>
          <ul className="border-b border-line">
            <CallRow call={FLAGGED_CALL_ROW} selected onSelect={noop} />
          </ul>
        </ListColumn>
      </Row>
    </GallerySection>
  );
}

function FlaggedSpecimen({
  on = false,
  count = FLAGGED_COUNT || 1,
  checked = true,
}: {
  on?: boolean;
  count?: number | null;
  checked?: boolean;
}) {
  return (
    <div className="w-full max-w-88 bg-surface">
      <FlaggedFilter on={on} onChange={noop} count={count} checked={checked} />
    </div>
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
      note="Four filters with their counts. The one that is on is filled with ink, and its status shape becomes a plain silhouette. Under them, a switch that keeps only the calls the rule check flagged; it works with the four, not in place of them."
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
      <Row label="flagged: off">
        <FlaggedSpecimen />
      </Row>
      <Row label="flagged: on">
        <FlaggedSpecimen on />
      </Row>
      <Row label="flagged: hover">
        <Force state="hover">
          <FlaggedSpecimen />
        </Force>
      </Row>
      <Row label="flagged: pressed">
        <Force state="pressed">
          <FlaggedSpecimen />
        </Force>
      </Row>
      <Row label="flagged: focus">
        <Force state="focus">
          <FlaggedSpecimen />
        </Force>
      </Row>
      <Row label="flagged: while the calls load">
        <FlaggedSpecimen count={null} />
      </Row>
      <Row label="no rule check has run">
        <FlaggedSpecimen count={0} checked={false} />
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
      note="The agent on the left on the surface, the customer on the right on the sunken tone. Placeholders are redaction bars. A turn the rule check points at is outlined in the colour of 'needs a person' and says which rule and which turn."
    >
      <Row label="a call">
        <div className="max-w-3xl">
          <TranscriptPanel transcript={{ status: "ready", data: TRANSCRIPT }} onRetry={noop} />
        </div>
      </Row>
      <Row label="turns the rule check points at">
        <div className="max-w-3xl">
          <TranscriptPanel
            transcript={{ status: "ready", data: FLAGGED_TRANSCRIPT }}
            onRetry={noop}
            findings={FINDINGS.findings}
          />
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

export function RuleCheckSection() {
  const source = FINDINGS_ARE_RECORDED
    ? "The findings are the live rule check's, from the recording."
    : "The call shown was written for the gallery, and its findings are what the rule check returns for it: the recording has no rule check yet.";
  const turnCount = FLAGGED_TRANSCRIPT.turns.length;
  return (
    <GallerySection
      id="rule-check"
      title="Rule check"
      note={`What fixed rules found in a call, over its transcript. Soft-square corners: it is not something Cue wrote. With a finding it takes the tint of the hand-off banner, because a person should read the turn. It always says that it is a rule check and that it misses things. ${source}`}
    >
      <Row label="findings">
        <div className="max-w-3xl">
          <FindingsPanel
            findings={{ status: "ready", data: FINDINGS }}
            turnCount={turnCount}
            onGoToTurn={noop}
            onRetry={noop}
          />
        </div>
      </Row>
      <Row label="go to turn: hover">
        <div className="max-w-3xl">
          <Force state="hover" nth={0}>
            <FindingsPanel
              findings={{ status: "ready", data: FINDINGS }}
              turnCount={turnCount}
              onGoToTurn={noop}
              onRetry={noop}
            />
          </Force>
        </div>
      </Row>
      <Row label="go to turn: focus">
        <div className="max-w-3xl">
          <Force state="focus" nth={0}>
            <FindingsPanel
              findings={{ status: "ready", data: FINDINGS }}
              turnCount={turnCount}
              onGoToTurn={noop}
              onRetry={noop}
            />
          </Force>
        </div>
      </Row>
      <Row label="no rule fired">
        <div className="max-w-3xl">
          <FindingsPanel
            findings={{ status: "ready", data: NO_FINDINGS }}
            turnCount={TRANSCRIPT.turns.length}
            onGoToTurn={noop}
            onRetry={noop}
          />
        </div>
      </Row>
      <Row label="a finding past the end of the transcript on show">
        <div className="max-w-3xl">
          <FindingsPanel
            findings={{ status: "ready", data: FINDINGS }}
            turnCount={1}
            onGoToTurn={noop}
            onRetry={noop}
          />
        </div>
      </Row>
      <Row label="narrow, as on a phone">
        <div className="max-w-80">
          <FindingsPanel
            findings={{ status: "ready", data: FINDINGS }}
            turnCount={turnCount}
            onGoToTurn={noop}
            onRetry={noop}
          />
        </div>
      </Row>
      <Row label="checking">
        <div className="max-w-3xl">
          <FindingsPanel
            findings={{ status: "loading" }}
            turnCount={null}
            onGoToTurn={noop}
            onRetry={noop}
          />
        </div>
      </Row>
      <Row label="the demo has no recorded rule check">
        <div className="max-w-3xl">
          <FindingsPanel
            findings={{
              status: "error",
              message:
                "The demo has no recorded rule check: its recording was made before the check was added. In the live app, the rules read the call when you open it.",
            }}
            turnCount={null}
            onGoToTurn={noop}
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
    <WrapUpPanel
      state={state}
      onDraft={noop}
      onChange={noop}
      onSave={noop}
      onReopen={noop}
      onRecheck={noop}
    />
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
      <Row label="looking for a saved wrap-up, as a call opens" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={{ status: "checking" }} />
      </Row>
      <Row label="saved earlier, read back when the call is opened" on="sunken" className="max-w-100">
        <WrapUpSpecimen
          state={{
            status: "saved",
            draft: WRAP_UP,
            // When it was saved comes with a record read back from the server.
            saved: { ...SAVED_WRAP_UP, saved_at: "2026-11-14T16:42:05Z" },
          }}
        />
      </Row>
      <Row label="could not find out whether one was saved" on="sunken" className="max-w-100">
        <WrapUpSpecimen state={{ status: "unknown" }} />
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
