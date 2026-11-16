import { useCallback, useRef, useState } from "react";

import { api, errorMessage } from "@/api/client";
import type { CallWrapUp, SavedWrapUp } from "@/api/types";

import { fieldsFrom, formFrom, type WrapUpForm } from "./wrapUpForm";

/**
 * Where the wrap-up of one call stands. A call that has no saved wrap-up, and
 * that nobody has asked a draft for, has no state.
 */
export type WrapUpState =
  /** The page is finding out whether a wrap-up was already saved for the call. */
  | { status: "checking" }
  /** It could not find out. A draft is offered, and the page says it does not know. */
  | { status: "unknown" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "draft";
      /** What the copilot drafted, as it arrived. */
      draft: CallWrapUp;
      /** What the form started as: the copilot's draft, or the saved record being changed. */
      start: WrapUpForm;
      startedFrom: "copilot" | "saved";
      form: WrapUpForm;
      saving: boolean;
      /** Why the last save did not work, if it did not. */
      problem: string | null;
    }
  | { status: "saved"; draft: CallWrapUp; saved: SavedWrapUp };

const NOT_SAVED = "The wrap-up could not be saved. Your changes are still here. Please try again.";

/** What a state function returns to leave the state as it is, or `REMOVE` to drop it. */
const REMOVE = null;
type Next = (current: WrapUpState | undefined) => WrapUpState | undefined | typeof REMOVE;

/**
 * A saved record as the draft it stands for, for a call whose wrap-up was read
 * back and not drafted in this visit. It has no related articles: those come
 * with a draft, and nothing was drafted.
 */
function draftOf(saved: SavedWrapUp): CallWrapUp {
  return {
    transcript_id: saved.transcript_id,
    disposition: saved.disposition,
    category: saved.category,
    notes: saved.notes,
    promises: saved.promises,
    follow_up: saved.follow_up,
    sentiment: saved.sentiment,
    related_articles: [],
  };
}

/**
 * The wrap-up of every call that has one saved or has been asked for one, by
 * call id. It is kept here, above the call that is on show, so that choosing
 * another call and coming back does not lose a draft or what was typed over it.
 */
export function useWrapUps(): {
  wrapUps: Record<string, WrapUpState>;
  /**
   * Look for a wrap-up already saved for the call, once, when the call is first
   * opened. If there is one, it is shown as saved, in place of the offer of a draft.
   */
  load: (transcriptId: string) => void;
  /** Look again, after a look that failed. */
  recheck: (transcriptId: string) => void;
  /** Ask the copilot for a draft. Nothing is saved. */
  draft: (transcriptId: string) => void;
  change: (transcriptId: string, form: WrapUpForm) => void;
  /** Save what the agent approved. Only this stores anything. */
  save: (transcriptId: string, form: WrapUpForm) => void;
  /** Open a saved wrap-up for changing. Saving again stores a newer record. */
  reopen: (transcriptId: string) => void;
} {
  const [wrapUps, setWrapUps] = useState<Record<string, WrapUpState>>({});
  // The calls already looked up, so that opening a call again asks nothing.
  const looked = useRef(new Set<string>());

  const update = useCallback((transcriptId: string, next: Next) => {
    setWrapUps((all) => {
      const state = next(all[transcriptId]);
      if (state === undefined) {
        return all;
      }
      if (state === REMOVE) {
        return Object.fromEntries(Object.entries(all).filter(([id]) => id !== transcriptId));
      }
      return { ...all, [transcriptId]: state };
    });
  }, []);

  const load = useCallback(
    (transcriptId: string) => {
      if (looked.current.has(transcriptId)) {
        return;
      }
      looked.current.add(transcriptId);
      // A draft the agent has already asked for is never replaced by this look.
      const waiting = (current: WrapUpState | undefined) =>
        current === undefined || current.status === "unknown" || current.status === "checking";
      update(transcriptId, (current) => (waiting(current) ? { status: "checking" } : undefined));
      api.getSavedWrapUp(transcriptId).then(
        (saved) => {
          update(transcriptId, (current) => {
            if (current?.status !== "checking") {
              return undefined;
            }
            return saved === null ? REMOVE : { status: "saved", draft: draftOf(saved), saved };
          });
        },
        () => {
          update(transcriptId, (current) =>
            current?.status === "checking" ? { status: "unknown" } : undefined,
          );
        },
      );
    },
    [update],
  );

  const recheck = useCallback(
    (transcriptId: string) => {
      looked.current.delete(transcriptId);
      load(transcriptId);
    },
    [load],
  );

  const draft = useCallback(
    (transcriptId: string) => {
      update(transcriptId, () => ({ status: "loading" }));
      api.draftWrapUp(transcriptId).then(
        (data) => {
          const form = formFrom(data);
          update(transcriptId, () => ({
            status: "draft",
            draft: data,
            start: form,
            startedFrom: "copilot",
            form,
            saving: false,
            problem: null,
          }));
        },
        (error: unknown) => {
          update(transcriptId, () => ({ status: "error", message: errorMessage(error) }));
        },
      );
    },
    [update],
  );

  const change = useCallback(
    (transcriptId: string, form: WrapUpForm) => {
      update(transcriptId, (current) =>
        current?.status === "draft" && !current.saving
          ? { ...current, form, problem: null }
          : undefined,
      );
    },
    [update],
  );

  const save = useCallback(
    (transcriptId: string, form: WrapUpForm) => {
      update(transcriptId, (current) =>
        current?.status === "draft" ? { ...current, saving: true, problem: null } : undefined,
      );
      const failed = (problem: string) => {
        update(transcriptId, (current) =>
          current?.status === "draft" ? { ...current, saving: false, problem } : undefined,
        );
      };
      api.saveWrapUp(transcriptId, fieldsFrom(form)).then(
        (saved) => {
          if (!saved.recorded) {
            failed(NOT_SAVED);
            return;
          }
          update(transcriptId, (current) =>
            current?.status === "draft"
              ? { status: "saved", draft: current.draft, saved }
              : undefined,
          );
          // The reply to a save does not say when the record was stored. The record
          // itself does, so it is read back. If that fails, what is shown stays right.
          api.getSavedWrapUp(transcriptId).then(
            (stored) => {
              update(transcriptId, (current) =>
                current?.status === "saved" &&
                stored !== null &&
                stored.wrapup_id === current.saved.wrapup_id
                  ? { ...current, saved: stored }
                  : undefined,
              );
            },
            () => undefined,
          );
        },
        (error: unknown) => {
          failed(errorMessage(error));
        },
      );
    },
    [update],
  );

  const reopen = useCallback(
    (transcriptId: string) => {
      update(transcriptId, (current) => {
        if (current?.status !== "saved") {
          return undefined;
        }
        // The form starts from the record as it was stored, with personal details replaced.
        const form = formFrom(current.saved);
        return {
          status: "draft",
          draft: current.draft,
          start: form,
          startedFrom: "saved",
          form,
          saving: false,
          problem: null,
        };
      });
    },
    [update],
  );

  return { wrapUps, load, recheck, draft, change, save, reopen };
}
