import { PrivacyIcon } from "@/components/icons/glyphs";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { findRemovedDetails } from "@/lib/placeholders";

export interface QuestionBubbleProps {
  /** The id for the question's text, so the exchange can be labelled by it. */
  id: string;
  /** The question as the agent typed it. */
  question: string;
  /** The question after personal details were replaced, once the answer has come back. */
  processed: string | null;
}

/**
 * The agent's own words: soft-square corners, on the sunken tone. When
 * personal details were replaced, they are underlined in the question, and
 * the "As processed" line shows what the copilot was given instead.
 */
export function QuestionBubble({ id, question, processed }: QuestionBubbleProps) {
  const typed = question.trim();
  const redacted = processed?.trim() ?? null;
  const showProcessed = redacted !== null && redacted !== typed;
  // Where the removed details sat in the question as typed, to underline them.
  const removed = showProcessed ? findRemovedDetails(typed, redacted) : null;

  return (
    <div className="flex max-w-2xl animate-rise flex-col items-end gap-2 self-end">
      <h2 className="cue">Agent</h2>
      <p
        id={id}
        className="rounded-box bg-sunken px-4 py-3 text-read break-words whitespace-pre-wrap text-ink"
      >
        {removed === null
          ? question
          : removed.map((part, index) =>
              part.kind === "removed" ? (
                // The parts of one text never reorder, so the position is a stable key.
                <span key={index} className="pii" title="Replaced before processing">
                  {part.value}
                </span>
              ) : (
                part.value
              ),
            )}
      </p>
      {showProcessed && (
        <div className="grid animate-fade grid-cols-[auto_minmax(0,1fr)] gap-2 self-stretch px-4 leading-relaxed text-ink-2">
          <PrivacyIcon size={16} className="mt-1 text-notice" />
          <p className="break-words">
            As processed: <PlaceholderText text={redacted} />
          </p>
        </div>
      )}
    </div>
  );
}
