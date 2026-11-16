"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { searchBuyers } from "@/lib/client-api";
import { fmtInt } from "@/lib/format";
import type { BuyerHit } from "@/lib/types";

const OCID = /^(?:ocds-[a-z0-9]+|sample-ocid)-[A-Za-z0-9._-]{1,100}$/;
// A process code looks like LETTERS-WORD-WORD-... (for example SIE-XXXX-2024-001).
const CODE = /^[A-Za-z]{2,8}(?:-[A-Za-z0-9]+){2,}$/;

interface Opt {
  key: string;
  href: string;
  title: string;
  sub?: string;
  kind: "process" | "code" | "buyer" | "all";
}

/** Entity and process-code search with the ARIA combobox pattern. The form also works without JavaScript (GET /procesos?q=). */
export function HeaderSearch({ inline = false, onNavigate }: { inline?: boolean; onNavigate?: () => void }) {
  const router = useRouter();
  const uid = useId();
  const listId = `${uid}-list`;
  const root = useRef<HTMLFormElement>(null);
  const [value, setValue] = useState("");
  const [hits, setHits] = useState<BuyerHit[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const text = value.trim();
  const isOcid = OCID.test(text);

  useEffect(() => {
    if (text.length < 3 || isOcid) return;
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      setState("loading");
      try {
        const res = await searchBuyers(text, ctl.signal);
        setHits(res);
        setState("done");
        setActive(-1);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setState("error");
      }
    }, 200);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [text, isOcid]);

  const showBuyers = text.length >= 3 && !isOcid;
  const opts: Opt[] = [];
  if (isOcid) opts.push({ key: "ocid", href: `/procesos/${encodeURIComponent(text)}`, title: `Abrir el proceso ${text}`, kind: "process" });
  else if (CODE.test(text)) opts.push({ key: "code", href: `/procesos?q=${encodeURIComponent(text)}`, title: `Buscar el código ${text}`, sub: "Procesos cuyo código coincide", kind: "code" });
  if (showBuyers && state !== "error")
    for (const b of hits)
      opts.push({
        key: b.ruc,
        href: `/entidades/${b.ruc}`,
        title: b.name,
        sub: [b.region_label, b.processes_total != null ? `${fmtInt(b.processes_total)} procesos` : null].filter(Boolean).join(" · "),
        kind: "buyer",
      });
  if (text.length >= 3 && !isOcid) opts.push({ key: "all", href: `/procesos?q=${encodeURIComponent(text)}`, title: `Buscar «${text}» en todos los procesos`, kind: "all" });

  const expanded = open && opts.length > 0;
  const status =
    text.length < 3
      ? ""
      : isOcid
        ? "Código de proceso reconocido. Pulsa Enter para abrirlo."
        : state === "loading"
          ? "Buscando entidades…"
          : state === "error"
            ? "No pudimos buscar entidades ahora. Puedes buscar en todos los procesos."
            : state === "done"
              ? hits.length
                ? `${hits.length} ${hits.length === 1 ? "entidad sugerida" : "entidades sugeridas"}. Usa las flechas para elegir.`
                : "Ninguna entidad coincide. Puedes buscar en todos los procesos."
              : "";

  useEffect(() => {
    const down = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, []);

  // "/" focuses the search from anywhere that is not a text field (the usual shortcut on data sites).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      const input = root.current?.querySelector<HTMLInputElement>("input");
      if (!input || input.offsetParent === null) return;
      e.preventDefault();
      input.focus();
      input.select();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const go = (href: string) => {
    setOpen(false);
    setActive(-1);
    setValue("");
    setHits([]);
    setState("idle");
    onNavigate?.();
    router.push(href);
  };

  return (
    <form
      ref={root}
      role="search"
      action="/procesos"
      method="get"
      className={`hs ${inline ? "hs--inline" : ""}`}
      onSubmit={(e) => {
        if (!text) return e.preventDefault();
        e.preventDefault();
        go(active >= 0 && opts[active] ? opts[active].href : (opts[0]?.kind === "process" ? opts[0].href : `/procesos?q=${encodeURIComponent(text)}`));
      }}
    >
      <label htmlFor={`${uid}-in`} className="sr-only">
        Buscar una entidad o un código de proceso
      </label>
      <svg className="hs__icon" width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <circle cx="8.5" cy="8.5" r="6" fill="none" stroke="currentColor" strokeWidth="2.6" />
        <path d="M13 13l5 5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      </svg>
      <input
        id={`${uid}-in`}
        name="q"
        type="search"
        autoComplete="off"
        maxLength={60}
        placeholder="Buscar entidad o código"
        className="hs__input"
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-keyshortcuts="/"
        aria-activedescendant={expanded && active >= 0 ? `${uid}-o${active}` : undefined}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setOpen(true);
          setActive(-1);
          if (e.target.value.trim().length < 3) {
            setHits([]);
            setState("idle");
          }
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            if (!opts.length) return;
            e.preventDefault();
            setOpen(true);
            setActive((a) => (e.key === "ArrowDown" ? (a + 1) % opts.length : (a - 1 + opts.length) % opts.length));
          } else if (e.key === "Escape") {
            if (expanded) {
              e.preventDefault();
              setOpen(false);
              setActive(-1);
            } else if (value) setValue("");
          } else if (e.key === "Tab") setOpen(false);
        }}
      />
      <kbd className="hs__kbd" aria-hidden="true">/</kbd>
      <p className="sr-only" role="status" aria-live="polite">
        {status}
      </p>
      <ul id={listId} role="listbox" aria-label="Sugerencias de búsqueda" className="hs__list" hidden={!expanded}>
        {opts.map((o, i) => (
          <li
            key={o.key}
            id={`${uid}-o${i}`}
            role="option"
            aria-selected={i === active}
            className={`hs__opt hs__opt--${o.kind} ${i === active ? "hs__opt--on" : ""}`}
            onPointerDown={(e) => e.preventDefault()}
            onPointerEnter={() => setActive(i)}
            onClick={() => go(o.href)}
          >
            <span className="hs__t">{o.title}</span>
            {o.sub ? <span className="hs__s">{o.sub}</span> : null}
          </li>
        ))}
      </ul>
    </form>
  );
}
