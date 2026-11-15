import { useState } from "react";

import { api } from "@/api/client";
import { Footer } from "@/components/shell/Footer";
import { TopBar, type View } from "@/components/shell/TopBar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AskView } from "@/features/ask/AskView";
import { CallsView } from "@/features/calls/CallsView";
import { useLoad } from "@/hooks/useLoad";
import { useTheme } from "@/hooks/useTheme";

const loadMeta = (signal: AbortSignal) => api.getMeta(signal);

/**
 * The shell: a top bar, one of two views, and the disclaimer. Both views stay
 * mounted once opened, so a conversation or a chosen call survives a switch.
 */
export function App() {
  const { state: meta, reload: reloadMeta } = useLoad(loadMeta);
  const { theme, toggleTheme } = useTheme();
  const [view, setView] = useState<View>("ask");
  const [callsOpened, setCallsOpened] = useState(false);
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
        <main id="main" tabIndex={-1} className="min-h-0 flex-1 focus-visible:outline-none">
          <div hidden={view !== "ask"} className="h-full">
            <AskView key={conversation} meta={meta} onRetryMeta={reloadMeta} />
          </div>
          {callsOpened && (
            <div hidden={view !== "calls"} className="h-full">
              <CallsView />
            </div>
          )}
        </main>
        <Footer disclaimer={meta.status === "ready" ? meta.data.disclaimer : null} />
      </div>
    </TooltipProvider>
  );
}
