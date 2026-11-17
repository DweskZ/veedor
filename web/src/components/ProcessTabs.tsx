"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { useAskOff } from "@/lib/ask-state";

export interface TabItem {
  /** Id of the tab. It is also the id of the section that opens the panel, so `#senales`-style links keep working. */
  id: string;
  label: string;
  /** Short count shown after the label (for example the number of signals). */
  badge?: string;
}

/**
 * Tabs for the process page (WAI-ARIA tabs pattern, automatic activation).
 *
 * Progressive enhancement: the server renders every panel in document order and the bar as plain anchor links, so the page
 * reads whole without JavaScript. With JavaScript the bar becomes a tablist, the inactive panels get `hidden`, and the active
 * tab lives in the URL hash. A hash that names an element inside a panel (for example `#sig-SINGLE_BIDDER`) opens that panel
 * and scrolls to the element. Before the script runs, CSS (`.js .ptabs:not(.ptabs--ready)`) already shows only the first panel
 * so the page does not flash its full length.
 *
 * Panels are the direct children of the container: `<div data-panel="<tab id>">`.
 */
export function ProcessTabs({ items: all, children, label = "Secciones de este proceso" }: { items: TabItem[]; children: ReactNode; label?: string }) {
  // The question box can turn itself off (the API answered 404): its tab leaves the bar with it.
  const askOff = useAskOff();
  const items = useMemo(() => all.filter((i) => !(askOff && i.id === "preguntar")), [all, askOff]);
  const first = items[0]?.id ?? "";
  const [active, setActive] = useState(first);
  // False on the server and during hydration, true afterwards: the markup first matches the server HTML, then becomes tabs.
  const ready = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const root = useRef<HTMLDivElement>(null);
  const panels = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLUListElement>(null);
  /** Set when the change came from the visitor (click, key, link): the page is then brought back to the top of the panel. */
  const moved = useRef<{ target: HTMLElement | null } | null>(null);

  const current = items.some((i) => i.id === active) ? active : first;

  const resolve = useCallback(
    (hash: string): { tab: string; target: HTMLElement | null } | null => {
      let id = hash.replace(/^#/, "");
      try {
        id = decodeURIComponent(id);
      } catch {
        /* keep the raw value */
      }
      if (!id) return null;
      if (items.some((i) => i.id === id)) return { tab: id, target: null };
      const el = document.getElementById(id);
      const tab = el?.closest<HTMLElement>("[data-panel]")?.dataset.panel;
      return el && tab && items.some((i) => i.id === tab) ? { tab, target: el } : null;
    },
    [items],
  );

  // Read the hash once the page is interactive, and follow it (links, back and forward).
  useEffect(() => {
    const sync = (fromUser: boolean) => {
      const r = resolve(window.location.hash);
      setActive(r?.tab ?? first);
      if (fromUser) moved.current = { target: r?.target ?? null };
      else if (r?.target) moved.current = { target: r.target };
    };
    sync(false);
    const onHash = () => sync(true);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [resolve, first]);

  // Show the active panel only, and give the panels their roles.
  useLayoutEffect(() => {
    const host = panels.current;
    if (!ready || !host) return;
    for (const p of host.querySelectorAll<HTMLElement>(":scope > [data-panel]")) {
      const id = p.dataset.panel ?? "";
      const on = id === current;
      p.hidden = !on;
      p.setAttribute("role", "tabpanel");
      p.setAttribute("aria-labelledby", `tab-${id}`);
    }
  }, [ready, current, items]);

  // After a change made by the visitor: land on the target, or at the top of the panel if the bar was scrolled past.
  useEffect(() => {
    const m = moved.current;
    if (!ready || !m) return;
    moved.current = null;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const behavior: ScrollBehavior = calm ? "auto" : "smooth";
    if (m.target) {
      m.target.scrollIntoView({ block: "start", behavior });
      return;
    }
    const r = root.current;
    if (!r) return;
    const header = document.querySelector<HTMLElement>(".header")?.offsetHeight ?? 76;
    const top = r.getBoundingClientRect().top + window.scrollY - header - 2;
    if (window.scrollY > top + 2) window.scrollTo({ top, behavior });
  }, [ready, current]);

  // Keep the active tab visible inside the horizontally scrolling bar, without moving the page.
  useEffect(() => {
    const ul = bar.current;
    const a = ul?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!ul || !a) return;
    const left = a.offsetLeft - (ul.clientWidth - a.offsetWidth) / 2;
    ul.scrollTo({ left: Math.max(0, left), behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [current]);

  const select = (id: string, mode: "push" | "replace") => {
    const url = id === first ? `${window.location.pathname}${window.location.search}` : `#${encodeURIComponent(id)}`;
    if (mode === "push") window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
    moved.current = { target: null };
    setActive(id);
  };

  const onKey = (e: KeyboardEvent<HTMLUListElement>) => {
    const i = items.findIndex((t) => t.id === current);
    let n = i;
    if (e.key === "ArrowRight") n = (i + 1) % items.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + items.length) % items.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = items.length - 1;
    else return;
    e.preventDefault();
    select(items[n].id, "replace");
    document.getElementById(`tab-${items[n].id}`)?.focus();
  };

  const onClick = (e: MouseEvent<HTMLAnchorElement>, id: string) => {
    if (!ready || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    select(id, "push");
  };

  return (
    <div ref={root} className={`ptabs ${ready ? "ptabs--ready" : ""}`}>
      <nav className="pnav" aria-label={label}>
        <div className="wrap">
          <ul ref={bar} className="pnav__list" role={ready ? "tablist" : undefined} aria-label={ready ? label : undefined} onKeyDown={ready ? onKey : undefined}>
            {items.map((it) => {
              const on = it.id === current;
              return (
                <li key={it.id} role={ready ? "presentation" : undefined}>
                  <a
                    id={`tab-${it.id}`}
                    href={`#${it.id}`}
                    role={ready ? "tab" : undefined}
                    aria-selected={ready ? on : undefined}
                    aria-controls={ready ? `panel-${it.id}` : undefined}
                    tabIndex={ready ? (on ? 0 : -1) : undefined}
                    onClick={(e) => onClick(e, it.id)}
                  >
                    {it.label}
                    {it.badge ? <span className="pnav__n">{it.badge}</span> : null}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      </nav>
      <div className="wrap doc">
        <div className="doc__main" ref={panels}>
          {children}
        </div>
      </div>
    </div>
  );
}
