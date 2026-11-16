"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Panorama" },
  { href: "/procesos", label: "Procesos" },
  { href: "/agentes", label: "Agentes" },
  { href: "/metodologia", label: "Metodología" },
];

export function Nav() {
  return <NavLinks pathname={usePathname()} />;
}

export function NavLinks({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Principal" className="flex flex-wrap items-center gap-0.5 sm:gap-1">
      {ITEMS.map((it) => {
        const active = it.href === "/" ? pathname === "/" : !!pathname?.startsWith(it.href);
        return (
          <Link
            key={it.href}
            href={it.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-2 py-1.5 text-sm font-medium sm:px-3 ${
              active ? "bg-surface-2 text-ink" : "text-muted hover:bg-surface-2 hover:text-ink"
            }`}
          >
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}
