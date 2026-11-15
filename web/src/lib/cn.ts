import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * tailwind-merge has to be told the names of this project's own type scale and
 * radii. Otherwise it reads `text-meta` as a colour and drops it when a real
 * colour such as `text-ink-2` follows.
 */
const merge = extendTailwindMerge({
  override: {
    theme: {
      text: ["label", "meta", "ui", "read", "title", "view", "head"],
      radius: ["box", "chip"],
      shadow: ["pop"],
    },
  },
});

/** Join class names, letting a later Tailwind class win over an earlier one. */
export function cn(...inputs: ClassValue[]): string {
  return merge(clsx(inputs));
}
