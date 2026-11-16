import type {
  CallWrapUp,
  FollowUpOwner,
  Resolution,
  SavedWrapUp,
  Sentiment,
  WrapUpFields,
} from "@/api/types";
import { humanize } from "@/lib/format";

/** The longest line the server accepts: one note, one promise, or the next step. */
export const MAX_LINE_CHARS = 300;

/** The most notes, and the most promises, the server accepts. */
export const MAX_LINES = 6;

/** "Nobody" is a choice in the form. The server is sent no follow-up at all for it. */
export type OwnerChoice = FollowUpOwner | "none";

/**
 * A wrap-up as the agent edits it. Notes and promises are typed one to a line,
 * which is quicker than a row of boxes, and are split into a list when saved.
 * Empty lines mean nothing.
 */
export interface WrapUpForm {
  disposition: Resolution;
  category: string;
  notes: string;
  promises: string;
  owner: OwnerChoice;
  action: string;
  sentiment: Sentiment;
}

/** The parts of the form that are marked as the copilot's draft or as changed. */
export type WrapUpField = "disposition" | "category" | "notes" | "promises" | "followUp" | "sentiment";

/** The three endings, each with what it means, so two agents pick the same one. */
export const DISPOSITIONS: readonly { value: Resolution; label: string }[] = [
  { value: "resolved", label: "Resolved: sorted out on this call" },
  { value: "escalated", label: "Escalated: passed to another team" },
  { value: "unresolved", label: "Unresolved: not sorted out" },
];

/** The ten call categories, in the words an agent reads. */
export const CATEGORIES: readonly { value: string; label: string }[] = [
  { value: "billing", label: "Billing" },
  { value: "troubleshooting", label: "Troubleshooting" },
  { value: "device_setup", label: "Device setup" },
  { value: "plan_change", label: "Plan change" },
  { value: "add_line", label: "Add a line" },
  { value: "international", label: "International" },
  { value: "lost_stolen", label: "Lost or stolen phone" },
  { value: "cancel_port", label: "Cancel, or move a number" },
  { value: "accessibility", label: "Accessibility" },
  { value: "scam", label: "Scam" },
];

export const OWNERS: readonly { value: OwnerChoice; label: string }[] = [
  { value: "none", label: "Nobody. Nothing is left to do" },
  { value: "customer", label: "The customer" },
  { value: "agent", label: "Me" },
  { value: "team", label: "Another team" },
];

export const SENTIMENTS: readonly { value: Sentiment; label: string }[] = [
  { value: "positive", label: "Positive" },
  { value: "neutral", label: "Neutral" },
  { value: "negative", label: "Negative" },
];

/** The words for a category, also for one the list above does not have. */
export function categoryLabel(category: string): string {
  return CATEGORIES.find((item) => item.value === category)?.label ?? humanize(category);
}

/** The lines of a box that holds one item to a line, without the blank ones. */
export function linesOf(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

/** The form for a draft, or for a saved wrap-up the agent wants to change. */
export function formFrom(wrapUp: CallWrapUp | SavedWrapUp): WrapUpForm {
  return {
    disposition: wrapUp.disposition,
    category: wrapUp.category,
    // A long item wraps inside the box, so an empty line is put between two items to
    // show where one ends. Empty lines are dropped again when the form is saved.
    notes: wrapUp.notes.join("\n\n"),
    promises: wrapUp.promises.join("\n\n"),
    owner: wrapUp.follow_up?.owner ?? "none",
    action: wrapUp.follow_up?.action ?? "",
    sentiment: wrapUp.sentiment,
  };
}

/** What is sent to the server when the agent saves. */
export function fieldsFrom(form: WrapUpForm): WrapUpFields {
  const action = form.action.trim();
  return {
    disposition: form.disposition,
    category: form.category,
    notes: linesOf(form.notes),
    promises: linesOf(form.promises),
    follow_up: form.owner === "none" || action === "" ? null : { owner: form.owner, action },
    sentiment: form.sentiment,
  };
}

/** Why the form cannot be saved as it is, in words for the agent. Null when it can. */
export function problemWith(form: WrapUpForm): string | null {
  const notes = linesOf(form.notes);
  const promises = linesOf(form.promises);
  if (notes.length === 0) {
    return "Add at least one note.";
  }
  if (notes.length > MAX_LINES) {
    return `Keep it to ${MAX_LINES} notes or fewer.`;
  }
  if (promises.length > MAX_LINES) {
    return `Keep it to ${MAX_LINES} promises or fewer.`;
  }
  if ([...notes, ...promises, form.action.trim()].some((line) => line.length > MAX_LINE_CHARS)) {
    return `One line is too long. Keep each line to ${MAX_LINE_CHARS} letters or fewer.`;
  }
  if (form.owner !== "none" && form.action.trim() === "") {
    return "Say what the next step is, or choose Nobody.";
  }
  return null;
}

/** Whether the agent has changed one part of the form from what it started as. */
export function isChanged(field: WrapUpField, form: WrapUpForm, start: WrapUpForm): boolean {
  switch (field) {
    case "notes":
      return linesOf(form.notes).join("\n") !== linesOf(start.notes).join("\n");
    case "promises":
      return linesOf(form.promises).join("\n") !== linesOf(start.promises).join("\n");
    case "followUp":
      return form.owner !== start.owner || form.action.trim() !== start.action.trim();
    default:
      return form[field] !== start[field];
  }
}
