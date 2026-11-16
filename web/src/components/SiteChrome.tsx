import Link from "next/link";
import { Suspense } from "react";
import { USE_MOCKS } from "@/lib/api";
import { RurayMark, Wordmark } from "./Logo";
import { HeaderSearch } from "./HeaderSearch";
import { Nav, NavLinks } from "./Nav";

export const RURAY_URL = "https://www.instagram.com/ruray.tech/";

export function MockBanner() {
  if (!USE_MOCKS) return null;
  return (
    <div role="status" className="notice">
      <b>Datos de ejemplo.</b> Las entidades, cifras y procesos son ficticios y no describen contratación real.
    </div>
  );
}

export function Header() {
  return (
    <header className="header">
      <div className="wrap header__in">
        <div className="brandline">
          <Link href="/" aria-label="Veedor, inicio" className="wm">
            veedor
          </Link>
          <p className="brandline__by">
            un producto de{" "}
            <a href={RURAY_URL} rel="noopener" target="_blank">
              ruray.<span className="sr-only"> (se abre en una pestaña nueva)</span>
            </a>
          </p>
        </div>
        <div className="header__search">
          <HeaderSearch />
        </div>
        <Suspense fallback={<NavLinks pathname={null} />}>
          <Nav />
        </Suspense>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <div className="wrap">
        <div className="footer__in">
          <div>
            <Wordmark />
            <p className="footer__tag">Mira cómo compra el Estado.</p>
            <p style={{ marginTop: 10, maxWidth: "26em" }}>
              Veedor muestra indicadores de riesgo calculados sobre datos públicos. No constituyen acusaciones ni
              determinan responsabilidades.
            </p>
          </div>
          <div>
            <h2>Datos</h2>
            <p>
              Servicio Nacional de Contratación Pública (SERCOP), datos abiertos, licencia CC BY 3.0 EC. Registros del SRI y de
              la Superintendencia de Compañías.
            </p>
          </div>
          <nav aria-label="Pie de página" className="footer__links">
            <h2>Páginas</h2>
            <ul>
              <li>
                <Link href="/procesos">Procesos</Link>
              </li>
              <li>
                <Link href="/mapa">Mapa de señales</Link>
              </li>
              <li>
                <Link href="/tendencias">Tendencias</Link>
              </li>
              <li>
                <Link href="/agentes">Agentes de investigación</Link>
              </li>
              <li>
                <Link href="/metodologia">Metodología y límites</Link>
              </li>
              <li>
                <Link href="/glosario">Glosario</Link>
              </li>
            </ul>
          </nav>
          <div className="footer__credit">
            <span className="footer__made">
              Hecho por
              <a href={RURAY_URL} rel="noopener" target="_blank" aria-label="Ruray en Instagram (se abre en una pestaña nueva)">
                <RurayMark />
              </a>
            </span>
            <span className="footer__author">Luis Figueroa, fundador de Ruray.</span>
            <span className="footer__place">Hazlo real. · Ecuador · Australia</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
