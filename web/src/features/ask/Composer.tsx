import { useId, useLayoutEffect, useState, type KeyboardEvent, type RefObject } from "react";

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
}

/** The question box. Enter sends, Shift+Enter starts a new line. */
export function Composer({ inputRef, onSend, waiting }: ComposerProps) {
  const [value, setValue] = useState("");
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
      {/* The focus ring is drawn on the box, since the text area has no edge of its own. */}
      <div className="flex items-end gap-3 rounded-box border-[1.5px] border-line-strong bg-surface py-3 pr-3 pl-5 transition-colors duration-150 focus-within:border-ink has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-offset-2 has-[textarea:focus-visible]:outline-brand-text">
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
          className="scrollbar-quiet min-h-11 flex-1 resize-none bg-transparent py-2 text-read text-ink focus-visible:outline-none"
        />
        <button
          type="submit"
          aria-label={waiting ? "Waiting for the answer" : "Send question"}
          disabled={!canSend}
          className="grid size-11 shrink-0 place-items-center rounded-box bg-brand text-on-brand transition-[filter,opacity] duration-150 hover:brightness-110 disabled:pointer-events-none disabled:opacity-50"
        >
          <SendIcon size={24} />
        </button>
      </div>
      <p id={hintId} className="mt-2 text-meta text-ink-3">
        Enter to send, Shift+Enter for a new line. Personal details are replaced before a question
        is processed or logged.
      </p>
    </form>
  );
}
