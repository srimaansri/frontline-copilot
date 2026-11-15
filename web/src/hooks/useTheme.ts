import { useCallback, useLayoutEffect, useState } from "react";
import { flushSync } from "react-dom";

import { themeFromUrl } from "@/lib/devHooks";

export type Theme = "light" | "dark";

/** The same key is read by the inline script in index.html, before the first paint. */
const STORAGE_KEY = "frontline-copilot.theme";

function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    // Storage can be blocked. The system setting is used instead.
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Change the theme as one event. Some controls ease their colours and most of
 * the page does not, so a plain switch shows the controls arriving a moment
 * after everything else. Here every transition is held off while the colours
 * change, and where the browser can, the old page cross-fades into the new one.
 */
function changeTogether(change: () => void): void {
  const root = document.documentElement;
  const settle = () => {
    root.classList.remove("theme-switch");
  };
  root.classList.add("theme-switch");
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!still && "startViewTransition" in document) {
    document.startViewTransition(change).finished.then(settle, settle);
  } else {
    change();
    // Two frames: the new colours have to be painted before transitions come back.
    requestAnimationFrame(() => requestAnimationFrame(settle));
  }
}

/**
 * The colour theme. The first visit follows the system setting. A choice made
 * with the toggle is remembered.
 *
 * In the dev server and in mock builds, `?theme=light` or `?theme=dark` in the
 * URL wins over both, for screenshots. A page opened that way never writes the
 * theme to storage, so it cannot change what the next visit sees.
 */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(
    () => themeFromUrl() ?? storedTheme() ?? systemTheme(),
  );

  // A layout effect, so the class has changed by the time `flushSync` returns below.
  useLayoutEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const toggleTheme = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    if (themeFromUrl() === null) {
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // The choice still applies to this visit.
      }
    }
    changeTogether(() => {
      flushSync(() => {
        setTheme(next);
      });
    });
  }, [theme]);

  return { theme, toggleTheme };
}
