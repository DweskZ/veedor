import Link from "next/link";
import { ApiError, getSimilar } from "@/lib/api";
import { fmtUsd, NA, shortCode } from "@/lib/format";
import type { SimilarProcess } from "@/lib/types";
import { canLinkBuyer } from "@/lib/validate";
import { EmptyState, Name, Num } from "./ui";

const sim = new Intl.NumberFormat("es-EC", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function SimilarityBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  return (
    <span className="simbar">
      <span aria-hidden="true" className="simbar__t">
        <i style={{ width: `${Math.max(2, pct)}%` }} />
      </span>
      <Num>{sim.format(value)}</Num>
    </span>
  );
}

function Buyer({ r }: { r: SimilarProcess }) {
  return canLinkBuyer(r.buyer_ruc) ? (
    <Link href={`/entidades/${r.buyer_ruc}`} className="cell-link">
      <Name value={r.buyer_name} />
    </Link>
  ) : (
    <><Name value={r.buyer_name} /></>
  );
}

function Table({ rows }: { rows: SimilarProcess[] }) {
  return (
    <>
      <div className="only-wide">
        <div className="tbl-wrap" tabIndex={0} role="region" aria-label="Procesos similares (tabla desplazable)">
          <table className="tbl" style={{ minWidth: "46rem" }}>
            <caption className="sr-only">Procesos similares, ordenados de mayor a menor similitud</caption>
            <thead>
              <tr>
                <th scope="col">Parecido</th>
                <th scope="col">Año</th>
                <th scope="col">Entidad</th>
                <th scope="col">Método</th>
                <th scope="col" className="r">Monto adjudicado</th>
                <th scope="col">Proceso</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ocid}>
                  <td>
                    <SimilarityBar value={r.similarity} />
                  </td>
                  <td>
                    <Num>{r.year ?? NA}</Num>
                  </td>
                  <td>
                    <Buyer r={r} />
                  </td>
                  <td>{r.method ?? NA}</td>
                  <td className="r">
                    <Num>{fmtUsd(r.award_total)}</Num>
                  </td>
                  <td>
                    <Link href={`/procesos/${encodeURIComponent(r.ocid)}`} className="code">
                      {shortCode(r.ocid)}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <ul className="only-narrow pcards" aria-label="Procesos similares, ordenados de mayor a menor similitud">
        {rows.map((r) => (
          <li key={r.ocid} className="pcard">
            <div className="pcard__top">
              <Link href={`/procesos/${encodeURIComponent(r.ocid)}`} className="pcard__code">
                {shortCode(r.ocid)}
              </Link>
              <SimilarityBar value={r.similarity} />
            </div>
            <dl>
              <div>
                <dt>Entidad</dt>
                <dd>
                  <Buyer r={r} />
                </dd>
              </div>
              <div>
                <dt>Año y método</dt>
                <dd>
                  <Num>{r.year ?? NA}</Num> · {r.method ?? NA}
                </dd>
              </div>
              <div>
                <dt>Monto adjudicado</dt>
                <dd>
                  <Num>{fmtUsd(r.award_total)}</Num>
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}

/** Loads and renders the similar-processes list; every API failure becomes a plain note, never hidden data. */
export async function SimilarBody({ ocid, sameBuyer }: { ocid: string; sameBuyer: boolean }) {
  const r = await getSimilar(ocid, sameBuyer).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) {
    const e = r.e;
    if (e instanceof ApiError && e.status === 404 && e.code === "not_indexed") {
      return <EmptyState>Este proceso no está en el índice de procesos parecidos.</EmptyState>;
    }
    if (e instanceof ApiError && e.status === 503) {
      return <EmptyState>El índice de procesos parecidos no está disponible en este momento. Inténtalo más tarde.</EmptyState>;
    }
    return (
      <p role="alert" className="err">
        No pudimos cargar los procesos parecidos. {e instanceof Error ? e.message : ""}
      </p>
    );
  }
  if (r.v.items.length === 0) {
    return (
      <EmptyState>
        {sameBuyer ? "No encontramos procesos parecidos de la misma entidad entre los más cercanos." : "No encontramos procesos parecidos."}
      </EmptyState>
    );
  }
  return <Table rows={r.v.items} />;
}
