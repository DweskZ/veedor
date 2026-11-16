"use client";

import { useEffect, useRef, useState } from "react";

export interface NavItem {
  id: string;
  label: string;
  /** Other headings that belong to this group (the group stays active while they are on screen). */
  also?: string[];
}

/**
 * Sticky section navigation for a long page. Plain anchor links (they work without JavaScript); with JavaScript the
 * group being read is marked with aria-current="location" and kept in view in the scrolling bar.
 */
export function SectionNav({ items, label = "Secciones de esta página" }: { items: NavItem[]; label?: string }) {
  const [current, setCurrent] = useState(items[0]?.id ?? "");
  const bar = useRef<HTMLUListElement>(null);

  useEffect(() => {
    let raf = 0;
    const compute = () => {
      raf = 0;
      const line = (document.querySelector<HTMLElement>(".header")?.offsetHeight ?? 76) + 96;
      let active = items[0]?.id ?? "";
      for (const it of items) {
        for (const id of [it.id, ...(it.also ?? [])]) {
          const el = document.getElementById(id);
          if (el && el.getBoundingClientRect().top <= line) active = it.id;
        }
      }
      if (window.scrollY > 200 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) active = items[items.length - 1].id;
      setCurrent(active);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(compute);
    };
    compute();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [items]);

  // Keep the active link visible inside the horizontally scrolling bar, without moving the page.
  useEffect(() => {
    const ul = bar.current;
    const a = ul?.querySelector<HTMLElement>('[aria-current="location"]');
    if (!ul || !a) return;
    const left = a.offsetLeft - (ul.clientWidth - a.offsetWidth) / 2;
    ul.scrollTo({ left: Math.max(0, left), behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [current]);

  return (
    <nav className="pnav" aria-label={label}>
      <div className="wrap">
        <ul ref={bar} className="pnav__list">
          {items.map((it) => (
            <li key={it.id}>
              <a href={`#${it.id}`} aria-current={current === it.id ? "location" : undefined}>
                {it.label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
