import type { ReactElement } from "react";

import { USE_MOCK } from "@/api/client";
import type { Meta } from "@/api/types";
import { CopilotMark } from "@/components/icons/CopilotMark";
import {
  AskIcon,
  CallsIcon,
  MoonIcon,
  NewConversationIcon,
  SunIcon,
} from "@/components/icons/glyphs";
import type { IconProps } from "@/components/icons/Icon";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import type { Loadable } from "@/hooks/useLoad";
import type { Theme } from "@/hooks/useTheme";
import { cn } from "@/lib/cn";

import { RunningPopover } from "./RunningPopover";

export type View = "ask" | "calls";

const VIEWS: readonly { id: View; label: string; icon: (props: IconProps) => ReactElement }[] = [
  { id: "ask", label: "Ask", icon: AskIcon },
  { id: "calls", label: "Calls", icon: CallsIcon },
];

/** A dashed outline marks a label about the data itself: it is synthetic, or mocked. */
function DataTag({ children, className }: { children: string; className?: string }) {
  return (
    <span
      className={cn(
        "shrink-0 border border-dashed border-line-strong px-2 py-[3px] text-label font-semibold whitespace-nowrap text-ink-2",
        className,
      )}
    >
      {children}
    </span>
  );
}

interface ThemeToggleProps {
  theme: Theme;
  onToggle: () => void;
}

/** Sun and moon side by side. The one that is on is filled with ink. */
function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  const label = `Switch to ${theme === "dark" ? "light" : "dark"} theme`;
  const half = "grid w-[30px] place-items-center sm:w-[38px]";
  const on = "bg-ink text-surface";
  const off = "text-ink-3";
  return (
    <Tooltip label={label}>
      <button
        type="button"
        aria-label={label}
        onClick={onToggle}
        className="inline-flex h-9 shrink-0 overflow-hidden rounded-box border-[1.5px] border-line-strong bg-surface transition-colors duration-150 hover:border-ink sm:h-10"
      >
        <span className={cn(half, theme === "light" ? on : off)}>
          <SunIcon />
        </span>
        <span className={cn(half, theme === "dark" ? on : off)}>
          <MoonIcon />
        </span>
      </button>
    </Tooltip>
  );
}

export interface TopBarProps {
  view: View;
  onViewChange: (view: View) => void;
  meta: Loadable<Meta>;
  theme: Theme;
  onToggleTheme: () => void;
  onNewConversation: () => void;
}

export function TopBar({
  view,
  onViewChange,
  meta,
  theme,
  onToggleTheme,
  onNewConversation,
}: TopBarProps) {
  return (
    <header className="shrink-0 border-b border-line bg-surface">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 px-4 py-2.5 sm:h-16 sm:flex-nowrap sm:px-6 sm:py-0">
        <div className="flex min-w-0 items-center gap-2.5">
          <CopilotMark size={30} />
          <p className="truncate font-display text-read font-bold tracking-[-0.015em] sm:text-title">
            Frontline Copilot
          </p>
        </div>
        <DataTag className="hidden lg:inline">Demo, synthetic data</DataTag>
        {USE_MOCK && <DataTag className="hidden xl:inline">Mock mode</DataTag>}

        <nav
          aria-label="Views"
          className="order-last flex w-full overflow-hidden rounded-box border-[1.5px] border-ink sm:order-none sm:ml-1 sm:w-auto"
        >
          {VIEWS.map(({ id, label, icon: Glyph }, index) => (
            <button
              key={id}
              type="button"
              aria-current={view === id ? "page" : undefined}
              onClick={() => {
                onViewChange(id);
              }}
              className={cn(
                "inline-flex h-[37px] flex-1 items-center justify-center gap-2 pr-4 pl-3 font-semibold transition-colors duration-150 focus-visible:-outline-offset-2 sm:flex-none",
                index > 0 && "border-l-[1.5px] border-ink",
                // Ink fill: you are here.
                view === id ? "bg-ink text-surface" : "bg-surface text-ink hover:bg-sunken",
              )}
            >
              <Glyph />
              {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2.5">
          <RunningPopover meta={meta} />
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          <Button
            className="h-9 px-2 sm:h-10 sm:px-2.5 xl:pr-3.5 xl:pl-3"
            aria-label="New conversation"
            onClick={onNewConversation}
          >
            <NewConversationIcon />
            <span className="hidden xl:inline">New conversation</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
