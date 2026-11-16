"use client";

import Link from "next/link";
import { PageShell } from "@/components/PageFrame";

export default function ErrorPage({ retry }: { error: unknown; retry: () => void }) {
  return (
    <PageShell>
    <section className="nf" aria-labelledby="err-h">
      <div className="wrap">
        <div role="alert" className="phead__text">
          <p className="eyebrow">Algo falló</p>
          <h1 className="h2" id="err-h">
            No pudimos <em>mostrar</em> esta página.
          </h1>
          <p className="lead">
            Pasó un error inesperado. No es un problema con los datos que miras: puedes intentarlo otra vez o volver al inicio. No mostramos datos de
            reemplazo.
          </p>
          <div className="actions">
            <button type="button" className="btn btn--tc" onClick={() => retry()}>
              Intentarlo otra vez
            </button>
            <Link href="/" className="btn btn--line">
              Ir al inicio
            </Link>
          </div>
        </div>
      </div>
    </section>
    </PageShell>
  );
}
