import type { CallListItem, RuleFinding } from "@/api/types";
import { humanize } from "@/lib/format";

/**
 * Each rule of the rule check in plain words. The names are those of
 * `src/copilot/compliance.py`; the sentence that says why a turn was flagged
 * comes from the server with each finding.
 */
const RULE_TITLES: Record<string, string> = {
  disclosure_before_verification: "Account details given before the identity check",
  verification_skipped: "No identity check anywhere in the call",
  card_read_back: "A full card number read back",
  unauthorized_promise: "A charge waived or refunded without the billing team",
  full_ssn_requested: "The full Social Security number asked for",
};

/** The words for a rule, also for one this list does not have yet. */
export function ruleTitle(rule: string): string {
  return RULE_TITLES[rule] ?? humanize(rule);
}

/** A turn as people count them: the first turn is turn 1. */
export function turnNumber(turnIndex: number): number {
  return turnIndex + 1;
}

/** The DOM id of one turn, so that a finding can send focus to the turn it points at. */
export function turnElementId(prefix: string, turnIndex: number): string {
  return `${prefix}-turn-${turnIndex}`;
}

/** True when the rule check has run on this call, whatever it found. */
export function isChecked(call: CallListItem): boolean {
  return call.findings !== undefined && call.findings !== null;
}

/** How many rules fired on a call. 0 for a call that was not checked. */
export function rulesFired(call: CallListItem): number {
  return call.findings?.length ?? 0;
}

/** The findings of each turn that has one, by turn index. */
export function findingsByTurn(findings: readonly RuleFinding[]): Map<number, RuleFinding[]> {
  const byTurn = new Map<number, RuleFinding[]>();
  for (const finding of findings) {
    byTurn.set(finding.turn_index, [...(byTurn.get(finding.turn_index) ?? []), finding]);
  }
  return byTurn;
}
