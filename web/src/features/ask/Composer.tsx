import { ArrowUp } from "lucide-react";
import { useId, useLayoutEffect, useState, type KeyboardEvent, type RefObject } from "react";

import { Button } from "@/components/ui/button";

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
      <div className="flex items-end gap-2 rounded-xl border border-border-strong bg-surface py-2 pr-2 pl-4 transition-[border-color,box-shadow] duration-150 focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--accent-soft)]">
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
          className="scrollbar-quiet min-h-10 flex-1 resize-none bg-transparent py-1.5 text-[1.0625rem] leading-7 text-fg placeholder:text-fg-subtle focus-visible:outline-none"
        />
        <Button
          type="submit"
          size="icon"
          className="size-10"
          aria-label={waiting ? "Waiting for the answer" : "Send question"}
          disabled={!canSend}
        >
          <ArrowUp aria-hidden="true" className="size-5" strokeWidth={2.25} />
        </Button>
      </div>
      <p id={hintId} className="mt-2 px-1 text-xs leading-relaxed text-fg-subtle">
        Enter to send, Shift+Enter for a new line. Personal details are replaced before a question
        is processed or logged.
      </p>
    </form>
  );
}
