import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ApiError, getBuyer, getProcesses, getSignalIndex } from "@/lib/api";
import { fmtInt, fmtNum, fmtPct, fmtUsd, NA } from "@/lib/format";
import { ProcessTable } from "@/components/ProcessTable";
import { canLinkSupplier, isRuc } from "@/lib/validate";
import { BarList, Card, EmptyState, ErrorState, Mono, PageHeader, PageSkeleton, partyName, Section, Stat } from "@/components/ui";

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
      <div className="mt-10">
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
        title={b.name ?? "Entidad contratante"}
        lead={
          <>
            RUC <Mono>{b.ruc}</Mono>
            {b.first_year && b.last_year ? ` · Procesos de ${b.first_year} a ${b.last_year}` : ""}
          </>
        }
      />
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Procesos" value={fmtInt(b.n_processes)} />
        <Stat label="Con al menos una señal" value={fmtInt(b.n_flagged)} hint={b.n_processes ? fmtPct(b.n_flagged / b.n_processes) : undefined} />
        <Stat label="Monto adjudicado" value={<span className="text-xl">{fmtUsd(b.total_awarded, true)}</span>} />
        <Stat label="Puntaje medio" value={fmtNum(b.mean_risk_score)} />
      </dl>

      <div className="mt-12 grid gap-8 lg:grid-cols-2">
        <section aria-labelledby="top-prov">
          <h2 id="top-prov" className="mb-4 text-xl font-semibold tracking-tight text-ink">Principales proveedores</h2>
          {b.top_suppliers.length ? (
            <div className="overflow-x-auto rounded-lg border border-line bg-surface" tabIndex={0} role="region" aria-label="Principales proveedores (tabla desplazable)">
              <table className="w-full min-w-[28rem] text-left text-sm">
                <caption className="sr-only">Proveedores con mayor monto adjudicado por la entidad</caption>
                <thead>
                  <tr className="border-b border-line bg-surface-2 text-xs uppercase tracking-wide text-muted">
                    <th scope="col" className="px-4 py-3 font-medium">Proveedor</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">Adjudic.</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">Monto</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">Parte</th>
                  </tr>
                </thead>
                <tbody>
                  {b.top_suppliers.map((s, i) => (
                    <tr key={s.ruc ?? i} className="border-b border-line last:border-b-0">
                      <td className="px-4 py-3">
                        {canLinkSupplier(s.ruc, s.kind) ? (
                          <Link href={`/proveedores/${s.ruc}`} className="text-accent underline-offset-2 hover:underline">
                            {partyName(s.name, s.kind)}
                          </Link>
                        ) : (
                          partyName(s.name, s.kind)
                        )}
                        <div className="text-muted">{s.ruc ? <Mono>{s.ruc}</Mono> : NA}</div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono">{fmtInt(s.n_awards)}</td>
                      <td className="px-4 py-3 text-right font-mono">{fmtUsd(s.total_awarded, true)}</td>
                      <td className="px-4 py-3 text-right font-mono">{fmtPct(s.share_of_awarded)}</td>
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
          <h2 id="mix" className="mb-4 text-xl font-semibold tracking-tight text-ink">Señales de sus procesos</h2>
          <Card>
            {mix.length ? (
              <BarList format={fmtInt} items={mix.map((c) => ({ key: c.code, label: c.label_es ?? labels[c.code] ?? c.code, value: c.count }))} />
            ) : (
              <p className="text-sm text-muted">Ninguna señal activada en sus procesos.</p>
            )}
          </Card>
        </section>
      </div>

      <Section title="Procesos con mayor puntaje" id="procesos">
        {recent.items.length ? (
          <ProcessTable rows={recent.items} labels={labels} context={index.context} caption="Procesos de la entidad con mayor puntaje" />
        ) : (
          <EmptyState>No hay procesos para mostrar.</EmptyState>
        )}
      </Section>
    </>
  );
}
