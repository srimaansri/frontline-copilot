import { useCallback, useEffect, useState } from "react";

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
 */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme());

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const toggleTheme = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The choice still applies to this visit.
    }
    setTheme(next);
  }, [theme]);

  return { theme, toggleTheme };
}
