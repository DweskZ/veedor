import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ApiError, getBuyer, getProcesses, getSignalIndex } from "@/lib/api";
import { fmtInt, fmtNum, fmtPct, fmtUsd, NA } from "@/lib/format";
import { ProcessTable } from "@/components/ProcessTable";
import { canLinkSupplier, isRuc } from "@/lib/validate";
import { BarList, Card, EmptyState, ErrorState, Fig, Name, Num, PageHeader, PageSkeleton, partyName, Section } from "@/components/ui";

export const metadata: Metadata = { title: "Entidad contratante" };

export default function BuyerPage({ params }: PageProps<"/entidades/[ruc]">) {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/entidades/[ruc]">["params"] }) {
  const ruc = decodeURIComponent((await params).ruc);
  if (!isRuc(ruc)) notFound();
  const r = await Promise.all([
    getBuyer(ruc),
    getSignalIndex(),
    getProcesses({ buyer_ruc: ruc, sort: "-risk_score", page_size: "10" }),
  ]).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) {
    if (r.e instanceof ApiError && r.e.status === 404) notFound();
    return (
      <div className="wrap" style={{ paddingBlock: 56 }}>
        <ErrorState detail={r.e instanceof Error ? r.e.message : undefined} />
      </div>
    );
  }
  const [b, index, recent] = r.v;
  const labels = index.labels;
  const mix = [...b.signal_mix].sort((x, y) => y.count - x.count);
  return (
    <>
      <PageHeader
        eyebrow="Entidad contratante"
        small
        title={<Name value={b.name} fallback="Entidad contratante" />}
        lead={
          <>
            RUC <Num>{b.ruc}</Num>
            {b.first_year && b.last_year ? ` · Procesos de ${b.first_year} a ${b.last_year}` : ""}
          </>
        }
      />
      <div className="wrap">
        <dl className="figs figs--4">
          <Fig label="procesos" value={fmtInt(b.n_processes)} />
          <Fig label="procesos con al menos una señal" value={fmtInt(b.n_flagged)} hint={b.n_processes ? `${fmtPct(b.n_flagged / b.n_processes)} del total` : undefined} />
          <Fig label="monto adjudicado" value={fmtUsd(b.total_awarded, true)} medium />
          <Fig label="puntaje medio" value={fmtNum(b.mean_risk_score)} />
        </dl>

        <div className="grid2" style={{ marginTop: "clamp(48px, 7vw, 88px)", alignItems: "start" }}>
          <section aria-labelledby="top-prov">
            <h2 id="top-prov" className="blk__title" style={{ marginBottom: 20 }}>A quién le compra más</h2>
            {b.top_suppliers.length ? (
              <div className="tbl-wrap" tabIndex={0} role="region" aria-label="Principales proveedores (tabla desplazable)">
                <table className="tbl" style={{ minWidth: "28rem" }}>
                  <caption className="sr-only">Proveedores con mayor monto adjudicado por la entidad</caption>
                  <thead>
                    <tr>
                      <th scope="col">Proveedor</th>
                      <th scope="col" className="r">Adjudic.</th>
                      <th scope="col" className="r">Monto</th>
                      <th scope="col" className="r">Parte</th>
                    </tr>
                  </thead>
                  <tbody>
                    {b.top_suppliers.map((s, i) => (
                      <tr key={`${s.ruc ?? "x"}-${i}`}>
                        <td>
                          {canLinkSupplier(s.ruc, s.kind) ? (
                            <Link href={`/proveedores/${s.ruc}`} className="cell-link">
                              {partyName(s.name, s.kind)}
                            </Link>
                          ) : (
                            partyName(s.name, s.kind)
                          )}
                          <div className="cell-sub">{s.ruc ? <Num>{s.ruc}</Num> : NA}</div>
                        </td>
                        <td className="r">{fmtInt(s.n_awards)}</td>
                        <td className="r">{fmtUsd(s.total_awarded, true)}</td>
                        <td className="r">{fmtPct(s.share_of_awarded)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState>No hay proveedores para mostrar.</EmptyState>
            )}
          </section>
          <section aria-labelledby="mix">
            <h2 id="mix" className="blk__title" style={{ marginBottom: 20 }}>Señales de sus procesos</h2>
            <Card>
              {mix.length ? (
                <BarList format={fmtInt} items={mix.map((c) => ({ key: c.code, label: c.label_es ?? labels[c.code] ?? c.code, value: c.count }))} />
              ) : (
                <p className="muted">Ninguna señal activada en sus procesos.</p>
              )}
            </Card>
          </section>
        </div>

        <Section title="Sus procesos con mayor puntaje" id="procesos">
          {recent.items.length ? (
            <ProcessTable rows={recent.items} labels={labels} context={index.context} caption="Procesos de la entidad con mayor puntaje" />
          ) : (
            <EmptyState art>
              <p className="empty__t">No hay procesos para mostrar.</p>
            </EmptyState>
          )}
        </Section>
        <div className="page-end" />
      </div>
    </>
  );
}
