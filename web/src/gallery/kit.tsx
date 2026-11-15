import { useLayoutEffect, useRef, type ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A transient state that `data-force` can pin, so a still picture shows it. */
export type ForcedState = "hover" | "focus" | "pressed";

export interface ForceProps {
  state: ForcedState;
  /** Which elements inside to pin, as a CSS selector. The default is every control. */
  target?: string;
  /** Pin only the nth match, counting from 0. */
  nth?: number;
  children: ReactNode;
}

/**
 * Pins a transient state on the real component inside it, by writing the
 * `data-force` attribute that every hover, focus and pressed style answers to
 * (see the custom variants at the top of index.css). The component's own code
 * is untouched: nothing here is a copy.
 */
export function Force({ state, target = "button, a, input, textarea", nth, children }: ForceProps) {
  const wrapper = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const matches = [...(wrapper.current?.querySelectorAll(target) ?? [])];
    const pinned = nth === undefined ? matches : matches.slice(nth, nth + 1);
    for (const element of pinned) {
      element.setAttribute("data-force", state);
    }
    return () => {
      for (const element of pinned) {
        element.removeAttribute("data-force");
      }
    };
  }, [state, target, nth]);

  return (
    <div ref={wrapper} className="contents">
      {children}
    </div>
  );
}

export interface GallerySectionProps {
  id: string;
  title: string;
  /** A sentence on what to look for. */
  note?: string;
  children: ReactNode;
}

/** One section of the gallery: a heading and its rows. */
export function GallerySection({ id, title, note, children }: GallerySectionProps) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-6">
      <div className="border-b-(length:--control-border) border-ink pb-2">
        <h2 id={`${id}-title`} className="display-view text-ink">
          {title}
        </h2>
        {note !== undefined && <p className="mt-1 max-w-3xl text-meta text-ink-2">{note}</p>}
      </div>
      <div>{children}</div>
    </section>
  );
}

const TONES = {
  paper: "bg-paper",
  surface: "bg-surface",
  sunken: "bg-sunken",
} as const;

export interface RowProps {
  /** The state this row shows, such as "hover". */
  label: string;
  /** The background the component normally sits on. */
  on?: keyof typeof TONES;
  /** Extra classes for the specimen, for example a width. */
  className?: string;
  children: ReactNode;
}

/** One state of a component: its name on the left, the component itself on the right. */
export function Row({ label, on = "paper", className, children }: RowProps) {
  return (
    <div className="grid gap-x-6 gap-y-2 border-b border-line py-5 md:grid-cols-[--spacing(44)_minmax(0,1fr)]">
      <p className="font-mono text-meta text-ink-2">{label}</p>
      <div className={cn("min-w-0", on !== "paper" && "p-4", TONES[on], className)}>
        {children}
      </div>
    </div>
  );
}

/** Several small specimens side by side in one row, each with its own caption. */
export function Specimens({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-end gap-x-8 gap-y-4">{children}</div>;
}

export interface SpecimenProps {
  caption: string;
  children: ReactNode;
}

export function Specimen({ caption, children }: SpecimenProps) {
  return (
    <figure className="grid justify-items-start gap-2">
      {children}
      <figcaption className="font-mono text-label text-ink-3">{caption}</figcaption>
    </figure>
  );
}
