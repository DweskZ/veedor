import Link from "next/link";
import { USE_MOCKS } from "@/lib/api";
import { Wordmark } from "./Logo";
import { Suspense } from "react";
import { Nav, NavLinks } from "./Nav";
import { ThemeToggle } from "./ThemeToggle";

export function MockBanner() {
  if (!USE_MOCKS) return null;
  return (
    <div role="status" className="border-b border-line bg-surface-2 px-4 py-1.5 text-center text-sm text-ink">
      <strong className="font-semibold">Datos de ejemplo.</strong> Las entidades, cifras y procesos son ficticios y no describen
      contratación real.
    </div>
  );
}

export function Header() {
  return (
    <header className="border-b border-line bg-bg">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" aria-label="Veedor, inicio" className="text-ink">
          <Wordmark />
        </Link>
        <div className="flex items-center gap-2">
          <Suspense fallback={<NavLinks pathname={null} />}>
            <Nav />
          </Suspense>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="mt-16 border-t border-line bg-surface">
      <div className="mx-auto grid max-w-6xl gap-4 px-4 py-8 text-sm text-muted sm:px-6 md:grid-cols-2">
        <p className="text-ink">
          Veedor muestra indicadores de riesgo calculados sobre datos públicos. No constituyen acusaciones ni determinan
          responsabilidades.
        </p>
        <p>
          Datos: Servicio Nacional de Contratación Pública (SERCOP), datos abiertos, licencia CC BY 3.0 EC. Registros del
          SRI y de la Superintendencia de Compañías. Más detalle en{" "}
          <Link href="/metodologia" className="text-accent underline underline-offset-2">
            Metodología
          </Link>
          .
        </p>
      </div>
    </footer>
  );
}
