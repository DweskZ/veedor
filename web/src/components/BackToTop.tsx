"use client";

import { useEffect, useState } from "react";
import { Icon } from "./Icon";

/** Appears after a long scroll. A real button: it works for keyboard and touch and respects reduced motion. */
export function BackToTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const on = () => setShow(window.scrollY > 1400);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  if (!show) return null;
  return (
    <button
      type="button"
      className="totop"
      onClick={() => {
        window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        document.getElementById("contenido")?.focus({ preventScroll: true });
      }}
    >
      <Icon name="up" size={20} />
      <span>Volver arriba</span>
    </button>
  );
}
