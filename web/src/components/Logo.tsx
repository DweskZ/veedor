/** Veedor wordmark: lowercase, weight 800, followed by a small terracotta dot (same construction as Ruray's). */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`wm ${className}`} aria-hidden="true">
      veedor
    </span>
  );
}

/** Ruray wordmark, reproduced as on ruray-site (.wm). The Ruray logo is provisional: do not redesign it here. */
export function RurayMark({ className = "" }: { className?: string }) {
  return (
    <span className={`wm ${className}`} aria-hidden="true">
      ruray
    </span>
  );
}
