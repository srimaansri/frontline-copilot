import { useLayoutEffect, useRef } from "react";

import type { CallTranscript } from "@/api/types";

import { AssistPanel } from "./AssistPanel";
import { ReplayControls } from "./ReplayControls";
import { Turns } from "./TranscriptPanel";
import { useAssist } from "./useAssist";
import { useReplay } from "./useReplay";

export interface ReplayViewProps {
  transcript: CallTranscript;
  /** Open with the whole call on show. Only a page opened on a demo state sets it. */
  startAtEnd?: boolean;
}

/**
 * A recorded call played back one turn at a time, with call assist following
 * it. The call and the panel are both on screen at every width: side by side
 * on a wide screen, and one above the other, half the height each, on a
 * narrower one, because the point is to watch the panel change as the call does.
 */
export function ReplayView({ transcript, startAtEnd = false }: ReplayViewProps) {
  const replay = useReplay(transcript.turns, startAtEnd);
  const assist = useAssist(transcript.transcript_id, replay.turn);
  const call = useRef<HTMLDivElement>(null);

  // The newest turn is kept in view. It is put there at once, not scrolled to:
  // the turn itself already arrives, and nothing else needs to move.
  useLayoutEffect(() => {
    const element = call.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [replay.turn]);

  return (
    <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ReplayControls
          turn={replay.turn}
          total={transcript.turns.length}
          playing={replay.playing}
          onPlay={replay.play}
          onPause={replay.pause}
          onNext={replay.next}
          onRestart={replay.restart}
        />
        <div ref={call} className="scroll-area min-h-0 flex-1 px-4 pt-6 pb-8 sm:px-8">
          <Turns transcript={transcript} upTo={replay.turn} />
        </div>
      </div>
      {/* The copilot's side rail, on the sunken tone. */}
      <aside className="scroll-area shrink-0 basis-1/2 border-t border-line bg-sunken px-4 py-5 sm:px-8 xl:w-110 xl:basis-auto xl:border-t-0 xl:border-l xl:p-6">
        <AssistPanel
          state={assist.state}
          turn={replay.turn}
          total={transcript.turns.length}
          pending={assist.pending}
          problem={assist.problem}
          onRetry={assist.retry}
        />
      </aside>
    </div>
  );
}
