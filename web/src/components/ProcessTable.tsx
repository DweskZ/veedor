import Link from "next/link";
import { fmtUsd, NA, shortCode } from "@/lib/format";
import type { ProcessSummary } from "@/lib/types";
import { canLinkBuyer, canLinkSupplier } from "@/lib/validate";
import { Mono, partyName, RiskScore, SignalChip } from "./ui";

export interface SortConfig {
  current: string;
  href: (field: string) => string;
}

const COLUMNS: { field: string | null; label: string; align?: "right" }[] = [
  { field: "risk_score", label: "Puntaje" },
  { field: null, label: "Proceso y entidad" },
  { field: null, label: "Adjudicatario" },
  { field: "award_total", label: "Monto adjudicado", align: "right" },
  { field: null, label: "Método" },
  { field: null, label: "Señales" },
];

function ariaSort(field: string | null, current: string): "ascending" | "descending" | "none" | undefined {
  if (!field) return undefined;
  if (current === field) return "ascending";
  if (current === `-${field}`) return "descending";
  return "none";
}

export function ProcessTable({
  rows,
  labels,
  caption,
  sort,
  context = [],
}: {
  rows: ProcessSummary[];
  labels: Record<string, string>;
  caption: string;
  sort?: SortConfig;
  /** Codes of context signals, shown with a quieter style. */
  context?: string[];
}) {
  return (
    <div
      className="overflow-x-auto rounded-lg border border-line bg-surface"
      tabIndex={0}
      role="region"
      aria-label={`${caption} (tabla desplazable)`}
    >
      <table className="w-full min-w-[56rem] border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line bg-surface-2 text-xs uppercase tracking-wide text-muted">
            {COLUMNS.map((c) => (
              <th
                key={c.label}
                scope="col"
                aria-sort={sort ? ariaSort(c.field, sort.current) : undefined}
                className={`px-4 py-3 font-medium ${c.align === "right" ? "text-right" : ""}`}
              >
                {sort && c.field ? (
                  <Link
                    href={sort.href(c.field)}
                    className="inline-flex items-center gap-1 text-ink underline-offset-2 hover:underline"
                  >
                    {c.label}
                    <span aria-hidden="true">{sort.current === c.field ? "↑" : sort.current === `-${c.field}` ? "↓" : "↕"}</span>
                  </Link>
                ) : (
                  c.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ocid} className="border-b border-line align-top last:border-b-0 hover:bg-surface-2/60">
              <td className="px-4 py-3">
                <RiskScore score={r.risk_score} />
              </td>
              <td className="px-4 py-3">
                <Link href={`/procesos/${encodeURIComponent(r.ocid)}`} className="whitespace-nowrap font-medium text-accent underline-offset-2 hover:underline">
                  <Mono>{shortCode(r.ocid)}</Mono>
                </Link>
                <div className="mt-0.5 text-muted">
                  {canLinkBuyer(r.buyer_ruc) ? (
                    <Link href={`/entidades/${r.buyer_ruc}`} className="hover:text-ink hover:underline">
                      {r.buyer_name ?? NA}
                    </Link>
                  ) : (
                    (r.buyer_name ?? NA)
                  )}
                  {r.year ? ` · ${r.year}` : ""}
                </div>
              </td>
              <td className="px-4 py-3">
                {r.winner_name || r.winner_kind ? (
                  <>
                    {canLinkSupplier(r.winner_ruc, r.winner_kind) ? (
                      <Link href={`/proveedores/${r.winner_ruc}`} className="hover:underline">
                        {partyName(r.winner_name, r.winner_kind)}
                      </Link>
                    ) : (
                      partyName(r.winner_name, r.winner_kind)
                    )}
                    {r.winner_ruc ? (
                      <div className="text-muted">
                        <Mono>{r.winner_ruc}</Mono>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <span className="text-muted">Sin adjudicatario</span>
                )}
              </td>
              <td className="px-4 py-3 text-right font-mono">{fmtUsd(r.award_total)}</td>
              <td className="px-4 py-3 text-muted">{r.method ?? NA}</td>
              <td className="px-4 py-3">
                {r.signal_codes.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {r.signal_codes.map((c) => (
                      <SignalChip key={c} code={c} labels={labels} quiet={context.includes(c)} />
                    ))}
                  </div>
                ) : (
                  <span className="text-muted">Ninguna</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
