import { useId, useLayoutEffect, useState, type KeyboardEvent, type RefObject } from "react";

import { USE_MOCK } from "@/api/client";
import { SendIcon } from "@/components/icons/glyphs";

import { MAX_QUESTION_CHARS } from "./useConversation";

/** The tallest the box grows before it scrolls, in pixels. */
const MAX_HEIGHT = 200;

export interface ComposerProps {
  /** The text box, so the view can move focus to it. */
  inputRef: RefObject<HTMLTextAreaElement | null>;
  /** Send the question. Returns false if it was not accepted, and the text is then kept. */
  onSend: (question: string) => boolean;
  /** True while an answer is on its way. Typing still works; sending does not. */
  waiting: boolean;
  /** Text to start with. Only the component gallery sets it, to show the box in use. */
  initialValue?: string;
}

/** The question box. Enter sends, Shift+Enter starts a new line. */
export function Composer({ inputRef, onSend, waiting, initialValue = "" }: ComposerProps) {
  const [value, setValue] = useState(initialValue);
  const inputId = useId();
  const hintId = useId();
  const canSend = !waiting && value.trim() !== "";

  // Grow with the text, up to a limit.
  useLayoutEffect(() => {
    const element = inputRef.current;
    if (element) {
      element.style.height = "auto";
      element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT)}px`;
    }
  }, [inputRef, value]);

  const send = () => {
    if (canSend && onSend(value)) {
      setValue("");
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter while an input method is composing a character belongs to that method.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      {/* The box is the field. Its one focus ring is drawn by the `field` class. */}
      <div className="field flex items-end gap-3 py-3 pr-3 pl-5">
        <label htmlFor={inputId} className="sr-only">
          Your question
        </label>
        <textarea
          ref={inputRef}
          id={inputId}
          rows={1}
          value={value}
          maxLength={MAX_QUESTION_CHARS}
          placeholder="Ask a question"
          aria-describedby={hintId}
          onChange={(event) => {
            setValue(event.target.value);
          }}
          onKeyDown={onKeyDown}
          className="scrollbar-quiet min-h-11 flex-1 resize-none bg-transparent py-2 text-read text-ink"
        />
        <button
          type="submit"
          aria-label={waiting ? "Waiting for the answer" : "Send question"}
          disabled={!canSend}
          className="grid size-11 shrink-0 place-items-center rounded-box bg-brand text-on-brand transition-colors hover:bg-brand-strong active:bg-brand-press disabled:pointer-events-none disabled:opacity-50"
        >
          <SendIcon size={24} />
        </button>
      </div>
      <p id={hintId} className="mt-2 text-meta text-ink-3">
        {/* A touch screen has no Shift+Enter, and the line costs a row of a small screen. */}
        <span className="pointer-coarse:hidden">Enter to send, Shift+Enter for a new line. </span>
        Personal details are replaced before a question is processed or logged.
        {/* The top bar's "Mock mode" tag is hidden on a narrow window. This is shown at any width. */}
        {USE_MOCK && (
          <span className="font-semibold text-ink-2"> Mock mode: answers are saved samples.</span>
        )}
      </p>
    </form>
  );
}
