/** Veedor mark: an open aperture ring enclosing three tally bars of increasing height. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
      <circle
        cx="16"
        cy="16"
        r="13"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="64 17.7"
        transform="rotate(-30 16 16)"
      />
      <rect x="9.5" y="16" width="3.2" height="6" rx="1" fill="var(--accent)" />
      <rect x="14.4" y="12" width="3.2" height="10" rx="1" fill="var(--accent)" />
      <rect x="19.3" y="8" width="3.2" height="14" rx="1" fill="var(--accent)" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark />
      <span className="text-xl font-semibold tracking-tight">Veedor</span>
    </span>
  );
}
