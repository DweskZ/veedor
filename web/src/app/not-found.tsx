import Link from "next/link";
import { PageShell } from "@/components/PageFrame";
import { Art } from "@/components/Art";

export const metadata = { title: "No encontrado" };

export default function NotFound() {
  return (
    <PageShell>
    <section className="nf" aria-labelledby="nf-h">
      <div className="wrap nf__grid">
        <div>
          <p className="eyebrow">Error 404</p>
          <p className="nf__code" aria-hidden="true">
            404<em>.</em>
          </p>
          <h1 className="h2" id="nf-h" style={{ marginTop: 16 }}>
            Aquí no hay <em>nada.</em>
          </h1>
          <p className="lead">
            Esa dirección no existe, o el proceso, la empresa o la entidad que buscas no está en los datos de Veedor. Revisa que el código esté bien escrito o
            empieza de nuevo desde el inicio.
          </p>
          <div className="actions">
            <Link href="/" className="btn btn--tc">
              Ir al inicio
            </Link>
            <Link href="/procesos" className="btn btn--line">
              Explorar procesos
            </Link>
          </div>
        </div>
        <Art name="vacio" sizes="(min-width: 900px) 40vw, 90vw" alt="Dibujo isométrico de un terreno vacío con una cerca y un letrero en blanco." />
      </div>
    </section>
    </PageShell>
  );
}
