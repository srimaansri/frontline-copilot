export interface FooterProps {
  /** The disclaimer the server sends. Nothing is shown until it has arrived. */
  disclaimer: string | null;
}

export function Footer({ disclaimer }: FooterProps) {
  return (
    <footer className="shrink-0 border-t bg-surface px-4 py-2 sm:px-6">
      <p className="min-h-4 text-center text-xs leading-4 text-fg-subtle">{disclaimer}</p>
    </footer>
  );
}
