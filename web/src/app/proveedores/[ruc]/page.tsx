import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ApiError, getSignalIndex, getSupplier } from "@/lib/api";
import { fmtDate, fmtInt, fmtNum, fmtPct, fmtUsd, NA } from "@/lib/format";
import { ProcessTable } from "@/components/ProcessTable";
import { isRuc } from "@/lib/validate";
import type { SriFacts } from "@/lib/types";
import { Card, EmptyState, ErrorState, Mono, PageHeader, PageSkeleton, partyName, Section, Stat } from "@/components/ui";

export const metadata: Metadata = { title: "Proveedor" };

const REGISTRY_LABELS: [keyof SriFacts, string][] = [
  ["legal_name", "Razón social"],
  ["status", "Estado actual en el SRI"],
  ["taxpayer_type", "Tipo de contribuyente"],
  ["activity_start_date", "Inicio de actividades"],
  ["suspension_date", "Fecha de suspensión"],
  ["restart_date", "Fecha de reinicio"],
  ["ciiu_code", "Código CIIU"],
  ["activity", "Actividad"],
  ["province", "Provincia"],
];

export default function SupplierPage({ params }: PageProps<"/proveedores/[ruc]">) {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/proveedores/[ruc]">["params"] }) {
  const ruc = decodeURIComponent((await params).ruc);
  if (!isRuc(ruc)) notFound();
  const r = await Promise.all([getSupplier(ruc), getSignalIndex()]).then(
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
  const [{ profile: s, registry, recent_processes }, index] = r.v;
  if (s.kind !== "company" && s.kind !== "public_entity") notFound();
  const sri = registry.sri;
  const sriRows = sri ? REGISTRY_LABELS.filter(([k]) => sri[k] != null && sri[k] !== "") : [];
  return (
    <>
      <PageHeader
        title={partyName(s.name, s.kind)}
        lead={
          <>
            RUC <Mono>{s.ruc ?? ruc}</Mono>
          </>
        }
      />
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Procesos en que participó" value={fmtInt(s.n_processes)} />
        <Stat label="Procesos ganados" value={fmtInt(s.n_wins)} hint={`${fmtInt(s.single_bidder_wins)} con oferente único`} />
        <Stat label="Monto adjudicado" value={<span className="text-xl">{fmtUsd(s.total_awarded, true)}</span>} />
        <Stat label="Puntaje medio" value={fmtNum(s.mean_risk_score)} hint="Promedio de sus procesos ganados" />
      </dl>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="text-base font-semibold text-ink">Historial de adjudicaciones</h2>
          <dl className="mt-3 space-y-1.5 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-muted">Primera adjudicación</dt><dd>{fmtDate(s.first_award_date)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-muted">Última adjudicación</dt><dd>{fmtDate(s.last_award_date)}</dd></div>
            <div className="flex justify-between gap-3"><dt className="text-muted">Entidades distintas</dt><dd className="font-mono">{fmtInt(s.n_buyers)}</dd></div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">Entidad principal</dt>
              <dd className="text-right">
                {s.top_buyer_ruc ? (
                  <Link href={`/entidades/${s.top_buyer_ruc}`} className="text-accent underline underline-offset-2">
                    <Mono>{s.top_buyer_ruc}</Mono>
                  </Link>
                ) : (
                  NA
                )}{" "}
                <span className="text-muted">({fmtPct(s.top_buyer_share)} del total)</span>
              </dd>
            </div>
          </dl>
        </Card>
        <Card>
          <h2 className="text-base font-semibold text-ink">Datos del registro</h2>
          {sriRows.length && sri ? (
            <dl className="mt-3 space-y-1.5 text-sm">
              {sriRows.map(([k, label]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="shrink-0 text-muted">{label}</dt>
                  <dd className="text-right">{/^\d{4}-\d{2}-\d{2}$/.test(String(sri[k])) ? fmtDate(sri[k]) : sri[k]}</dd>
                </div>
              ))}
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Listado de empresas inexistentes del SRI</dt>
                <dd>{registry.ghost_company_listed == null ? NA : registry.ghost_company_listed ? "Figura" : "No figura"}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-muted">No disponible.</p>
          )}
          <p className="mt-3 text-xs text-muted">El estado del registro es el actual, no el vigente al momento de cada adjudicación.</p>
        </Card>
      </div>
      {registry.financials.length ? (
        <Section title="Estados financieros reportados" id="financieros">
          <div className="overflow-x-auto rounded-lg border border-line bg-surface" tabIndex={0} role="region" aria-label="Estados financieros (tabla desplazable)">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <caption className="sr-only">Cifras anuales reportadas a la Superintendencia de Compañías</caption>
              <thead>
                <tr className="border-b border-line bg-surface-2 text-xs uppercase tracking-wide text-muted">
                  <th scope="col" className="px-4 py-3 font-medium">Año</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Ingresos</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Activos</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Patrimonio</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Empleados</th>
                </tr>
              </thead>
              <tbody>
                {registry.financials.map((f) => (
                  <tr key={f.year} className="border-b border-line last:border-b-0">
                    <th scope="row" className="px-4 py-2.5 text-left font-mono font-normal">{f.year}</th>
                    <td className="px-4 py-2.5 text-right font-mono">{fmtUsd(f.revenue, true)}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{fmtUsd(f.assets, true)}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{fmtUsd(f.equity, true)}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{fmtInt(f.employees)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}
      <Section title="Procesos recientes" id="procesos">
        {recent_processes.length ? (
          <ProcessTable rows={recent_processes} labels={index.labels} context={index.context} caption="Procesos recientes del proveedor" />
        ) : (
          <EmptyState>No hay procesos para mostrar.</EmptyState>
        )}
      </Section>
    </>
  );
}
