"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/**
 * Inline glossary help. A dotted-underline button; the definition opens on hover, focus or tap, closes with Esc,
 * a second tap or a tap elsewhere, and never traps focus. The definition always sits in the DOM, so a screen
 * reader gets it as the button's description; without JavaScript the term is plain text and /glosario has the list.
 */
export function TermPopover({ children, definition, anchor }: { children: ReactNode; definition: string; anchor: string }) {
  const id = useId();
  const root = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [shift, setShift] = useState(0);
  const [above, setAbove] = useState(false);
  const open = (hover || focus || pinned) && !dismissed;

  const close = useCallback(() => {
    setHover(false);
    setPinned(false);
    setDismissed(true);
  }, []);

  // Keep the popover inside the viewport: shift it sideways and flip it above when there is no room below.
  useLayoutEffect(() => {
    if (!open || !pop.current || !root.current) return;
    const p = pop.current.getBoundingClientRect();
    const r = root.current.getBoundingClientRect();
    const margin = 12;
    const natural = p.left - shift;
    let dx = 0;
    if (natural + p.width > window.innerWidth - margin) dx = window.innerWidth - margin - (natural + p.width);
    if (natural + dx < margin) dx = margin - natural;
    setShift(dx);
    setAbove(r.bottom + p.height + 16 > window.innerHeight && r.top > p.height + 16);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        btn.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  return (
    <span
      ref={root}
      className="term"
      onPointerEnter={(e) => {
        if (e.pointerType === "mouse") {
          setDismissed(false);
          setHover(true);
        }
      }}
      onPointerLeave={(e) => {
        if (e.pointerType === "mouse") setHover(false);
      }}
      onBlur={(e) => {
        if (!root.current?.contains(e.relatedTarget as Node)) {
          setFocus(false);
          setPinned(false);
        }
      }}
    >
      <button
        ref={btn}
        type="button"
        className="term__btn"
        aria-describedby={id}
        onFocus={() => {
          setDismissed(false);
          setFocus(true);
        }}
        onClick={() => {
          setDismissed(false);
          setPinned((p) => !(p && open));
        }}
      >
        {children}
      </button>
      <span
        ref={pop}
        id={id}
        className={`term__pop ${open ? "term__pop--open" : ""} ${above ? "term__pop--above" : ""}`}
        style={{ transform: `translateX(${shift}px)` }}
      >
        {definition}{" "}
        <Link href={`/glosario#${anchor}`} className="term__more">
          Ver en el glosario
        </Link>
      </span>
    </span>
  );
}
