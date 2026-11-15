import { cn } from "@/lib/cn";

export interface BrandMarkProps {
  className?: string;
}

/** The copilot's mark: a small robot face on the accent colour. Decorative. */
export function BrandMark({ className }: BrandMarkProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-fg",
        className,
      )}
    >
      <svg viewBox="0 0 24 24" fill="none" className="size-[68%]">
        <line
          x1="12"
          y1="2.5"
          x2="12"
          y2="6"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <circle cx="12" cy="2.5" r="1.4" fill="currentColor" />
        <rect x="4" y="6" width="16" height="13" rx="4" fill="currentColor" />
        <circle cx="9" cy="12" r="1.8" className="fill-accent" />
        <circle cx="15" cy="12" r="1.8" className="fill-accent" />
        <rect x="9" y="15.2" width="6" height="1.6" rx="0.8" className="fill-accent" />
        <rect x="1.5" y="10" width="2" height="5" rx="1" fill="currentColor" />
        <rect x="20.5" y="10" width="2" height="5" rx="1" fill="currentColor" />
      </svg>
    </span>
  );
}
