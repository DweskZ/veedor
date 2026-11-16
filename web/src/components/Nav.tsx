"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId, useState } from "react";

const ITEMS = [
  { href: "/", label: "Inicio" },
  { href: "/procesos", label: "Procesos" },
  { href: "/agentes", label: "Agentes" },
  { href: "/metodologia", label: "Metodología" },
];

const isActive = (href: string, pathname: string | null) =>
  href === "/" ? pathname === "/" : !!pathname?.startsWith(href);

export function Nav() {
  return <NavLinks pathname={usePathname()} />;
}

/** Wide screens: a row of pill links. Narrow screens: a "Menú" button that opens the same links (it closes when the route changes). */
export function NavLinks({ pathname }: { pathname: string | null }) {
  const id = useId();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn !== null && openOn === (pathname ?? "");
  return (
    <>
      <nav aria-label="Principal" className="nav">
        {ITEMS.map((it) => (
          <Link key={it.href} href={it.href} aria-current={isActive(it.href, pathname) ? "page" : undefined}>
            {it.label}
          </Link>
        ))}
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
          <nav id={id} aria-label="Principal (menú)" className="menu__list">
            {ITEMS.map((it) => (
              <Link key={it.href} href={it.href} aria-current={isActive(it.href, pathname) ? "page" : undefined}>
                {it.label}
              </Link>
            ))}
          </nav>
        ) : null}
      </div>
    </>
  );
}
