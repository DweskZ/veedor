import type { Metadata } from "next";
import { PageShell } from "@/components/PageFrame";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getSignalIndex, getSupplier } from "@/lib/api";
import { fmtDate, fmtInt, fmtNum, fmtPct, fmtUsd, NA } from "@/lib/format";
import { ProcessTable } from "@/components/ProcessTable";
import { isRuc } from "@/lib/validate";
import type { SriFacts } from "@/lib/types";
import { Card, EmptyState, ErrorState, Fig, Name, Num, PageHeader, partyName, Section } from "@/components/ui";

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
    <Content params={params} />
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
      <PageShell>
        <div className="wrap" style={{ paddingBlock: 56 }}>
          <ErrorState detail={r.e instanceof Error ? r.e.message : undefined} />
        </div>
      </PageShell>
    );
  }
  const [{ profile: s, registry, recent_processes }, index] = r.v;
  if (s.kind !== "company" && s.kind !== "public_entity") notFound();
  const sri = registry.sri;
  const sriRows = sri ? REGISTRY_LABELS.filter(([k]) => sri[k] != null && sri[k] !== "") : [];
  return (
    <PageShell>
      <PageHeader
        eyebrow="Proveedor"
        small
        title={<Name value={s.name} fallback={partyName(s.name, s.kind)} />}
        lead={
          <>
            RUC <Num>{s.ruc ?? ruc}</Num>
          </>
        }
      />
      <div className="wrap">
        <dl className="figs figs--4">
          <Fig label="procesos en los que participó" value={fmtInt(s.n_processes)} />
          <Fig label="procesos que ganó" value={fmtInt(s.n_wins)} hint={`${fmtInt(s.single_bidder_wins)} con la señal «oferente único»`} />
          <Fig label="monto adjudicado" value={fmtUsd(s.total_awarded, true)} medium />
          <Fig label="puntaje medio" value={fmtNum(s.mean_risk_score)} hint="Promedio de los procesos que ganó" />
        </dl>
        <div className="grid2 grid2--top" style={{ marginTop: "clamp(28px, 4vw, 40px)" }}>
          <Card>
            <h2 className="h3">Historial de adjudicaciones</h2>
            <dl className="kvs">
              <Row label="Primera adjudicación">{fmtDate(s.first_award_date)}</Row>
              <Row label="Última adjudicación">{fmtDate(s.last_award_date)}</Row>
              <Row label="Entidades distintas">
                <Num>{fmtInt(s.n_buyers)}</Num>
              </Row>
              <Row label="Entidad principal">
                {s.top_buyer_ruc ? (
                  <Link href={`/entidades/${s.top_buyer_ruc}`} className="cell-link">
                    <Num>{s.top_buyer_ruc}</Num>
                  </Link>
                ) : (
                  NA
                )}{" "}
                <span className="muted">({fmtPct(s.top_buyer_share)} del total)</span>
              </Row>
            </dl>
          </Card>
          <Card>
            <h2 className="h3">Datos del registro</h2>
            {sriRows.length && sri ? (
              <dl className="kvs">
                {sriRows.map(([k, label]) => (
                  <Row key={k} label={label}>
                    {/^\d{4}-\d{2}-\d{2}$/.test(String(sri[k])) ? fmtDate(sri[k]) : sri[k]}
                  </Row>
                ))}
                <Row label="Listado de empresas inexistentes del SRI">
                  {registry.ghost_company_listed == null ? NA : registry.ghost_company_listed ? "Figura" : "No figura"}
                </Row>
              </dl>
            ) : (
              <p className="muted" style={{ marginTop: 12 }}>No disponible.</p>
            )}
            <p className="muted small" style={{ marginTop: 16 }}>El estado del registro es el de hoy, no el que tenía cuando se adjudicó cada proceso.</p>
          </Card>
        </div>
        {registry.financials.length ? (
          <Section title="Estados financieros reportados" id="financieros" note="Cifras anuales que la empresa reportó a la Superintendencia de Compañías.">
            <div className="tbl-wrap" tabIndex={0} role="region" aria-label="Estados financieros (tabla desplazable)">
              <table className="tbl" style={{ minWidth: "32rem" }}>
                <caption className="sr-only">Cifras anuales reportadas a la Superintendencia de Compañías</caption>
                <thead>
                  <tr>
                    <th scope="col">Año</th>
                    <th scope="col" className="r">Ingresos</th>
                    <th scope="col" className="r">Activos</th>
                    <th scope="col" className="r">Patrimonio</th>
                    <th scope="col" className="r">Empleados</th>
                  </tr>
                </thead>
                <tbody>
                  {registry.financials.map((f) => (
                    <tr key={f.year}>
                      <th scope="row">{f.year}</th>
                      <td className="r">{fmtUsd(f.revenue, true)}</td>
                      <td className="r">{fmtUsd(f.assets, true)}</td>
                      <td className="r">{fmtUsd(f.equity, true)}</td>
                      <td className="r">{fmtInt(f.employees)}</td>
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
            <EmptyState art>
              <p className="empty__t">No hay procesos para mostrar.</p>
            </EmptyState>
          )}
        </Section>
        <div className="page-end" />
      </div>
    </PageShell>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="kv">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
