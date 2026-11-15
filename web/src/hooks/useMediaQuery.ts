import { useCallback, useSyncExternalStore } from "react";

/** Tailwind's `lg` breakpoint: room for a side panel next to the conversation. */
export const WIDE_SCREEN = "(min-width: 64rem)";

/** Tailwind's `xl` breakpoint: room for a third column. */
export const EXTRA_WIDE_SCREEN = "(min-width: 80rem)";

export const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

/** Whether a CSS media query matches, kept up to date. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => {
        list.removeEventListener("change", onChange);
      };
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches);
}
