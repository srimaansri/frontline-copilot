import type { DemoNote } from "@/api/types";
import { SendIcon } from "@/components/icons/glyphs";
import { StatusStamp } from "@/components/icons/StatusStamp";

/**
 * Said by the demo page, above an answer it replays for a question that was not
 * typed word for word. The answer under it is the copilot's, but to another
 * question, and a reader must not have to work that out. It is the page
 * speaking, not the copilot, so its corners are square.
 */
export function SimilarQuestionNotice({ shownFor }: { shownFor: string }) {
  return (
    <div
      role="note"
      className="mb-2 flex items-start gap-3 rounded-box border border-line-strong bg-surface px-4 py-3"
    >
      <StatusStamp status="notice" size={20} className="mt-0.5" />
      <p className="min-w-0 text-ui leading-relaxed text-ink">
        This page replays recordings and cannot run the copilot. It has none of your question as you
        typed it, so this is what the live copilot answered to the closest one:{" "}
        <strong className="font-semibold">{shownFor}</strong>
      </p>
    </div>
  );
}

export interface RecordedQuestionsProps {
  note: DemoNote;
  /** Asks one of the recorded questions. Absent where nothing can be asked, as in the gallery. */
  onAsk?: (question: string) => void;
}

/** Recorded questions to ask next, the closest first. Each is a real recording. */
export function RecordedQuestions({ note, onAsk }: RecordedQuestionsProps) {
  if (note.suggestions.length === 0) {
    return null;
  }
  return (
    <div className="mt-3">
      <p className="cue text-ink-2">
        {note.shown_for === null ? "Recorded questions to try" : "Other recorded questions"}
      </p>
      <ul className="mt-2 grid gap-2">
        {note.suggestions.map((question) => (
          <li key={question}>
            <button
              type="button"
              disabled={onAsk === undefined}
              onClick={() => {
                onAsk?.(question);
              }}
              className="flex w-full items-center gap-3 rounded-box border border-line-strong bg-surface px-4 py-2.5 text-left text-ui text-ink transition-[border-color,background-color] hover:edge-ink active:bg-sunken"
            >
              <span className="min-w-0 flex-1">{question}</span>
              <SendIcon size={16} className="shrink-0 text-brand-text" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
