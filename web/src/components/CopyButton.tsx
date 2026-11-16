"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for insecure contexts and older browsers.
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    ta.remove();
    return ok;
  }
}

/** Copies `text` and says so ("Copiado") for two seconds, in text and for screen readers. Hidden without JavaScript. */
export function CopyButton({ text, label, doneLabel = "Copiado", className = "", iconOnly = false }: { text: string; label: string; doneLabel?: string; className?: string; iconOnly?: boolean }) {
  const [state, setState] = useState<"idle" | "done" | "fail">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);
  const onClick = async () => {
    const ok = await writeClipboard(text);
    setState(ok ? "done" : "fail");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  };
  const shown = state === "done" ? doneLabel : state === "fail" ? "No se pudo copiar" : label;
  return (
    <span className={`needs-js copy ${className}`}>
      <button type="button" className={`copybtn ${state === "done" ? "copybtn--done" : ""}`} onClick={onClick} aria-label={iconOnly ? label : undefined}>
        <Icon name={state === "done" ? "check" : "copy"} size={18} />
        <span className={iconOnly ? "sr-only" : undefined}>{shown}</span>
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {state === "done" ? doneLabel : state === "fail" ? "No se pudo copiar" : ""}
      </span>
    </span>
  );
}
