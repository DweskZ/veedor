"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { HeaderSearch } from "./HeaderSearch";

const PRIMARY = [
  { href: "/procesos", label: "Procesos" },
  { href: "/mapa", label: "Mapa" },
  { href: "/tendencias", label: "Tendencias" },
];
const MORE = [
  { href: "/agentes", label: "Agentes" },
  { href: "/metodologia", label: "Metodología" },
  { href: "/glosario", label: "Glosario" },
];
const ALL = [{ href: "/", label: "Inicio" }, ...PRIMARY, ...MORE];

const isActive = (href: string, pathname: string | null) =>
  href === "/" ? pathname === "/" : !!pathname?.startsWith(href);

export function Nav() {
  return <NavLinks pathname={usePathname()} />;
}

/** "Más": secondary pages in a small disclosure menu. Closes with Esc, a click elsewhere, focus leaving or a route change. */
function More({ pathname }: { pathname: string | null }) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn !== null && openOn === (pathname ?? "");
  const current = MORE.some((m) => isActive(m.href, pathname));
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpenOn(null);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  return (
    <div
      ref={root}
      className="more"
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          setOpenOn(null);
          root.current?.querySelector("button")?.focus();
        }
      }}
      onBlur={(e) => {
        if (!root.current?.contains(e.relatedTarget as Node)) setOpenOn(null);
      }}
    >
      <button
        type="button"
        className={`more__btn ${current ? "more__btn--cur" : ""}`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpenOn(open ? null : (pathname ?? ""))}
      >
        Más
        <svg width="12" height="8" viewBox="0 0 12 8" aria-hidden="true" focusable="false">
          <path d="M1.5 1.5l4.5 4.5 4.5-4.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open ? (
        <ul id={id} className="more__list">
          {MORE.map((it) => (
            <li key={it.href}>
              <Link href={it.href} aria-current={isActive(it.href, pathname) ? "page" : undefined}>
                {it.label}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Wide screens: pill links with the secondary ones under "Más". Narrow screens: a "Menú" button with search and every link. */
export function NavLinks({ pathname }: { pathname: string | null }) {
  const id = useId();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn !== null && openOn === (pathname ?? "");
  return (
    <>
      <nav aria-label="Principal" className="nav">
        {PRIMARY.map((it) => (
          <Link key={it.href} href={it.href} aria-current={isActive(it.href, pathname) ? "page" : undefined}>
            {it.label}
          </Link>
        ))}
        <More pathname={pathname} />
      </nav>
      <div
        className="menu"
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpenOn(null);
        }}
      >
        <button
          type="button"
          className="menu__btn"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpenOn(open ? null : (pathname ?? ""))}
        >
          Menú
          <svg width="16" height="12" viewBox="0 0 16 12" aria-hidden="true" focusable="false">
            <path d="M1 2h14M1 6h14M1 10h14" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        </button>
        {open ? (
          <div id={id} className="menu__list">
            <HeaderSearch inline onNavigate={() => setOpenOn(null)} />
            <nav aria-label="Principal (menú)" className="menu__links">
              {ALL.map((it) => (
                <Link key={it.href} href={it.href} aria-current={isActive(it.href, pathname) ? "page" : undefined}>
                  {it.label}
                </Link>
              ))}
            </nav>
          </div>
        ) : null}
      </div>
    </>
  );
}
