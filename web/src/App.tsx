import { useState } from "react";

import { api } from "@/api/client";
import { Footer } from "@/components/shell/Footer";
import { TopBar, type View } from "@/components/shell/TopBar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AskView } from "@/features/ask/AskView";
import { CallsView } from "@/features/calls/CallsView";
import { useLoad } from "@/hooks/useLoad";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/cn";
import { DEMO_CALL, DEMO_QUESTION } from "@/lib/devHooks";

const loadMeta = (signal: AbortSignal) => api.getMeta(signal);

/** In mock mode a `?demo=` in the URL can open the page on the Calls view. Otherwise: Ask. */
const FIRST_VIEW: View = DEMO_CALL === null ? "ask" : "calls";

/**
 * The shell: a top bar, one of two views, and the disclaimer. Both views stay
 * mounted once opened, so a conversation or a chosen call survives a switch.
 */
export function App() {
  const { state: meta, reload: reloadMeta } = useLoad(loadMeta);
  const { theme, toggleTheme } = useTheme();
  const [view, setView] = useState<View>(FIRST_VIEW);
  const [callsOpened, setCallsOpened] = useState(FIRST_VIEW === "calls");
  // A new key remounts the Ask view, which clears the conversation and cancels its request.
  const [conversation, setConversation] = useState(0);

  const changeView = (next: View) => {
    setView(next);
    if (next === "calls") {
      setCallsOpened(true);
    }
  };

  const startNewConversation = () => {
    setConversation((current) => current + 1);
    setView("ask");
  };

  return (
    <TooltipProvider>
      <div className="flex h-dvh flex-col overflow-clip bg-paper text-ink">
        <a
          href="#main"
          className="sr-only z-50 rounded-box bg-ink px-4 py-2 text-meta font-semibold text-surface focus-visible:not-sr-only focus-visible:absolute focus-visible:top-2 focus-visible:left-2"
        >
          Skip to the main content
        </a>
        <TopBar
          view={view}
          onViewChange={changeView}
          meta={meta}
          theme={theme}
          onToggleTheme={toggleTheme}
          onNewConversation={startNewConversation}
        />
        {/*
          The view that is not on show is made invisible and inert, not removed
          from layout. An element that comes back from `display: none` starts
          its CSS animations again, so a hidden conversation would arrive a
          second time on every return.
        */}
        <main
          id="main"
          tabIndex={-1}
          className="relative min-h-0 flex-1 focus-visible:outline-none"
        >
          <div
            inert={view !== "ask"}
            className={cn("absolute inset-0", view !== "ask" && "invisible")}
          >
            <AskView
              key={conversation}
              meta={meta}
              onRetryMeta={reloadMeta}
              // A demo question is sent once, when the page opens, not after "New conversation".
              firstQuestion={conversation === 0 ? DEMO_QUESTION : null}
            />
          </div>
          {callsOpened && (
            <div
              inert={view !== "calls"}
              className={cn("absolute inset-0", view !== "calls" && "invisible")}
            >
              <CallsView />
            </div>
          )}
        </main>
        <Footer disclaimer={meta.status === "ready" ? meta.data.disclaimer : null} />
      </div>
    </TooltipProvider>
  );
}
