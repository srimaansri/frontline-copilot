import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

/** The stages every question goes through. Shown in turn; they are not live progress. */
const HINTS = [
  "Removing personal details",
  "Checking the request",
  "Looking it up",
  "Checking the answer",
] as const;

const HINT_MILLISECONDS = 1800;

/**
 * Shown while an answer is on its way. It moves through the names of the
 * stages at a steady pace and claims nothing about which one is running.
 */
export function ProgressHint() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % HINTS.length);
    }, HINT_MILLISECONDS);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div role="status" className="flex items-center gap-4 rounded-xl border bg-surface px-5 py-4">
      <span className="sr-only">Working on the answer.</span>
      <span aria-hidden="true" className="flex shrink-0 items-center gap-1">
        {HINTS.map((hint, position) => (
          <span
            key={hint}
            className={cn(
              "h-1.5 rounded-full transition-all duration-500 ease-out",
              position === index ? "w-6 bg-accent" : "w-1.5 bg-border-strong",
            )}
          />
        ))}
      </span>
      <span key={index} aria-hidden="true" className="animate-fade text-base text-fg-muted">
        {HINTS[index]}
      </span>
    </div>
  );
}
