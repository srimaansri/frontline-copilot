import { useCallback, useState } from "react";

import { api, errorMessage } from "@/api/client";
import type { CallWrapUp, SavedWrapUp } from "@/api/types";

import { fieldsFrom, formFrom, type WrapUpForm } from "./wrapUpForm";

/** Where the wrap-up of one call stands. A call nobody has wrapped up has no state. */
export type WrapUpState =
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

/**
 * The wrap-up of every call that has been asked for one, by call id. It is kept
 * here, above the call that is on show, so that choosing another call and
 * coming back does not lose a draft or what was typed over it.
 */
export function useWrapUps(): {
  wrapUps: Record<string, WrapUpState>;
  /** Ask the copilot for a draft. Nothing is saved. */
  draft: (transcriptId: string) => void;
  change: (transcriptId: string, form: WrapUpForm) => void;
  /** Save what the agent approved. Only this stores anything. */
  save: (transcriptId: string, form: WrapUpForm) => void;
  /** Open a saved wrap-up for changing. Saving again stores a newer record. */
  reopen: (transcriptId: string) => void;
} {
  const [wrapUps, setWrapUps] = useState<Record<string, WrapUpState>>({});

  const update = useCallback(
    (transcriptId: string, next: (current: WrapUpState | undefined) => WrapUpState | undefined) => {
      setWrapUps((all) => {
        const state = next(all[transcriptId]);
        return state === undefined ? all : { ...all, [transcriptId]: state };
      });
    },
    [],
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

  return { wrapUps, draft, change, save, reopen };
}
