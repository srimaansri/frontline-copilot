import { useRef } from "react";

import type { Step } from "@/api/types";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { RunningDetails } from "@/components/shell/RunningPopover";
import { PopoverPanel } from "@/components/ui/popover";
import { AnswerCard } from "@/features/ask/AnswerCard";
import { AnswerFooter } from "@/features/ask/AnswerFooter";
import { Composer } from "@/features/ask/Composer";
import { ExampleList } from "@/features/ask/EmptyState";
import { HandOffDraftCard } from "@/features/ask/HandOffDraftCard";
import type { FeedbackState } from "@/features/ask/FeedbackButtons";
import { ProgressHint } from "@/features/ask/ProgressHint";
import { QuestionBubble } from "@/features/ask/QuestionBubble";
import { SourceList } from "@/features/ask/SourceList";
import { RouteLegend, StepsRoute } from "@/features/ask/StepsRoute";
import type { AnsweredExchange } from "@/features/ask/useConversation";

import {
  CITED,
  decline,
  MULTI_CITED,
  ERROR_MESSAGE,
  EXAMPLES,
  HANDOFF,
  HANDOFF_DRAFT,
  HANDOFF_TICKET,
  META,
  NO_CITATIONS,
  noop,
  PLANS,
  REFUSAL,
  ROUTE_WITH_PROBLEMS,
  TOOLS,
  WAIVER,
} from "../fixtures";
import { Force, GallerySection, Row } from "../kit";

interface ComposerSpecimenProps {
  waiting?: boolean;
  initialValue?: string;
}

function ComposerSpecimen({ waiting = false, initialValue }: ComposerSpecimenProps) {
  const input = useRef<HTMLTextAreaElement>(null);
  return (
    <div className="max-w-3xl">
      <Composer inputRef={input} onSend={decline} waiting={waiting} initialValue={initialValue} />
    </div>
  );
}

const TYPED = "How much is the late payment fee, and can it be waived?";

export function ComposerSection() {
  return (
    <GallerySection
      id="composer"
      title="Question composer"
      note="The box is the field. Focus is one cobalt ring: the border turns cobalt and grows outward, with no second line."
    >
      <Row label="empty">
        <ComposerSpecimen />
      </Row>
      <Row label="hover">
        <Force state="hover" target=".field">
          <ComposerSpecimen />
        </Force>
      </Row>
      <Row label="focused">
        <Force state="focus" target=".field">
          <ComposerSpecimen />
        </Force>
      </Row>
      <Row label="typing">
        <ComposerSpecimen initialValue={TYPED} />
      </Row>
      <Row label="typing, send under the pointer">
        <Force state="hover" target="button">
          <ComposerSpecimen initialValue={TYPED} />
        </Force>
      </Row>
      <Row label="disabled while waiting">
        <ComposerSpecimen waiting initialValue="And can a payment arrangement stop it?" />
      </Row>
    </GallerySection>
  );
}

export function QuestionSection() {
  return (
    <GallerySection
      id="question"
      title="Agent question bubble"
      note="The agent's own words, on the sunken tone with soft-square corners. Removed details are underlined, and the line below shows what the copilot was given."
    >
      <Row label="plain">
        <div className="flex max-w-3xl flex-col">
          <QuestionBubble id="gallery-question-plain" question={CITED.question} processed={null} />
        </div>
      </Row>
      <Row label="details removed">
        <div className="flex max-w-3xl flex-col">
          <QuestionBubble
            id="gallery-question-redacted"
            question={HANDOFF.question}
            processed={HANDOFF.response.question_as_processed}
          />
        </div>
      </Row>
    </GallerySection>
  );
}

interface AnswerSpecimenProps {
  exchange: AnsweredExchange;
  selected?: boolean;
  activeCitation?: number | null;
}

function AnswerSpecimen({ exchange, selected = false, activeCitation = null }: AnswerSpecimenProps) {
  return (
    <div className="max-w-3xl">
      <AnswerCard
        exchange={exchange}
        tools={TOOLS}
        selected={selected}
        sidePanel
        detailsId={`${exchange.id}-details`}
        activeCitation={activeCitation}
        onCite={noop}
        onToggleDetails={noop}
      />
    </div>
  );
}

export function AnswerSection() {
  return (
    <GallerySection
      id="answer"
      title="Copilot answer card"
      note="The card with the cut corner holds only what the copilot wrote. The banner and the footer sit under it."
    >
      <Row label="cited answer">
        <AnswerSpecimen exchange={CITED} />
      </Row>
      <Row label="cited, selected, source 2 in focus">
        <AnswerSpecimen exchange={MULTI_CITED} selected activeCitation={2} />
      </Row>
      <Row label="waiver steps, as the live model wrote it">
        <AnswerSpecimen exchange={WAIVER} />
      </Row>
      <Row label="table">
        <AnswerSpecimen exchange={PLANS} />
      </Row>
      <Row label="hand-off: script line and banner">
        <AnswerSpecimen exchange={HANDOFF} />
      </Row>
      <Row label="hand-off drafted, waiting for the agent">
        <div className="max-w-3xl">
          <HandOffDraftCard draft={HANDOFF_DRAFT} />
        </div>
      </Row>
      <Row label="hand-off opened by the agent">
        <div className="max-w-3xl">
          <HandOffDraftCard draft={HANDOFF_DRAFT} initialTicket={HANDOFF_TICKET} />
        </div>
      </Row>
      <Row label="refusal">
        <AnswerSpecimen exchange={REFUSAL} />
      </Row>
      <Row label="error with retry">
        <div className="max-w-3xl">
          <ErrorNotice message={ERROR_MESSAGE} onRetry={noop} />
        </div>
      </Row>
      <Row label="pending">
        <ProgressHint
          stage={{
            stage: "tool",
            label: "Searching the help articles",
            tool: "search_kb",
            at: 0.9,
          }}
        />
      </Row>
    </GallerySection>
  );
}

interface FooterSpecimenProps {
  exchange?: AnsweredExchange;
  feedback?: FeedbackState;
  selected?: boolean;
  sidePanel?: boolean;
}

function FooterSpecimen({
  exchange = CITED,
  feedback,
  selected = false,
  sidePanel = true,
}: FooterSpecimenProps) {
  return (
    <div className="max-w-3xl">
      <AnswerFooter
        response={exchange.response}
        tools={TOOLS}
        selected={selected}
        sidePanel={sidePanel}
        detailsId="gallery-footer-details"
        onToggleDetails={noop}
        initialFeedback={feedback}
      />
    </div>
  );
}

export function AnswerFooterSection() {
  return (
    <GallerySection
      id="answer-footer"
      title="Answer footer"
      note="Tool badges, the time taken, the two feedback buttons and the button for sources and steps."
    >
      <Row label="rest">
        <FooterSpecimen />
      </Row>
      <Row label="voted, saving">
        <FooterSpecimen feedback={{ status: "saving", helpful: true }} />
      </Row>
      <Row label="saved">
        <FooterSpecimen feedback={{ status: "saved", helpful: true }} />
      </Row>
      <Row label="saved, not helpful">
        <FooterSpecimen feedback={{ status: "saved", helpful: false }} />
      </Row>
      <Row label="could not save">
        <FooterSpecimen feedback={{ status: "error", message: "Feedback could not be saved." }} />
      </Row>
      <Row label="details on show (wide)">
        <FooterSpecimen selected />
      </Row>
      <Row label="narrow, details closed">
        <FooterSpecimen sidePanel={false} />
      </Row>
      <Row label="narrow, details open">
        <FooterSpecimen sidePanel={false} selected />
      </Row>
      <Row label="no trace: no feedback buttons">
        <FooterSpecimen exchange={REFUSAL} />
      </Row>
    </GallerySection>
  );
}

const SOURCES = CITED.response.citations;

export function SourcesSection() {
  return (
    <GallerySection
      id="sources"
      title="Source card"
      note="A source opens in a new tab. The one a citation chip pointed at is outlined in ink and its chip is filled."
    >
      <Row label="rest" on="sunken" className="max-w-md">
        <SourceList citations={SOURCES} highlight={null} />
      </Row>
      <Row label="hover on the first" on="sunken" className="max-w-md">
        <Force state="hover" nth={0}>
          <SourceList citations={SOURCES} highlight={null} />
        </Force>
      </Row>
      <Row label="focus on the first" on="sunken" className="max-w-md">
        <Force state="focus" nth={0}>
          <SourceList citations={SOURCES} highlight={null} />
        </Force>
      </Row>
      <Row label="pressed on the first" on="sunken" className="max-w-md">
        <Force state="pressed" nth={0}>
          <SourceList citations={SOURCES} highlight={null} />
        </Force>
      </Row>
      <Row label="second highlighted" on="sunken" className="max-w-md">
        <SourceList citations={SOURCES} highlight={{ number: 2, tick: 0 }} />
      </Row>
      <Row label="none" on="sunken" className="max-w-md">
        <SourceList citations={NO_CITATIONS} highlight={null} />
      </Row>
    </GallerySection>
  );
}

function RouteSpecimen({ steps }: { steps: readonly Step[] }) {
  return <StepsRoute steps={steps} tools={TOOLS} />;
}

export function RouteSection() {
  return (
    <GallerySection
      id="route"
      title="Steps route"
      note="One line, a station per step. A hand-off branches at 45 degrees and runs dashed to its tag, while the main line carries on."
    >
      <Row label="all OK" on="sunken" className="max-w-md">
        <RouteSpecimen steps={WAIVER.response.steps} />
      </Row>
      <Row label="with a notice" on="sunken" className="max-w-md">
        <RouteSpecimen steps={CITED.response.steps} />
      </Row>
      <Row label="hand-off: branch and tag" on="sunken" className="max-w-md">
        <RouteSpecimen steps={HANDOFF.response.steps} />
      </Row>
      <Row label="a warning and a blocked step" on="sunken" className="max-w-md">
        <RouteSpecimen steps={ROUTE_WITH_PROBLEMS} />
      </Row>
      <Row label="legend alone" on="sunken" className="max-w-md">
        <RouteLegend />
      </Row>
    </GallerySection>
  );
}

export function ExamplesSection() {
  return (
    <GallerySection
      id="examples"
      title="Example cards"
      note="The cue column is as wide as the longest cue, the cue and the question share a baseline, and the four cards are equal in height."
    >
      <Row label="rest">
        <div className="max-w-2xl">
          <ExampleList examples={EXAMPLES} tools={TOOLS} onPick={noop} />
        </div>
      </Row>
      <Row label="1 hover · 2 focus · 3 pressed · 4 rest">
        <div className="max-w-2xl">
          <Force state="hover" nth={0}>
            <Force state="focus" nth={1}>
              <Force state="pressed" nth={2}>
                <ExampleList examples={EXAMPLES} tools={TOOLS} onPick={noop} />
              </Force>
            </Force>
          </Force>
        </div>
      </Row>
      <Row label="wide">
        <ExampleList examples={EXAMPLES} tools={TOOLS} onPick={noop} />
      </Row>
    </GallerySection>
  );
}

export function RunningSection() {
  return (
    <GallerySection
      id="running"
      title="What's running"
      note="The content of the popover in the top bar, on the popover's own panel."
    >
      <Row label="ready">
        <PopoverPanel>
          <RunningDetails meta={{ status: "ready", data: META }} />
        </PopoverPanel>
      </Row>
      <Row label="tracing off">
        <PopoverPanel>
          <RunningDetails meta={{ status: "ready", data: { ...META, tracing: false } }} />
        </PopoverPanel>
      </Row>
      <Row label="loading">
        <PopoverPanel>
          <RunningDetails meta={{ status: "loading" }} />
        </PopoverPanel>
      </Row>
      <Row label="error">
        <PopoverPanel>
          <RunningDetails
            meta={{
              status: "error",
              message: "The service could not be reached. Check the connection and try again.",
            }}
          />
        </PopoverPanel>
      </Row>
    </GallerySection>
  );
}
