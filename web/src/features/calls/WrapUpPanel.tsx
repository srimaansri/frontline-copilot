import { useId, useLayoutEffect, useRef, type ReactNode } from "react";

import type { CallWrapUp, SavedWrapUp, Sentiment } from "@/api/types";
import { WrapUpIcon } from "@/components/icons/glyphs";
import { StatusLabel } from "@/components/icons/StatusStamp";
import { ErrorNotice } from "@/components/shared/ErrorNotice";
import { PlaceholderText } from "@/components/shared/PlaceholderText";
import { WorkingCard } from "@/components/shared/WorkingCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCycle } from "@/hooks/useCycle";
import { formatDateTime } from "@/lib/format";

import { CallStatus } from "./CallStatus";
import { Field, MoodLabel, RelatedArticles } from "./SummaryPanel";
import type { WrapUpState } from "./useWrapUps";
import {
  CATEGORIES,
  categoryLabel,
  DISPOSITIONS,
  isChanged,
  MAX_LINE_CHARS,
  OWNERS,
  problemWith,
  SENTIMENTS,
  type OwnerChoice,
  type WrapUpField,
  type WrapUpForm,
} from "./wrapUpForm";

/** Who takes the next step, as a saved wrap-up says it. */
const OWNER_NAMES: Record<Exclude<OwnerChoice, "none">, string> = {
  customer: "The customer",
  agent: "You",
  team: "Another team",
};

type DraftState = Extract<WrapUpState, { status: "draft" }>;

interface LabelProps {
  htmlFor: string;
  children: ReactNode;
  /** Whether the agent has changed this part since the form opened. */
  changed: boolean;
  startedFrom: DraftState["startedFrom"];
}

/**
 * The label of one part of the form. Beside it, whose words are in the box
 * right now: the copilot's, until the agent changes them.
 */
function Label({ htmlFor, children, changed, startedFrom }: LabelProps) {
  const unchanged = startedFrom === "copilot" ? "Cue's draft" : "As saved";
  return (
    <label
      htmlFor={htmlFor}
      className="flex flex-wrap items-baseline justify-between gap-x-3 text-label font-semibold text-ink-2"
    >
      {children}
      <span className={changed ? "text-ink" : "font-normal text-ink-3"}>
        {changed ? "Changed by you" : unchanged}
      </span>
    </label>
  );
}

function Choice<T extends string>({
  id,
  value,
  options,
  disabled,
  onChange,
}: {
  id: string;
  value: T;
  options: readonly { value: T; label: string }[];
  disabled: boolean;
  onChange: (value: T) => void;
}) {
  return (
    <div className="field mt-1 px-2">
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          const chosen = options.find((option) => option.value === event.target.value);
          if (chosen) {
            onChange(chosen.value);
          }
        }}
        className="h-10 w-full bg-transparent text-ui text-ink"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

interface LinesBoxProps {
  id: string;
  /** The fewest lines the box shows. */
  rows: number;
  value: string;
  disabled: boolean;
  placeholder?: string;
  describedBy?: string;
  onChange: (value: string) => void;
}

/**
 * A box that holds one item to a line. It grows with its text, so the whole
 * draft is on show and nothing has to be scrolled into view to be checked.
 */
function LinesBox({ id, rows, value, disabled, placeholder, describedBy, onChange }: LinesBoxProps) {
  const box = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const element = box.current;
    if (!element) {
      return undefined;
    }
    const fit = () => {
      element.style.height = "auto";
      element.style.height = `${element.scrollHeight}px`;
    };
    fit();
    // The text wraps differently when the box changes width or the typeface arrives.
    const observer = new ResizeObserver(fit);
    observer.observe(element);
    void document.fonts.ready.then(fit);
    return () => {
      observer.disconnect();
    };
  }, [value]);

  return (
    <div className="field mt-1 px-3 py-2">
      <textarea
        ref={box}
        id={id}
        rows={rows}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        aria-describedby={describedBy}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="block w-full resize-none overflow-hidden bg-transparent text-ui text-ink placeholder:text-ink-3"
      />
    </div>
  );
}

interface DraftFormProps {
  state: DraftState;
  onChange: (form: WrapUpForm) => void;
  onSave: () => void;
}

/**
 * The wrap-up as a form. The copilot filled it in; the agent checks it, changes
 * what is wrong, and saves it. Nothing is stored until they do.
 *
 * Like a hand-off draft it keeps soft-square corners, not the cut corner: it is
 * the agent's to act on, and what is saved is the agent's record.
 */
function DraftForm({ state, onChange, onSave }: DraftFormProps) {
  const { form, start, startedFrom, saving } = state;
  const ids = {
    disposition: useId(),
    category: useId(),
    notes: useId(),
    promises: useId(),
    owner: useId(),
    action: useId(),
    sentiment: useId(),
    hint: useId(),
  };
  const set = <K extends keyof WrapUpForm>(key: K, value: WrapUpForm[K]) => {
    onChange({ ...form, [key]: value });
  };
  const label = (field: WrapUpField, htmlFor: string, words: string) => (
    <Label htmlFor={htmlFor} changed={isChanged(field, form, start)} startedFrom={startedFrom}>
      {words}
    </Label>
  );
  const problem = problemWith(form);
  const edited = (
    ["disposition", "category", "notes", "promises", "followUp", "sentiment"] as const
  ).some((field) => isChanged(field, form, start));
  // A category this list does not have is still shown, so that nothing is changed unseen.
  const categories = CATEGORIES.some((item) => item.value === form.category)
    ? CATEGORIES
    : [...CATEGORIES, { value: form.category, label: categoryLabel(form.category) }];

  return (
    <div className="mt-4 animate-rise rounded-box border border-line-strong bg-surface px-4 py-4 text-ink">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-semibold">
        <WrapUpIcon />
        {startedFrom === "copilot" ? "Cue drafted this." : "You are changing a saved wrap-up."}
        <span className="rounded-box border border-dashed border-line-strong px-2 py-0.5 text-label font-semibold text-ink-2">
          {startedFrom === "copilot" ? "Not saved yet" : "Changes not saved yet"}
        </span>
      </p>
      <p className="mt-2 text-ui text-ink-2">
        Check it, change what is wrong, then save it. Personal details were replaced before it was
        drafted, and anything you type is checked again when you save.
      </p>

      <div className="mt-4 grid gap-4">
        <div>
          {label("disposition", ids.disposition, "How the call ended")}
          <Choice
            id={ids.disposition}
            value={form.disposition}
            options={DISPOSITIONS}
            disabled={saving}
            onChange={(value) => {
              set("disposition", value);
            }}
          />
        </div>

        <div>
          {label("category", ids.category, "What the call was about")}
          <Choice
            id={ids.category}
            value={form.category}
            options={categories}
            disabled={saving}
            onChange={(value) => {
              set("category", value);
            }}
          />
        </div>

        <div>
          {label("notes", ids.notes, "Notes")}
          <LinesBox
            id={ids.notes}
            rows={3}
            value={form.notes}
            disabled={saving}
            describedBy={ids.hint}
            onChange={(value) => {
              set("notes", value);
            }}
          />
          <p id={ids.hint} className="mt-1 text-meta text-ink-2">
            One note on each line.
          </p>
        </div>

        <div>
          {label("promises", ids.promises, "What the customer was told will happen")}
          <LinesBox
            id={ids.promises}
            rows={2}
            value={form.promises}
            disabled={saving}
            placeholder="Nothing was promised"
            onChange={(value) => {
              set("promises", value);
            }}
          />
          <p className="mt-1 text-meta text-ink-2">
            One on each line. Leave it empty if nothing was promised.
          </p>
        </div>

        <div>
          {label("followUp", ids.owner, "Who takes the next step")}
          <Choice
            id={ids.owner}
            value={form.owner}
            options={OWNERS}
            disabled={saving}
            onChange={(value) => {
              set("owner", value);
            }}
          />
          {form.owner !== "none" && (
            <>
              <label
                htmlFor={ids.action}
                className="mt-3 block text-label font-semibold text-ink-2"
              >
                What the next step is
              </label>
              <div className="field mt-1 px-3">
                <input
                  id={ids.action}
                  type="text"
                  value={form.action}
                  maxLength={MAX_LINE_CHARS}
                  disabled={saving}
                  onChange={(event) => {
                    set("action", event.target.value);
                  }}
                  className="h-10 w-full bg-transparent text-ui text-ink"
                />
              </div>
            </>
          )}
        </div>

        <div>
          {label("sentiment", ids.sentiment, "The customer's mood at the end")}
          <Choice<Sentiment>
            id={ids.sentiment}
            value={form.sentiment}
            options={SENTIMENTS}
            disabled={saving}
            onChange={(value) => {
              set("sentiment", value);
            }}
          />
        </div>
      </div>

      {state.problem !== null && (
        <p role="alert" className="mt-4 text-ui font-semibold text-ink">
          {state.problem}
        </p>
      )}
      {/* What is missing is said in words, so the button is never off without a reason. */}
      {problem !== null && <p className="mt-4 text-ui text-ink-2">{problem}</p>}

      <div className="mt-4 flex flex-wrap gap-3">
        <Button variant="primary" disabled={saving || problem !== null} onClick={onSave}>
          {saving ? "Saving the wrap-up" : "Save wrap-up"}
        </Button>
        {edited && (
          <Button
            variant="quiet"
            disabled={saving}
            onClick={() => {
              onChange(start);
            }}
          >
            Undo my changes
          </Button>
        )}
      </div>
    </div>
  );
}

function Lines({ lines }: { lines: string[] }) {
  return (
    <ol className="grid gap-2">
      {lines.map((line, index) => (
        // Two notes may say the same thing, and the list is never reordered.
        <li key={index} className="grid grid-cols-[--spacing(6)_minmax(0,1fr)]">
          <span aria-hidden="true" className="font-mono font-semibold text-ink-3">
            {index + 1}.
          </span>
          <span className="break-words">
            <PlaceholderText text={line} />
          </span>
        </li>
      ))}
    </ol>
  );
}

interface SavedRecordProps {
  saved: SavedWrapUp;
  onReopen: () => void;
}

/**
 * The wrap-up as it was stored. If the agent typed a personal detail, it shows
 * here as a redaction bar, because that is what the table holds.
 */
function SavedRecord({ saved, onReopen }: SavedRecordProps) {
  return (
    <div className="mt-4 animate-rise rounded-box border border-line-strong bg-surface px-4 py-4 text-ink">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <StatusLabel status="ok">Saved</StatusLabel>
        <span className="font-mono text-meta font-semibold text-ink-2">{saved.wrapup_id}</span>
      </p>
      <p className="mt-2 text-ui text-ink-2">
        {saved.saved_at !== undefined && (
          <>
            Saved on <time dateTime={saved.saved_at}>{formatDateTime(saved.saved_at)}</time>.{" "}
          </>
        )}
        This is the record as it was saved. Personal details in it were replaced.
      </p>
      <dl className="mt-4 grid gap-4">
        <Field term="How the call ended">
          <CallStatus resolution={saved.disposition} />
        </Field>
        <Field term="What the call was about">{categoryLabel(saved.category)}</Field>
        <Field term="Notes">
          <Lines lines={saved.notes} />
        </Field>
        <Field term="What the customer was told will happen">
          {saved.promises.length > 0 ? <Lines lines={saved.promises} /> : "Nothing was promised."}
        </Field>
        <Field term="Next step">
          {saved.follow_up ? (
            <>
              <span className="font-semibold">{OWNER_NAMES[saved.follow_up.owner]}: </span>
              <PlaceholderText text={saved.follow_up.action} />
            </>
          ) : (
            "Nothing is left to do."
          )}
        </Field>
        <Field term="The customer's mood at the end">
          <MoodLabel sentiment={saved.sentiment} />
        </Field>
      </dl>
      <Button size="sm" className="mt-4" onClick={onReopen}>
        Change it
      </Button>
    </div>
  );
}

/** The copilot's card while it drafts the wrap-up, with its signal bars seeking. */
function Drafting() {
  const bar = useCycle(4, 900);
  return <WorkingCard bar={bar}>Drafting the wrap-up</WorkingCard>;
}

function Articles({ draft }: { draft: CallWrapUp }) {
  if (draft.related_articles.length === 0) {
    return null;
  }
  return (
    <div className="mt-4">
      <p className="mb-1 cue">Related articles</p>
      <RelatedArticles articles={draft.related_articles} />
    </div>
  );
}

export interface WrapUpPanelProps {
  /** Undefined when the call has no saved wrap-up and none has been asked for. */
  state: WrapUpState | undefined;
  onDraft: () => void;
  onChange: (form: WrapUpForm) => void;
  onSave: (form: WrapUpForm) => void;
  onReopen: () => void;
  /** Look again for a saved wrap-up, after a look that failed. */
  onRecheck?: () => void;
}

/**
 * After-call work for one call. If a wrap-up was already saved for it, that
 * record is shown. If not: a button that asks the copilot to draft the record,
 * then the draft as a form the agent edits and saves, then the record as it was
 * saved.
 */
export function WrapUpPanel({
  state,
  onDraft,
  onChange,
  onSave,
  onReopen,
  onRecheck,
}: WrapUpPanelProps) {
  const unknown = state?.status === "unknown";
  return (
    <section aria-label="Call wrap-up">
      <h3 className="display-title text-ink">Wrap-up</h3>
      <div aria-live="polite">
        {state?.status === "checking" && (
          <>
            <p className="sr-only">Looking for a saved wrap-up.</p>
            {/* The only sign of loading in this panel, so it pulses. */}
            <Skeleton className="mt-4 h-24" />
          </>
        )}
        {(state === undefined || unknown) && (
          <>
            {unknown && (
              // A draft is still offered, but not as if the call were known to have no record.
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
                <p className="min-w-0 flex-1 basis-56 text-ink">
                  Could not find out whether a wrap-up was already saved for this call. If one
                  was, saving a new one puts a newer record beside it.
                </p>
                {onRecheck && (
                  <Button size="sm" variant="quiet" onClick={onRecheck}>
                    Look again
                  </Button>
                )}
              </div>
            )}
            <p className="mt-2 text-ink-2">
              Get a draft of the record for this call: how it ended, what it was about, notes, what
              was promised and the next step. You check it before it is saved.
            </p>
            <Button className="mt-4" onClick={onDraft}>
              <WrapUpIcon />
              Wrap up
            </Button>
          </>
        )}
        {state?.status === "loading" && (
          <div className="mt-4">
            <Drafting />
          </div>
        )}
        {state?.status === "error" && (
          <ErrorNotice className="mt-4" message={state.message} onRetry={onDraft} />
        )}
        {state?.status === "draft" && (
          <>
            <DraftForm
              state={state}
              onChange={onChange}
              onSave={() => {
                onSave(state.form);
              }}
            />
            <Articles draft={state.draft} />
          </>
        )}
        {state?.status === "saved" && <SavedRecord saved={state.saved} onReopen={onReopen} />}
      </div>
    </section>
  );
}
