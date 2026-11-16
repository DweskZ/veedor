import Link from "next/link";
import { USE_MOCKS } from "@/lib/api";
import { HeaderSearch } from "./HeaderSearch";
import { Nav } from "./Nav";

import { RURAY_URL } from "./Footer";

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
        <Nav />
      </div>
    </header>
  );
}
