export interface FooterProps {
  /** The disclaimer the server sends. Nothing is shown until it has arrived. */
  disclaimer: string | null;
}

export function Footer({ disclaimer }: FooterProps) {
  return (
    <footer className="shrink-0 border-t border-line bg-paper px-4 py-2 sm:px-6">
      <p className="min-h-4 text-label text-ink-3">{disclaimer}</p>
    </footer>
  );
}
