/**
 * The icon set, drawn for this product. Every icon uses the `Icon` base: a 24
 * grid, runs at 45 and 90 degrees, flat ends and mitred joins. See DESIGN.md.
 */

import { Icon, type IconProps } from "./Icon";

// --- Views -----------------------------------------------------------------------------------

/** A speech bubble holding two lines of a question. */
export function AskIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 4.5h16V16h-8l-4.5 4v-4H4z" />
      <path d="M8 8.8h8M8 12.2h5" />
    </Icon>
  );
}

/** A handset over two lines of transcript. */
export function CallsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 9l3-3h12l3 3v4.5h-5.5v-3h-7v3H3z" />
      <path d="M6 17.5h12M6 20.6h7" />
    </Icon>
  );
}

// --- Tools -----------------------------------------------------------------------------------

/** Help articles: a page with a cut corner and three lines. */
export function ArticlesIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 3h8.5L19 7.5V21H6z" />
      <path d="M9.5 8h2.5M9.5 12h6M9.5 16h6" />
    </Icon>
  );
}

/** Plan catalogue: a price tag. */
export function PlansIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.5 3.5H12l8.5 8.5-8.5 8.5L3.5 12z" />
      <path d="M7.3 7.3h2v2h-2z" />
    </Icon>
  );
}

/** Call summary: many lines gathered into one. */
export function CallSummaryIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.5 6h7M3.5 10h7M3.5 14h7M3.5 18h7" />
      <path d="M13.5 5h3v14h-3M16.5 12h4.5" />
    </Icon>
  );
}

/** Wrap-up: the record of a call on a clipboard, ticked off. */
export function WrapUpIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 4.5H5V21h14V4.5h-4" />
      <path d="M9 3h6v3.5H9z" />
      <path d="M8.5 13.5l2.5 2.5 4.5-4.5" />
    </Icon>
  );
}

/** Hand-off: an arrow passing to a person. */
export function HandoffIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M1.5 10H7M4.5 7l3 3-3 3" />
      <path d="M13 4h4.5v4.5H13z" />
      <path d="M9.5 20v-4l3-3H18l3 3v4" />
    </Icon>
  );
}

/** A tool the interface has no drawing for: a plain nut. */
export function GenericToolIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 2.8l8 4.6v9.2l-8 4.6-8-4.6V7.4z" />
      <path d="M9.8 9.8h4.4v4.4H9.8z" />
    </Icon>
  );
}

// --- Stages of a request ----------------------------------------------------------------------

/** Privacy: lines of text with part of one struck out by a redaction bar. */
export function PrivacyIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 6.5h16M4 12h3.5M4 17.5h11" />
      <rect x="9.5" y="9.8" width="10.5" height="4.4" fill="currentColor" stroke="none" />
    </Icon>
  );
}

/** Request check: a shield. */
export function RequestCheckIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3l7.5 3v6.5L12 21l-7.5-8.5V6z" />
      <path d="M10.4 8.6h3.2v3.2h-3.2z" />
    </Icon>
  );
}

/** Answer check: lines of an answer, ticked. */
export function AnswerCheckIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 6h16M4 11h8.5" />
      <path d="M10.5 16.5l3.5 3.5 7-7.5" />
    </Icon>
  );
}

// --- The rule check on a call -----------------------------------------------------------------

/** Rule check: a flag on its pole, its fly cut to a notch. A rule pointed here. */
export function FlagIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 21.5V4h13l-4.5 4.5L19 13H6" />
    </Icon>
  );
}

// --- Mood of a call ---------------------------------------------------------------------------
// One eight-sided face, the same eyes, and only the mouth changes.

const FACE = "M8.5 3h7L21 8.5v7L15.5 21h-7L3 15.5v-7z";
const EYES = "M9.2 8.4v3.2M14.8 8.4v3.2";

export function MoodPositiveIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d={FACE} />
      <path d={EYES} />
      <path d="M7.8 14l2.5 2.5h3.4l2.5-2.5" />
    </Icon>
  );
}

export function MoodNeutralIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d={FACE} />
      <path d={EYES} />
      <path d="M8.5 15.6h7" />
    </Icon>
  );
}

export function MoodNegativeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d={FACE} />
      <path d={EYES} />
      <path d="M7.8 17l2.5-2.5h3.4l2.5 2.5" />
    </Icon>
  );
}

// --- Controls ---------------------------------------------------------------------------------

/** Send: the arrow on an Enter key, because Enter sends. */
export function SendIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M19 5v8.5H6.5" />
      <path d="M10.5 9.5l-4 4 4 4" />
    </Icon>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 7.5l4.5 4.5-4.5 4.5L7.5 12z" />
      <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
    </Icon>
  );
}

/** A crescent with every edge at 45 or 90 degrees: an eight-sided disc with a bite out of it. */
export function MoonIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M13.5 4h-5l-5 5v7l5 5h7l5-5h-6l-4-4V7z" />
    </Icon>
  );
}

/** The Ask bubble with a plus in it. */
export function NewConversationIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 4.5h16V16h-8l-4.5 4v-4H4z" />
      <path d="M12 7.2v6M9 10.2h6" />
    </Icon>
  );
}

const THUMB = "M7.5 20.5v-10l4-7h1.8l1.2 1.5v4H20l1 1.5-1.5 8.5-1.5 1.5z";
const CUFF = "M7.5 10.5h-4v10h4";

export function ThumbUpIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d={THUMB} />
      <path d={CUFF} />
    </Icon>
  );
}

export function ThumbDownIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <g transform="rotate(180 12 12)">
        <path d={THUMB} />
        <path d={CUFF} />
      </g>
    </Icon>
  );
}

export function ExternalLinkIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M10.5 5h-6v14.5H19v-6" />
      <path d="M13.5 4.5h6v6M19.5 4.5l-9 9" />
    </Icon>
  );
}

/** An eight-sided lens and its handle. */
export function SearchIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 3.5h5.5l4 4V13l-4 4H8l-4-4V7.5z" />
      <path d="M15.5 15l5.5 5.5" />
    </Icon>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M5.5 9l6.5 6.5L18.5 9" />
    </Icon>
  );
}

export function BackIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M20 12H5.5M11 6.5L5.5 12l5.5 5.5" />
    </Icon>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M5.5 5.5l13 13M18.5 5.5l-13 13" />
    </Icon>
  );
}

/** An eight-sided loop that comes back round to its own arrowhead. */
export function RetryIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M15.5 4.5h-7l-4 4v7l4 4h7l4-4V11" />
      <path d="M12.5 1.5l3 3-3 3" />
    </Icon>
  );
}

/** A window with a panel down its right side. */
export function PanelIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.5 4.5h17v15h-17z" />
      <path d="M14.5 4.5v15" />
    </Icon>
  );
}

// --- Replay ----------------------------------------------------------------------------------

/** Play: a triangle that points the way the call runs. */
export function PlayIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 4.5l7.5 7.5L8 19.5z" />
    </Icon>
  );
}

/** Pause: two bars. */
export function PauseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8.5 5v14M15.5 5v14" />
    </Icon>
  );
}

/** One turn on: the play triangle up against a bar. */
export function NextTurnIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 5l7 7-7 7z" />
      <path d="M17.5 5v14" />
    </Icon>
  );
}

/** Back to the first turn: a bar, and the triangle turned to face it. */
export function StartAgainIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6.5 5v14" />
      <path d="M18 5l-7 7 7 7z" />
    </Icon>
  );
}
