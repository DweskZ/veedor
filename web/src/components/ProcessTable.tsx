import Link from "next/link";
import { fmtUsd, NA, shortCode } from "@/lib/format";
import type { ProcessSummary } from "@/lib/types";
import { canLinkBuyer, canLinkSupplier } from "@/lib/validate";
import { shortLabel } from "@/lib/signal-copy";
import { SignalChips } from "./SignalChips";
import { Name, Num, partyName, RiskScore } from "./ui";

export interface SortConfig {
  current: string;
  href: (field: string) => string;
}

const COLUMNS: { field: string | null; label: string; align?: "right" }[] = [
  { field: "risk_score", label: "Puntaje" },
  { field: null, label: "Proceso y entidad" },
  { field: null, label: "Quién ganó" },
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

function Buyer({ r }: { r: ProcessSummary }) {
  return canLinkBuyer(r.buyer_ruc) ? (
    <Link href={`/entidades/${r.buyer_ruc}`} className="cell-link">
      <Name value={r.buyer_name} />
    </Link>
  ) : (
    <><Name value={r.buyer_name} /></>
  );
}

function WinnerName({ r }: { r: ProcessSummary }) {
  return r.winner_kind === "natural_person" ? <>{partyName(r.winner_name, r.winner_kind)}</> : <Name value={r.winner_name ?? partyName(r.winner_name, r.winner_kind)} />;
}

function Winner({ r, withRuc = true }: { r: ProcessSummary; withRuc?: boolean }) {
  if (!r.winner_name && !r.winner_kind) return <span className="muted">Sin adjudicatario</span>;
  return (
    <>
      <span className="clamp2" title={r.winner_kind === "natural_person" ? undefined : (r.winner_name ?? undefined)}>
        {canLinkSupplier(r.winner_ruc, r.winner_kind) ? (
          <Link href={`/proveedores/${r.winner_ruc}`} className="cell-link">
            <WinnerName r={r} />
          </Link>
        ) : (
          <WinnerName r={r} />
        )}
      </span>
      {withRuc && r.winner_ruc ? (
        <div className="cell-sub">
          <Num>{r.winner_ruc}</Num>
        </div>
      ) : null}
    </>
  );
}

function Signals({ r, labels, context }: { r: ProcessSummary; labels: Record<string, string>; context: string[] }) {
  return (
    <SignalChips
      items={r.signal_codes.map((c) => ({ code: c, text: shortLabel(c, labels), full: labels[c] ?? c, quiet: context.includes(c) }))}
    />
  );
}

/** Table on wide screens, one card per process on narrow ones (same data, only one of them is displayed). */
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
    <>
      <div className="only-wide">
        <div className="tbl-wrap" tabIndex={0} role="region" aria-label={`${caption} (tabla desplazable)`}>
          <table className="tbl tbl--proc" style={{ minWidth: "62rem" }}>
            <caption className="sr-only">{caption}</caption>
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <th
                    key={c.label}
                    scope="col"
                    aria-sort={sort ? ariaSort(c.field, sort.current) : undefined}
                    className={c.align === "right" ? "r" : undefined}
                  >
                    {sort && c.field ? (
                      <Link href={sort.href(c.field)}>
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
                <tr key={r.ocid}>
                  <td>
                    <RiskScore score={r.risk_score} />
                  </td>
                  <td>
                    <Link href={`/procesos/${encodeURIComponent(r.ocid)}`} className="code">
                      {shortCode(r.ocid)}
                    </Link>
                    {r.year ? <span className="cell-sub cell-sub--inline"> · {r.year}</span> : null}
                    <div className="cell-sub clamp2" title={r.buyer_name ?? undefined}>
                      <Buyer r={r} />
                    </div>
                  </td>
                  <td>
                    <Winner r={r} />
                  </td>
                  <td className="r">
                    <Num>{fmtUsd(r.award_total)}</Num>
                  </td>
                  <td>{r.method ?? NA}</td>
                  <td>
                    <Signals r={r} labels={labels} context={context} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <ul className="only-narrow pcards" aria-label={caption}>
        {rows.map((r) => (
          <li key={r.ocid} className="pcard">
            <div className="pcard__top">
              <Link href={`/procesos/${encodeURIComponent(r.ocid)}`} className="pcard__code">
                {shortCode(r.ocid)}
              </Link>
              <RiskScore score={r.risk_score} />
            </div>
            <dl>
              <div>
                <dt>Entidad</dt>
                <dd className="clamp2" title={r.buyer_name ?? undefined}>
                  <Buyer r={r} />
                </dd>
              </div>
              <div>
                <dt>Ganó</dt>
                <dd>
                  <Winner r={r} withRuc={false} />
                </dd>
              </div>
              <div>
                <dt>Monto</dt>
                <dd>
                  <Num>{fmtUsd(r.award_total)}</Num> · {r.method ?? NA}{r.year ? ` · ${r.year}` : ""}
                </dd>
              </div>
              <div>
                <dt>Señales</dt>
                <dd>
                  <Signals r={r} labels={labels} context={context} />
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}
