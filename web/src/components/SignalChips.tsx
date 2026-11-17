"use client";

import Link from "next/link";
import { useId, useState } from "react";

export interface ChipItem {
  code: string;
  /** Short label shown on the chip. */
  text: string;
  /** Full label from the API, used as the tooltip. */
  full: string;
  /** Context signals do not add points and get the quieter style. */
  quiet: boolean;
}

/**
 * The signals of one process as a compact, wrapping row: the first `max` chips and a button with the rest ("+2 más").
 * Without JavaScript every chip is in the row (progressive enhancement; the `.js` class collapses it). The button's name lists the
 * hidden signals, so screen-reader users get the full list without opening it, and keyboard users open it with Enter or Space.
 */
export function SignalChips({ items, max = 2 }: { items: ChipItem[]; max?: number }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!items.length) return <span className="muted">Ninguna</span>;
  const rest = items.length - max;
  const chip = (c: ChipItem) => (
    <Link
      key={c.code}
      href={`/procesos?signal=${encodeURIComponent(c.code)}`}
      title={`${c.full}. Ver más procesos con esta señal${c.quiet ? " (solo contexto, no suma puntos)" : ""}`}
      className={`chip ${c.quiet ? "chip--quiet" : ""}`}
    >
      {c.text}
    </Link>
  );
  if (rest <= 0) return <div className="chips chips--row">{items.map(chip)}</div>;
  return (
    <div className={`chips chips--row ${open ? "is-open" : ""}`}>
      {items.slice(0, max).map(chip)}
      <span id={id} className="chips__rest">
        {items.slice(max).map(chip)}
      </span>
      <button
        type="button"
        className="chips__more needs-js"
        aria-expanded={open}
        aria-controls={id}
        aria-label={open ? undefined : `+${rest} más: ${items.slice(max).map((c) => c.full).join("; ")}`}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "ver menos" : `+${rest} más`}
      </button>
    </div>
  );
}
