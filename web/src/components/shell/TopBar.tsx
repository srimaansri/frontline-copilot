import { MessagesSquare, Moon, PhoneCall, SquarePen, Sun, type LucideIcon } from "lucide-react";

import { USE_MOCK } from "@/api/client";
import type { Meta } from "@/api/types";
import { BrandMark } from "@/components/shared/BrandMark";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import type { Loadable } from "@/hooks/useLoad";
import type { Theme } from "@/hooks/useTheme";
import { cn } from "@/lib/cn";

import { RunningPopover } from "./RunningPopover";

export type View = "ask" | "calls";

const VIEWS: readonly { id: View; label: string; icon: LucideIcon }[] = [
  { id: "ask", label: "Ask", icon: MessagesSquare },
  { id: "calls", label: "Calls", icon: PhoneCall },
];

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
  const nextTheme = theme === "dark" ? "light" : "dark";
  return (
    <header className="shrink-0 border-b bg-surface">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:flex-nowrap sm:px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <BrandMark />
          <p className="truncate text-[0.9375rem] font-semibold tracking-tight text-fg">
            Frontline Copilot
          </p>
          <span className="hidden shrink-0 rounded-full border px-2 py-0.5 text-[0.6875rem] font-medium text-fg-subtle md:inline">
            Demo, synthetic data
          </span>
          {USE_MOCK && (
            <span className="hidden shrink-0 rounded-full bg-warning-soft px-2 py-0.5 text-[0.6875rem] font-medium text-warning lg:inline">
              Mock mode
            </span>
          )}
        </div>

        <nav
          aria-label="Views"
          className="order-last flex w-full gap-1 rounded-lg bg-surface-muted p-1 sm:order-none sm:ml-2 sm:w-auto"
        >
          {VIEWS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              aria-current={view === id ? "page" : undefined}
              onClick={() => {
                onViewChange(id);
              }}
              className={cn(
                "inline-flex h-8 flex-1 items-center justify-center gap-2 rounded-md px-3.5 text-sm font-medium transition-colors duration-150 sm:flex-none",
                view === id
                  ? "bg-surface text-fg shadow-xs ring-1 ring-border"
                  : "text-fg-muted hover:text-fg",
              )}
            >
              <Icon aria-hidden="true" className="size-4" />
              {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <RunningPopover meta={meta} />
          <IconButton label={`Switch to ${nextTheme} theme`} onClick={onToggleTheme}>
            {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
          </IconButton>
          <Button
            variant="outline"
            size="sm"
            className="ml-1 h-9"
            aria-label="New conversation"
            onClick={onNewConversation}
          >
            <SquarePen aria-hidden="true" />
            <span className="hidden lg:inline">New conversation</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
