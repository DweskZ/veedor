import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ApiError, getDossier, getInvestigation, getMeta, getProcess, getReviews, getSignals } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtInt, fmtNum, fmtUsd, NA, shortCode } from "@/lib/format";
import type { ProcessFacts, SignalDef } from "@/lib/types";
import { SignalCard } from "@/components/SignalCard";
import { DossierIndex, DossierSectionView } from "@/components/DossierSections";
import { InvestigationPanel } from "@/components/Investigation";
import { SameBuyerToggle } from "@/components/SameBuyerToggle";
import { SimilarBody } from "@/components/SimilarProcesses";
import { canLinkBuyer, canLinkSupplier, isOcid } from "@/lib/validate";
import { REVIEW_LABELS } from "@/lib/reviews";
import { Card, EmptyState, ErrorState, Mono, PageSkeleton, partyName, RiskScore, Section, Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Expediente de proceso" };

const EMPTY_FACTS: ProcessFacts = {
  process_code: null, release_date: null, year: null, buyer_ruc: null, buyer_name: null, buyer_region: null,
  buyer_locality: null, method: null, method_group: null, category: null, status: null, description: null,
  budget: null, tender_start: null, tender_end: null, n_tenderers: null, n_bids: null, n_awards: null,
  award_total: null, first_award_date: null, date_signed: null, main_cpc: null, main_cpc_description: null,
};

export default function ProcessPage({ params, searchParams }: PageProps<"/procesos/[ocid]">) {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Dossier params={params} searchParams={searchParams} />
    </Suspense>
  );
}

const PAGE_INDEX: [string, string][] = [
  ["hechos", "Hechos"],
  ["senales", "Señales"],
  ["investigacion", "Investigación"],
  ["similares", "Similares"],
  ["texto", "Texto del expediente"],
  ["fuentes", "Fuentes"],
  ["verificar", "Cómo verificar"],
  ["revision", "Revisión humana"],
];

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-line py-2.5 sm:grid sm:grid-cols-[11rem_1fr] sm:gap-4">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="text-sm text-ink">{children}</dd>
    </div>
  );
}

async function Dossier({
  params,
  searchParams,
}: {
  params: PageProps<"/procesos/[ocid]">["params"];
  searchParams: PageProps<"/procesos/[ocid]">["searchParams"];
}) {
  const ocid = decodeURIComponent((await params).ocid);
  const sb = (await searchParams).same_buyer;
  const sameBuyer = (Array.isArray(sb) ? sb[0] : sb) === "1";
  if (!isOcid(ocid)) notFound();
  let detail;
  let defs: SignalDef[] = [];
  try {
    [detail, defs] = await Promise.all([getProcess(ocid), getSignals().catch(() => [] as SignalDef[])]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    return (
      <div className="mt-10">
        <ErrorState detail={e instanceof Error ? e.message : undefined} />
      </div>
    );
  }
  const f = detail.facts ?? EMPTY_FACTS;
  const w = detail.winner;
  const score = detail.score;
  const defByCode = new Map(defs.map((d) => [d.code, d]));
  const isContext = (s: { code: string; kind?: string }) => (s.kind ?? defByCode.get(s.code)?.kind) === "context";
  const riskSignals = detail.signals.filter((s) => !isContext(s));
  const contextSignals = detail.signals.filter(isContext);

  return (
    <>
      <p className="mt-8 text-sm">
        <Link href="/procesos" className="text-accent underline underline-offset-2">
          ← Procesos
        </Link>
      </p>
      <div className="mb-8 mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold tracking-tight text-ink">
            <Mono>{f.process_code ?? shortCode(ocid)}</Mono>
          </h1>
          {f.description ? (
            <p className="mt-2 max-w-3xl text-base text-muted">{f.description}</p>
          ) : detail.facts?.description_withheld ? (
            <p className="mt-2 max-w-3xl text-base text-muted">Descripción omitida por contener datos personales.</p>
          ) : null}
        </div>
        <Card className="min-w-48">
          <p className="text-sm text-muted">Puntaje de riesgo</p>
          <div className="mt-1">
            {score ? <RiskScore score={score.risk_score} /> : <span className="text-sm text-muted">No disponible</span>}
          </div>
          {score?.anomaly_score != null ? (
            <p className="mt-2 text-xs text-muted">
              Puntaje de anomalía: <Mono>{fmtNum(score.anomaly_score)}</Mono>. Se informa por separado y no modifica el puntaje.
            </p>
          ) : null}
        </Card>
      </div>

      <nav aria-label="En esta página" className="-mt-2 mb-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {PAGE_INDEX.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="text-accent underline underline-offset-2">
            {label}
          </a>
        ))}
      </nav>

      <Section title="Hechos del proceso" id="hechos">
        <dl>
          <Fact label="Entidad contratante">
            {canLinkBuyer(f.buyer_ruc) ? (
              <Link href={`/entidades/${f.buyer_ruc}`} className="text-accent underline underline-offset-2">
                {f.buyer_name ?? NA}
              </Link>
            ) : (
              (f.buyer_name ?? NA)
            )}
            {f.buyer_ruc ? (
              <>
                {" "}
                · <Mono>{f.buyer_ruc}</Mono>
              </>
            ) : null}
          </Fact>
          <Fact label="Adjudicatario">
            {w && (w.ruc || w.name) ? (
              <>
                {canLinkSupplier(w.ruc, w.kind) ? (
                  <Link href={`/proveedores/${w.ruc}`} className="text-accent underline underline-offset-2">
                    {partyName(w.name, w.kind)}
                  </Link>
                ) : (
                  partyName(w.name, w.kind)
                )}
                {w.ruc ? (
                  <>
                    {" "}
                    · <Mono>{w.ruc}</Mono>
                  </>
                ) : null}
              </>
            ) : (
              "Sin adjudicatario registrado"
            )}
          </Fact>
          <Fact label="Método">{f.method ?? NA}</Fact>
          <Fact label="Categoría">{f.category ?? NA}</Fact>
          <Fact label="Estado">{f.status ?? NA}</Fact>
          <Fact label="Fecha de publicación">{fmtDate(f.release_date)}</Fact>
          <Fact label="Presupuesto referencial">
            <span className="font-mono">{fmtUsd(f.budget)}</span>
          </Fact>
          <Fact label="Monto adjudicado">
            <span className="font-mono">{fmtUsd(f.award_total)}</span>
          </Fact>
          <Fact label="Oferentes">
            {detail.tenderers.length ? (
              <ul className="space-y-0.5">
                {detail.tenderers.map((t, i) => (
                  <li key={`${t.ruc}-${i}`}>
                    {partyName(t.name, t.kind)}
                    {t.ruc ? (
                      <>
                        {" "}
                        · <Mono>{t.ruc}</Mono>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              NA
            )}
          </Fact>
          <Fact label="Oferentes / ofertas">
            <span className="font-mono">
              {fmtInt(f.n_tenderers)} / {fmtInt(f.n_bids)}
            </span>
          </Fact>
          <Fact label="Periodo de ofertas">
            {f.tender_start || f.tender_end ? `${fmtDate(f.tender_start)} a ${fmtDate(f.tender_end)}` : NA}
          </Fact>
          <Fact label="Fecha de firma">{fmtDate(f.date_signed)}</Fact>
          <Fact label="CPC principal">
            {f.main_cpc ? (
              <>
                <Mono>{f.main_cpc}</Mono>
                {f.main_cpc_description ? ` · ${f.main_cpc_description}` : ""}
              </>
            ) : (
              NA
            )}
          </Fact>
          <Fact label="Identificador OCDS">
            <Mono>{ocid}</Mono>
          </Fact>
        </dl>
      </Section>

      <Section title={`Señales de riesgo (${riskSignals.length})`} id="senales">
        {riskSignals.length === 0 ? (
          <EmptyState>Este proceso no activó ninguna señal de riesgo. Eso no significa que esté libre de problemas: solo que ninguna regla disponible lo marcó.</EmptyState>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {riskSignals.map((s) => (
              <SignalCard key={s.code} signal={s} def={defByCode.get(s.code)} />
            ))}
          </div>
        )}
      </Section>

      {contextSignals.length ? (
        <Section title="Contexto registral" id="contexto">
          <p className="mb-4 max-w-3xl text-sm text-muted">
            Estos datos describen el registro del proveedor en relación con el proceso. No afectan el puntaje de riesgo.
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {contextSignals.map((s) => (
              <SignalCard key={s.code} signal={s} def={defByCode.get(s.code)} quiet />
            ))}
          </div>
        </Section>
      ) : null}

      <Section title="Investigación" id="investigacion">
        <Suspense fallback={<Skeleton className="h-64" />}>
          <InvestigationSection ocid={ocid} />
        </Suspense>
      </Section>

      <Section
        title="Procesos similares"
        id="similares"
        aside={<SameBuyerToggle checked={sameBuyer} />}
      >
        <p className="mb-4 max-w-3xl text-sm text-muted">
          La similitud se calcula según la clasificación y la descripción del objeto; no implica relación entre los procesos.
          Es una ayuda de búsqueda y no una señal de riesgo.
        </p>
        <Suspense fallback={<Skeleton className="h-72" />}>
          <SimilarBody ocid={ocid} sameBuyer={sameBuyer} />
        </Suspense>
      </Section>

      <Suspense fallback={<Skeleton className="mt-12 h-64" />}>
        <DossierText ocid={ocid} />
      </Suspense>

      <Section title="Cómo verificar" id="verificar">
        <Card>
          <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-ink">
            <li>
              Copie el identificador OCDS (<Mono>{ocid}</Mono>) y búsquelo en el portal de datos abiertos de SERCOP o en el
              archivo de liberaciones OCDS de la fuente.
            </li>
            <li>Compare los campos de la sección &quot;Hechos del proceso&quot; con el registro original: presupuesto, monto adjudicado, número de oferentes y fechas.</li>
            <li>Revise el valor observado y el umbral de cada señal; la evidencia lista los campos usados en el cálculo.</li>
            <li>Para el adjudicatario, contraste el estado con la consulta pública del SRI. El estado del registro es el actual, no el vigente al momento de la adjudicación.</li>
          </ol>
          <p className="mt-3 text-sm text-muted">Un indicador no es un hallazgo. Si algo no concuerda con la fuente, regístrelo en el panel de revisión.</p>
        </Card>
      </Section>

      <Section title="Revisión humana" id="revision">
        <Suspense fallback={<Skeleton className="h-48" />}>
          <Reviews ocid={ocid} />
        </Suspense>
      </Section>
    </>
  );
}

async function InvestigationSection({ ocid }: { ocid: string }) {
  const r = await getInvestigation(ocid).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) return <ErrorState title="No se pudo cargar la investigación" detail={r.e instanceof Error ? r.e.message : undefined} />;
  if (!r.v) return <p className="text-sm text-muted">No hay una investigación registrada para este proceso.</p>;
  return <InvestigationPanel inv={r.v} />;
}

async function DossierText({ ocid }: { ocid: string }) {
  const r = await getDossier(ocid).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) {
    const pending = r.e instanceof ApiError && r.e.status === 503;
    return (
      <Section title="Texto del expediente" id="texto">
        {pending ? (
          <EmptyState>
            <strong className="block text-ink">Expediente no disponible para este proceso</strong>
            Los hechos y las señales de arriba sí provienen de los datos.
          </EmptyState>
        ) : (
          <ErrorState title="No se pudo cargar el texto del expediente" detail={r.e instanceof Error ? r.e.message : undefined} />
        )}
      </Section>
    );
  }
  const d = r.v;
  const grounded = d.grounding_report?.passed === true;
  const modeLabel =
    d.mode === "llm"
      ? "Redactado con modelo de lenguaje y verificado"
      : d.mode === "template_minimal"
        ? "Plantilla mínima: solo hechos del proceso"
        : "Generado por plantilla determinista a partir de los datos";
  return (
    <>
      <Section title="Texto del expediente" id="texto">
        <Card>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line pb-3 text-sm">
            <span className="font-medium text-ink">
              {grounded ? "Texto verificado contra los datos" : "Texto sin verificación disponible"}
            </span>
            {d.grounding_report ? (
              <span className="text-muted">{fmtInt(d.grounding_report.n_checked)} elementos comprobados</span>
            ) : null}
            <span className="text-muted">
              Modo: <Mono>{d.mode ?? NA}</Mono> · {modeLabel}
            </span>
            {d.generated_at ? <span className="text-muted">Generado: {fmtDateTime(d.generated_at)}</span> : null}
          </div>
          {d.summary_es ? <p className="mt-4 text-base leading-relaxed text-ink">{d.summary_es}</p> : null}
          <div className="mt-4">
            <DossierIndex sections={d.sections} />
          </div>
          {d.sections.map((s) => (
            <DossierSectionView key={s.title} section={s} />
          ))}
        </Card>
      </Section>
      <Section title="Fuentes" id="fuentes">
        {d.sources.length === 0 ? (
          <EmptyState>No hay fuentes registradas para este expediente.</EmptyState>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {d.sources.map((s, i) => (
              <li key={`${s.dataset}-${i}`} className="rounded-lg border border-line bg-surface p-4 text-sm">
                <p className="font-medium text-ink">{s.dataset}</p>
                <dl className="mt-2 space-y-1 text-muted">
                  <div>
                    Licencia: <span className="text-ink">{s.licence ?? NA}</span>
                  </div>
                  <div>
                    Obtenido: <span className="text-ink">{fmtDate(s.retrieved_at)}</span>
                  </div>
                  <div className="break-all">
                    Registro: {s.record_id ? <Mono>{s.record_id}</Mono> : NA}
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

async function Reviews({ ocid }: { ocid: string }) {
  const [meta, reviews] = await Promise.all([
    getMeta(),
    getReviews(ocid).then(
      (v) => ({ ok: true as const, v }),
      () => ({ ok: false as const, v: [] }),
    ),
  ]);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <h3 className="mb-3 text-sm font-semibold text-ink">Revisiones registradas</h3>
        {!reviews.ok ? (
          <p role="alert" className="text-sm text-muted">No se pudo cargar el historial de revisiones.</p>
        ) : reviews.v.length === 0 ? (
          <p className="text-sm text-muted">Aún no hay revisiones humanas para este proceso.</p>
        ) : (
          <ul className="space-y-3">
            {reviews.v.map((r) => (
              <li key={r.id} className="rounded-md border border-line bg-surface p-3 text-sm">
                <div className="flex flex-wrap justify-between gap-2">
                  <span className="font-medium text-ink">{REVIEW_LABELS[r.status]}</span>
                  <span className="text-muted">{fmtDateTime(r.created_at)}</span>
                </div>
                {r.note ? <p className="mt-1 whitespace-pre-line text-muted">{r.note}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="self-start rounded-lg border border-dashed border-line p-4 text-sm text-muted">
        {meta.reviews_enabled
          ? "Las revisiones las registran revisores autorizados; aquí se muestran solo en lectura."
          : "El registro de revisiones está deshabilitado en esta instancia."}
      </p>
    </div>
  );
}
