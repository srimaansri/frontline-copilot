import { useSyncExternalStore } from "react";

import { CopilotMark } from "@/components/icons/CopilotMark";
import * as glyphs from "@/components/icons/glyphs";

import { GallerySection, Row, Specimen, Specimens } from "../kit";

/** Every colour token, in the order of DESIGN.md. */
const COLOURS = [
  "paper",
  "surface",
  "sunken",
  "line",
  "line-strong",
  "edge",
  "ink",
  "ink-2",
  "ink-3",
  "brand",
  "brand-strong",
  "brand-press",
  "brand-text",
  "brand-tint",
  "on-brand",
  "hi",
  "hi-ink",
  "redact",
  "on-redact",
  "ok",
  "ok-tint",
  "notice",
  "notice-tint",
  "warn",
  "warn-tint",
  "block",
  "block-tint",
  "knock",
] as const;

const TYPE_STEPS = [
  { token: "text-label", size: "12.5px", className: "text-label font-bold", sample: "Privacy" },
  { token: "text-meta", size: "14px", className: "text-meta", sample: "1 source cited." },
  { token: "text-ui", size: "15.5px", className: "text-ui font-semibold", sample: "New conversation" },
  { token: "text-read", size: "18px", className: "text-read", sample: "Dial 611 from your phone." },
  { token: "display-title", size: "22px", className: "display-title", sample: "Sources" },
  { token: "display-view", size: "30px", className: "display-view", sample: "Calls" },
  {
    token: "display-head",
    size: "46px",
    className: "display-head",
    sample: "What does the customer need?",
  },
] as const;

/** The steps of the spacing scale that the interface uses. One step is 4px. */
const SPACING_STEPS = [0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 18] as const;

function subscribeToTheme(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => {
    observer.disconnect();
  };
}

/** The value of every colour token in the current theme, as "name=#hex" joined by commas. */
function readColours(): string {
  const style = getComputedStyle(document.documentElement);
  return COLOURS.map((name) => `${name}=${style.getPropertyValue(`--${name}`).trim()}`).join(",");
}

/** The colour tokens with their values, kept up to date when the theme changes. */
function useColours(): { name: string; value: string }[] {
  const snapshot = useSyncExternalStore(subscribeToTheme, readColours);
  return snapshot.split(",").map((entry) => {
    const [name = "", value = ""] = entry.split("=");
    return { name, value };
  });
}

export function TokensSection() {
  const colours = useColours();
  return (
    <GallerySection
      id="tokens"
      title="Tokens"
      note="Colour, type, spacing and shape. Components use these and nothing else. The values shown are read from the page, for the theme it is in."
    >
      <Row label="colour">
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(--spacing(36),1fr))] gap-x-4 gap-y-5">
          {colours.map(({ name, value }) => (
            <li key={name}>
              <span
                className="block h-12 border border-line-strong"
                style={{ background: `var(--${name})` }}
              />
              <span className="mt-2 block text-meta font-bold text-ink">{name}</span>
              <span className="block font-mono text-label text-ink-2">{value}</span>
            </li>
          ))}
        </ul>
      </Row>
      {TYPE_STEPS.map(({ token, size, className, sample }) => (
        <Row key={token} label={`${token} · ${size}`}>
          <p className={className}>{sample}</p>
        </Row>
      ))}
      <Row label="faces">
        <div className="grid gap-3">
          <p className="display-title">Bricolage Grotesque: display</p>
          <p className="text-read">Atkinson Hyperlegible Next: text. Il1 O0 B8 5S rn m</p>
          <p className="font-mono text-read font-semibold">
            Atkinson Hyperlegible Mono: codes. ESC-B695DE84 T0002
          </p>
        </div>
      </Row>
      <Row label="spacing · 4px base">
        <ul className="grid gap-2">
          {SPACING_STEPS.map((step) => (
            <li key={step} className="flex items-center gap-4">
              <span className="w-24 font-mono text-label text-ink-2">
                {step} · {step * 4}px
              </span>
              <span className="block h-3 bg-ink-2" style={{ width: `${step * 4}px` }} />
            </li>
          ))}
        </ul>
      </Row>
      <Row label="radius, border, cut">
        <Specimens>
          <Specimen caption="rounded-box · 3px">
            <span className="block size-12 rounded-box frame border-ink bg-surface" />
          </Specimen>
          <Specimen caption="rounded-chip · 2px">
            <span className="block size-12 rounded-chip frame border-ink bg-surface" />
          </Specimen>
          <Specimen caption="hairline · 1px">
            <span className="block size-12 border border-line-strong bg-surface" />
          </Specimen>
          <Specimen caption="control border · 1.5px">
            <span className="block size-12 frame border-line-strong bg-surface" />
          </Specimen>
          <Specimen caption="SIM cut · 24px">
            <span className="sim block w-20">
              <span className="sim-body block h-12" />
            </span>
          </Specimen>
        </Specimens>
      </Row>
      <Row label="motion">
        <p className="font-mono text-meta text-ink-2">
          state change: 120ms · arriving: 200ms · easing: cubic-bezier(0.2, 0.7, 0.2, 1)
        </p>
      </Row>
    </GallerySection>
  );
}

const ICON_SIZES = [16, 20, 24] as const;

export function IconsSection() {
  return (
    <GallerySection
      id="icons"
      title="Icons"
      note="Every icon in the set at 16, 20 and 24px. One hand: a 24 grid, flat ends, mitred joins, corners cut at 45 degrees."
    >
      <Row label="glyphs" on="surface">
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(--spacing(44),1fr))] gap-x-4 gap-y-6">
          {Object.entries(glyphs).map(([name, Glyph]) => (
            <li key={name} className="grid gap-2">
              <span className="flex items-end gap-4 text-ink">
                {ICON_SIZES.map((size) => (
                  <Glyph key={size} size={size} />
                ))}
              </span>
              <span className="font-mono text-label text-ink-2">{name}</span>
            </li>
          ))}
        </ul>
      </Row>
      <Row label="mark" on="surface">
        <Specimens>
          <Specimen caption="16, small drawing">
            <CopilotMark size={16} />
          </Specimen>
          <Specimen caption="20, small drawing">
            <CopilotMark size={20} />
          </Specimen>
          <Specimen caption="32, master">
            <CopilotMark size={32} />
          </Specimen>
          <Specimen caption="64">
            <CopilotMark size={64} />
          </Specimen>
          <Specimen caption="working">
            <CopilotMark size={32} working />
          </Specimen>
        </Specimens>
      </Row>
      <Row label="mark" on="paper">
        <Specimens>
          <Specimen caption="16">
            <CopilotMark size={16} />
          </Specimen>
          <Specimen caption="32">
            <CopilotMark size={32} />
          </Specimen>
          <Specimen caption="64">
            <CopilotMark size={64} />
          </Specimen>
        </Specimens>
      </Row>
    </GallerySection>
  );
}
