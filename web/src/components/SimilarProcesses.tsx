import Link from "next/link";
import { ApiError, getSimilar } from "@/lib/api";
import { fmtUsd, NA, shortCode } from "@/lib/format";
import type { SimilarProcess } from "@/lib/types";
import { canLinkBuyer } from "@/lib/validate";
import { EmptyState, Mono } from "./ui";

const sim = new Intl.NumberFormat("es-EC", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function SimilarityBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden="true" className="h-2 w-20 rounded-sm bg-surface-2">
        <span className="block h-full rounded-sm border border-line" style={{ width: `${Math.max(2, pct)}%`, background: "var(--accent)" }} />
      </span>
      <span className="font-mono">{sim.format(value)}</span>
    </span>
  );
}

function Table({ rows }: { rows: SimilarProcess[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface" tabIndex={0} role="region" aria-label="Procesos similares (tabla desplazable)">
      <table className="w-full min-w-[48rem] border-collapse text-left text-sm">
        <caption className="sr-only">Procesos similares, ordenados de mayor a menor similitud</caption>
        <thead>
          <tr className="border-b border-line bg-surface-2 text-xs uppercase tracking-wide text-muted">
            <th scope="col" className="px-4 py-3 font-medium">Similitud</th>
            <th scope="col" className="px-4 py-3 font-medium">Año</th>
            <th scope="col" className="px-4 py-3 font-medium">Entidad</th>
            <th scope="col" className="px-4 py-3 font-medium">Método</th>
            <th scope="col" className="px-4 py-3 text-right font-medium">Monto adjudicado</th>
            <th scope="col" className="px-4 py-3 font-medium">Proceso</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ocid} className="border-b border-line align-top last:border-b-0 hover:bg-surface-2/60">
              <td className="px-4 py-3">
                <SimilarityBar value={r.similarity} />
              </td>
              <td className="px-4 py-3 font-mono">{r.year ?? NA}</td>
              <td className="px-4 py-3 text-ink">
                {canLinkBuyer(r.buyer_ruc) ? (
                  <Link href={`/entidades/${r.buyer_ruc}`} className="hover:underline">
                    {r.buyer_name ?? NA}
                  </Link>
                ) : (
                  (r.buyer_name ?? NA)
                )}
              </td>
              <td className="px-4 py-3 text-muted">{r.method ?? NA}</td>
              <td className="px-4 py-3 text-right font-mono">{fmtUsd(r.award_total)}</td>
              <td className="px-4 py-3">
                <Link href={`/procesos/${encodeURIComponent(r.ocid)}`} className="whitespace-nowrap font-medium text-accent underline-offset-2 hover:underline">
                  <Mono>{shortCode(r.ocid)}</Mono>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Loads and renders the similar-processes table; every API failure becomes a plain note, never hidden data. */
export async function SimilarBody({ ocid, sameBuyer }: { ocid: string; sameBuyer: boolean }) {
  const r = await getSimilar(ocid, sameBuyer).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) {
    const e = r.e;
    if (e instanceof ApiError && e.status === 404 && e.code === "not_indexed") {
      return <EmptyState>Este proceso no está en el índice de similares.</EmptyState>;
    }
    if (e instanceof ApiError && e.status === 503) {
      return <EmptyState>El índice de similares no está disponible en este momento. Intente nuevamente más tarde.</EmptyState>;
    }
    return (
      <p role="alert" className="rounded-lg border border-line bg-surface p-4 text-sm text-muted">
        No se pudieron cargar los procesos similares. {e instanceof Error ? e.message : ""}
      </p>
    );
  }
  if (r.v.items.length === 0) {
    return (
      <EmptyState>
        {sameBuyer ? "No se encontraron procesos similares de la misma entidad entre los más cercanos." : "No se encontraron procesos similares."}
      </EmptyState>
    );
  }
  return <Table rows={r.v.items} />;
}
