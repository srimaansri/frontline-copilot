/** "plan_change" -> "Plan change". */
export function humanize(value: string): string {
  const words = value.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** 2.4 -> "2.4 seconds". */
export function formatSeconds(seconds: number): string {
  const rounded = Math.round(seconds * 10) / 10;
  return `${rounded.toFixed(1)} ${rounded === 1 ? "second" : "seconds"}`;
}

/** The host of a URL, or the URL itself if it cannot be parsed. */
export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** "1 source", "2 sources". */
export function countOf(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
