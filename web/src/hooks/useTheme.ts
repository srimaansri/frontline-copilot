import { useCallback, useEffect, useState } from "react";

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

  useEffect(() => {
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
    setTheme(next);
  }, [theme]);

  return { theme, toggleTheme };
}
