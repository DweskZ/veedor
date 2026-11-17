"use client";

/** Reloads the current page. Hidden without JavaScript (the error text already says to try again). */
export function RetryButton({ label = "Volver a intentar" }: { label?: string }) {
  return (
    <button type="button" className="btn btn--line btn--sm needs-js" onClick={() => window.location.reload()}>
      {label}
    </button>
  );
}
