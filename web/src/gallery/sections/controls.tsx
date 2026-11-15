import type { StepStatus } from "@/api/types";
import {
  NewConversationIcon,
  RetryIcon,
  ThumbUpIcon,
} from "@/components/icons/glyphs";
import { StatusLabel, StatusStamp, StatusWord } from "@/components/icons/StatusStamp";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { SignalBars } from "@/components/shared/SignalBars";
import { ToolBadge } from "@/components/shared/ToolBadge";
import { WorkingCard } from "@/components/shared/WorkingCard";
import { DataTag, ThemeToggle, ViewSwitcher } from "@/components/shell/TopBar";
import { Button, type ButtonProps } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { AnswerMarkdown } from "@/features/ask/AnswerMarkdown";
import { ProgressHint } from "@/features/ask/ProgressHint";

import { CITED, NO_CITATIONS, NO_REFERENCES, noop, TOOLS } from "../fixtures";
import { Force, GallerySection, Row, Specimen, Specimens } from "../kit";

type Variant = NonNullable<ButtonProps["variant"]>;

const VARIANTS: readonly { variant: Variant; means: string }[] = [
  { variant: "primary", means: "the one main thing to press" },
  { variant: "outline", means: "an ordinary action" },
  { variant: "quiet", means: "an action in a bar" },
  { variant: "on", means: "showing what is on" },
];

const FORCED = ["hover", "focus", "pressed"] as const;

export function ButtonsSection() {
  return (
    <GallerySection
      id="buttons"
      title="Buttons and icon buttons"
      note="Each variant at rest, under the pointer, focused from the keyboard, pressed and disabled. No state changes the size of the button."
    >
      {VARIANTS.map(({ variant, means }) => (
        <Row key={variant} label={`${variant}: ${means}`} on="surface">
          <Specimens>
            <Specimen caption="rest">
              <Button variant={variant}>
                <NewConversationIcon />
                New conversation
              </Button>
            </Specimen>
            {FORCED.map((state) => (
              <Specimen key={state} caption={state}>
                <Button variant={variant} data-force={state}>
                  <NewConversationIcon />
                  New conversation
                </Button>
              </Specimen>
            ))}
            <Specimen caption="disabled">
              <Button variant={variant} disabled>
                <NewConversationIcon />
                New conversation
              </Button>
            </Specimen>
          </Specimens>
        </Row>
      ))}
      <Row label="sizes" on="surface">
        <Specimens>
          <Specimen caption="sm · 36px">
            <Button size="sm">
              <RetryIcon size={16} />
              Try again
            </Button>
          </Specimen>
          <Specimen caption="md · 40px">
            <Button>Summarize</Button>
          </Specimen>
        </Specimens>
      </Row>
      {(["outline", "on"] as const).map((variant) => (
        <Row key={variant} label={`icon button, ${variant}`} on="surface">
          <Specimens>
            <Specimen caption="rest">
              <IconButton label="Helpful" variant={variant}>
                <ThumbUpIcon />
              </IconButton>
            </Specimen>
            {FORCED.map((state) => (
              <Specimen key={state} caption={state}>
                <IconButton label="Helpful" variant={variant} data-force={state}>
                  <ThumbUpIcon />
                </IconButton>
              </Specimen>
            ))}
            <Specimen caption="disabled">
              <IconButton label="Helpful" variant={variant} disabled>
                <ThumbUpIcon />
              </IconButton>
            </Specimen>
          </Specimens>
        </Row>
      ))}
    </GallerySection>
  );
}

export function ViewSwitcherSection() {
  return (
    <GallerySection
      id="view-switcher"
      title="View switcher"
      note="The view you are on is filled with ink. The states below are pinned on the other button."
    >
      <Row label="states" on="surface">
        <Specimens>
          <Specimen caption="Ask is current">
            <ViewSwitcher view="ask" onViewChange={noop} />
          </Specimen>
          <Specimen caption="Calls is current">
            <ViewSwitcher view="calls" onViewChange={noop} />
          </Specimen>
          {FORCED.map((state) => (
            <Specimen key={state} caption={`${state} on Calls`}>
              <Force state={state} nth={1}>
                <ViewSwitcher view="ask" onViewChange={noop} />
              </Force>
            </Specimen>
          ))}
        </Specimens>
      </Row>
    </GallerySection>
  );
}

export function ThemeToggleSection() {
  return (
    <GallerySection
      id="theme-toggle"
      title="Theme toggle"
      note="Sun and moon side by side. The theme in use is filled with ink."
    >
      <Row label="states" on="surface">
        <Specimens>
          <Specimen caption="light is on">
            <ThemeToggle theme="light" onToggle={noop} />
          </Specimen>
          <Specimen caption="dark is on">
            <ThemeToggle theme="dark" onToggle={noop} />
          </Specimen>
          {FORCED.map((state) => (
            <Specimen key={state} caption={state}>
              <Force state={state}>
                <ThemeToggle theme="light" onToggle={noop} />
              </Force>
            </Specimen>
          ))}
        </Specimens>
      </Row>
    </GallerySection>
  );
}

export function TagsSection() {
  return (
    <GallerySection
      id="tags"
      title="Tags and tool badges"
      note="A dashed tag is a label about the data itself. A tool badge names a tool the copilot used."
    >
      <Row label="data tags" on="surface">
        <Specimens>
          <DataTag>Demo, synthetic data</DataTag>
          <DataTag>Mock mode</DataTag>
        </Specimens>
      </Row>
      <Row label="tool badges">
        <Specimens>
          {TOOLS.map((tool) => (
            <ToolBadge key={tool.name} name={tool.name} tools={TOOLS} />
          ))}
          <ToolBadge name="an_unknown_tool" tools={TOOLS} />
        </Specimens>
      </Row>
    </GallerySection>
  );
}

const STATUSES: readonly StepStatus[] = ["ok", "notice", "warning", "blocked"];
const STAMP_SIZES = [16, 20, 24] as const;

export function StatusSection() {
  return (
    <GallerySection
      id="status"
      title="Status stamps"
      note="Shape first, colour second, word third: circle OK, square Notice, triangle Warning, octagon Blocked."
    >
      {STAMP_SIZES.map((size) => (
        <Row key={size} label={`stamps · ${size}px`} on="surface">
          <Specimens>
            {STATUSES.map((status) => (
              <StatusStamp key={status} status={status} size={size} />
            ))}
          </Specimens>
        </Row>
      ))}
      <Row label="on the rail" on="sunken">
        <Specimens>
          {STATUSES.map((status) => (
            <span key={status} className="inline-flex items-center gap-3">
              <StatusStamp status={status} size={24} />
              <StatusWord status={status} />
            </span>
          ))}
        </Specimens>
      </Row>
      <Row label="with words" on="surface">
        <Specimens>
          <StatusLabel status="ok">Resolved</StatusLabel>
          <StatusLabel status="notice">Escalated</StatusLabel>
          <StatusLabel status="warning">Unresolved</StatusLabel>
          <StatusLabel status="blocked">Not responding</StatusLabel>
        </Specimens>
      </Row>
      <Row label="silhouette on ink">
        <span className="inline-flex items-center gap-4 bg-ink p-3">
          {STATUSES.map((status) => (
            <StatusStamp key={status} status={status} className="text-surface" />
          ))}
        </span>
      </Row>
    </GallerySection>
  );
}

const CLAIM = "The Late Payment Fee is **$5** [1].";
const FIRST_SOURCE = CITED.response.citations.slice(0, 1);

export function CitationSection() {
  return (
    <GallerySection
      id="citation"
      title="Citation chip"
      note="A square numeral after a claim. Outlined at rest, tinted under the pointer, filled when its source is the one in focus."
    >
      <Row label="states" on="surface">
        <Specimens>
          <Specimen caption="rest">
            <AnswerMarkdown
              markdown={CLAIM}
              citations={FIRST_SOURCE}
              references={NO_REFERENCES}
              activeCitation={null}
              onCite={noop}
            />
          </Specimen>
          {FORCED.map((state) => (
            <Specimen key={state} caption={state}>
              <Force state={state}>
                <AnswerMarkdown
                  markdown={CLAIM}
                  citations={FIRST_SOURCE}
                  references={NO_REFERENCES}
                  activeCitation={null}
                  onCite={noop}
                />
              </Force>
            </Specimen>
          ))}
          <Specimen caption="selected">
            <AnswerMarkdown
              markdown={CLAIM}
              citations={FIRST_SOURCE}
              references={NO_REFERENCES}
              activeCitation={1}
              onCite={noop}
            />
          </Specimen>
        </Specimens>
      </Row>
    </GallerySection>
  );
}

export function RedactionSection() {
  return (
    <GallerySection
      id="redaction"
      title="Redaction bar and highlighter"
      note="The two pen marks. A bar where a personal detail was removed; the highlighter on a fact to say out loud."
    >
      <Row label="redaction bar" on="surface">
        <p className="text-read">
          <PlaceholderText text="Her name is <PERSON_1> and her number is <PHONE_NUMBER_1>." />
        </p>
      </Row>
      <Row label="redaction bar, small text" on="sunken">
        <p className="text-ui text-ink-2">
          <PlaceholderText text="As processed: send it to <EMAIL_ADDRESS_1>." />
        </p>
      </Row>
      <Row label="highlighter" on="surface">
        <AnswerMarkdown
          markdown="Dial **611** from a Northline phone, **or** **1-800-555-0199** from any phone, and ask for a **one-time waiver**."
          citations={NO_CITATIONS}
          references={NO_REFERENCES}
          activeCitation={null}
          onCite={noop}
        />
      </Row>
      <Row label="bold that is not a fact" on="surface">
        <AnswerMarkdown
          markdown={"**How to request a waiver**\n\n**Next step:** call support, **not** the store."}
          citations={NO_CITATIONS}
          references={NO_REFERENCES}
          activeCitation={null}
          onCite={noop}
        />
      </Row>
    </GallerySection>
  );
}

const STAGE_NAMES = ["Privacy", "Request check", "Lookup", "Answer check"] as const;

export function SignalBarsSection() {
  return (
    <GallerySection
      id="signal-bars"
      title="Signal bars"
      note="The copilot's own state: one bar per stage. The bar being worked on pulses."
    >
      <Row label="sizes" on="surface">
        <Specimens>
          <Specimen caption="sm · 16px">
            <SignalBars level={4} size="sm" />
          </Specimen>
          <Specimen caption="md · 24px">
            <SignalBars level={4} />
          </Specimen>
          <Specimen caption="lg · 36px, ink">
            <SignalBars level={4} size="lg" tone="ink" />
          </Specimen>
        </Specimens>
      </Row>
      <Row label="filled, 0 to 4" on="surface">
        <Specimens>
          {[0, 1, 2, 3, 4].map((level) => (
            <Specimen key={level} caption={String(level)}>
              <SignalBars level={level} />
            </Specimen>
          ))}
        </Specimens>
      </Row>
      <Row label="each stage, on the card">
        <div className="grid gap-3">
          {STAGE_NAMES.map((stage, index) => (
            <WorkingCard key={stage} bar={index}>
              {stage}
            </WorkingCard>
          ))}
        </div>
      </Row>
      <Row label="waiting, animated">
        <ProgressHint />
      </Row>
    </GallerySection>
  );
}
