import Link from "next/link";
import { RurayMark, Wordmark } from "./Logo";

export const RURAY_URL = "https://www.instagram.com/ruray.tech/";

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
