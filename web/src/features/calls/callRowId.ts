/** The DOM id of a call's row in the list, so focus can be returned to it. */
export function callRowId(transcriptId: string): string {
  return `call-row-${transcriptId}`;
}
