import type { ReactNode } from "react";

import type { AssistState } from "@/api/types";
import { PlayIcon } from "@/components/icons/glyphs";
import { Button } from "@/components/ui/button";
import { AssistPanel } from "@/features/calls/AssistPanel";
import {
  CallList,
  CallRow,
  ResolutionFilter,
  SearchField,
  type CallFilter,
} from "@/features/calls/CallList";
import { CallHeader, NothingSelected } from "@/features/calls/CallsView";
import { ReplayControls } from "@/features/calls/ReplayControls";
import { SummaryPanel } from "@/features/calls/SummaryPanel";
import { TranscriptPanel, Turns } from "@/features/calls/TranscriptPanel";
import type { WrapUpState } from "@/features/calls/useWrapUps";
import { formFrom } from "@/features/calls/wrapUpForm";
import { WrapUpPanel } from "@/features/calls/WrapUpPanel";

import {
  ASSIST_A_TURN_LATER,
  ASSIST_AT_THE_ISSUE,
  ASSIST_IS_RECORDED,
  ASSIST_NOTHING_YET,
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

function ControlsSpecimen({ turn, playing = false }: { turn: number; playing?: boolean }) {
  return (
    <div className="max-w-3xl border border-line">
      <ReplayControls
        turn={turn}
        total={TRANSCRIPT.turns.length}
        playing={playing}
        onPlay={noop}
        onPause={noop}
        onNext={noop}
        onRestart={noop}
      />
    </div>
  );
}

/** The switch in the call header, as the Calls view draws it: ink while the replay is on. */
function ReplaySwitch({ on }: { on: boolean }) {
  return (
    <Button variant={on ? "on" : "outline"} size="sm" aria-pressed={on}>
      <PlayIcon size={16} />
      Replay with assist
    </Button>
  );
}

export function ReplaySection() {
  return (
    <GallerySection
      id="replay"
      title="Replay"
      note="A call played back one turn at a time. Play is the one cobalt fill; the place in the call is a readout, not a bar. In a replay every turn carries its number, so it can be matched to the assist panel."
    >
      <Row label="stopped at the first turn">
        <ControlsSpecimen turn={0} />
      </Row>
      <Row label="playing">
        <ControlsSpecimen turn={5} playing />
      </Row>
      <Row label="paused part way">
        <ControlsSpecimen turn={5} />
      </Row>
      <Row label="at the last turn">
        <ControlsSpecimen turn={TRANSCRIPT.turns.length - 1} />
      </Row>
      <Row label="1 hover · 2 pressed · 3 focus">
        <Force state="hover" nth={0}>
          <Force state="pressed" nth={1}>
            <Force state="focus" nth={2}>
              <ControlsSpecimen turn={5} />
            </Force>
          </Force>
        </Force>
      </Row>
      <Row label="the call so far, six turns in">
        <div className="max-w-3xl">
          <Turns transcript={TRANSCRIPT} upTo={5} />
        </div>
      </Row>
      <Row label="call header: the replay is off">
        <div className="max-w-3xl">
          <CallHeader call={FIRST_CALL} action={<ReplaySwitch on={false} />} />
        </div>
      </Row>
      <Row label="call header: the replay is on">
        <div className="max-w-3xl">
          <CallHeader call={FIRST_CALL} compact action={<ReplaySwitch on />} />
        </div>
      </Row>
    </GallerySection>
  );
}

interface AssistSpecimenProps {
  state: AssistState | null;
  pending?: boolean;
  problem?: string | null;
  retry?: boolean;
  /** The turn on show, when it is ahead of the newest state there is. */
  turn?: number;
}

function AssistSpecimen({ state, pending = false, problem = null, retry = false, turn }: AssistSpecimenProps) {
  return (
    <AssistPanel
      state={state}
      turn={turn ?? state?.turn ?? 0}
      total={TRANSCRIPT.turns.length}
      pending={pending}
      problem={problem}
      onRetry={retry ? noop : undefined}
    />
  );
}

/** A state of the specimen call with whatever one row changes. */
function assistWith(changes: Partial<AssistState>): AssistState {
  return { ...ASSIST_A_TURN_LATER, ...changes };
}

export function AssistSection() {
  const source = ASSIST_IS_RECORDED
    ? "The article and the next step are the live copilot's, from the recording."
    : "The article and the next step shown were written for the gallery: the recording has no call assist yet.";
  const later = ASSIST_A_TURN_LATER.turn;
  return (
    <GallerySection
      id="assist"
      title="Call assist"
      note={`What the copilot keeps beside a replayed call without being asked: the identity check, reminders from the rules, a hint to hand off, a next step and the help article it was written from. Each part says at which turn it came up, and carries the notice shape at the turn it is new. The signal bars in the head are the one thing that says "working". ${source} The reminders, the hint and the problems in the rows below are written for the gallery.`}
    >
      <Row label="reading the first turn" on="sunken" className="max-w-110">
        <AssistSpecimen state={null} pending />
      </Row>
      <Row label="nothing to show yet" on="sunken" className="max-w-110">
        <AssistSpecimen state={ASSIST_NOTHING_YET} />
      </Row>
      <Row label="an article and a next step, new at this turn" on="sunken" className="max-w-110">
        <AssistSpecimen state={ASSIST_AT_THE_ISSUE} />
      </Row>
      <Row label="one turn later: nothing is new" on="sunken" className="max-w-110">
        <AssistSpecimen state={ASSIST_A_TURN_LATER} />
      </Row>
      <Row label="reading the next turn" on="sunken" className="max-w-110">
        <AssistSpecimen state={ASSIST_AT_THE_ISSUE} turn={ASSIST_AT_THE_ISSUE.turn + 1} pending />
      </Row>
      <Row label="the identity check, new at this turn" on="sunken" className="max-w-110">
        <AssistSpecimen state={assistWith({ identity_checked_at: later, changed: ["identity"] })} />
      </Row>
      <Row label="two reminders from the rules, one new" on="sunken" className="max-w-110">
        <AssistSpecimen
          state={assistWith({
            changed: ["reminder"],
            reminders: [
              {
                rule: "account_before_identity",
                title: "Account details before the identity check",
                detail:
                  "Something from the account was said or changed before the customer answered an identity question.",
                turn: later - 2,
              },
              {
                rule: "card_read_back",
                title: "A card number was read back",
                detail:
                  "A full payment card number was said aloud. The last four digits are enough to confirm a card.",
                turn: later,
              },
            ],
          })}
        />
      </Row>
      <Row label="a hint to hand off, new at this turn" on="sunken" className="max-w-110">
        <AssistSpecimen
          state={assistWith({
            identity_checked_at: later - 1,
            changed: ["hand_off"],
            hand_off: { category: "billing", team: "the billing team", turn: later },
          })}
        />
      </Row>
      <Row label="a figure that is in no source" on="sunken" className="max-w-110">
        <AssistSpecimen
          state={assistWith({
            next_step: {
              text: "You can ask for a one-time waiver of the $7 late fee.",
              since_turn: ASSIST_AT_THE_ISSUE.turn,
              unsupported: ["money"],
            },
          })}
        />
      </Row>
      <Row label="an article the model found nothing to say about" on="sunken" className="max-w-110">
        <AssistSpecimen state={assistWith({ next_step: null, step_problem: null })} />
      </Row>
      <Row label="a next step that was withheld" on="sunken" className="max-w-110">
        <AssistSpecimen
          state={assistWith({
            next_step: null,
            step_problem: "Cue wrote a next step that broke a rule, so it is not shown.",
          })}
        />
      </Row>
      <Row label="a turn could not be read" on="sunken" className="max-w-110">
        <AssistSpecimen
          state={ASSIST_AT_THE_ISSUE}
          turn={ASSIST_AT_THE_ISSUE.turn + 1}
          problem="Call assist could not read this turn just now. Please try again."
          retry
        />
      </Row>
      <Row label="the demo has no recording for this call" on="sunken" className="max-w-110">
        <AssistSpecimen
          state={null}
          problem="The demo has no recorded call assist for call T0003. It has one for these calls: T0001, T0002."
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
