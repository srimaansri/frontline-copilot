import { cn } from "@/lib/cn";

const BARS = [0, 1, 2, 3] as const;

export interface SignalBarsProps {
  /** How many bars are filled, from 0 to 4. */
  level: number;
  /** The bar being worked on (0 to 3), which pulses. */
  seeking?: number;
  size?: "sm" | "md";
  /** "live" bars fill with cobalt. "ink" bars are a still diagram. */
  tone?: "live" | "ink";
  className?: string;
}

/**
 * Four signal bars: the copilot's own state, one bar per stage of a request.
 * Decorative. Whatever they show is also said in words beside them.
 */
export function SignalBars({
  level,
  seeking,
  size = "md",
  tone = "live",
  className,
}: SignalBarsProps) {
  return (
    <span aria-hidden="true" data-size={size} data-tone={tone} className={cn("bars", className)}>
      {BARS.map((bar) => {
        let state = "off";
        if (bar === seeking) {
          state = "now";
        } else if (bar < level) {
          state = "on";
        }
        return <span key={bar} data-state={state} />;
      })}
    </span>
  );
}
