import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ApiError, getDossier, getInvestigation, getMeta, getProcess, getReviews, getSignals } from "@/lib/api";
import { fmtCategory, fmtDate, fmtDateTime, fmtInt, fmtNum, fmtStatus, fmtUsd, NA, shortCode } from "@/lib/format";
import type { ProcessFacts, SignalDef } from "@/lib/types";
import { SignalCard } from "@/components/SignalCard";
import { DossierIndex, DossierSectionView } from "@/components/DossierSections";
import { InvestigationPanel } from "@/components/Investigation";
import { SameBuyerToggle } from "@/components/SameBuyerToggle";
import { SimilarBody } from "@/components/SimilarProcesses";
import { canLinkBuyer, canLinkSupplier, isOcid } from "@/lib/validate";
import { REVIEW_LABELS } from "@/lib/reviews";
import { Card, EmptyState, ErrorState, Num, PageSkeleton, partyName, RiskScore, Section, Skeleton } from "@/components/ui";

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

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Toc({ items }: { items: [string, string][] }) {
  const list = (
    <ol>
      {items.map(([id, label]) => (
        <li key={id}>
          <a href={`#${id}`}>{label}</a>
        </li>
      ))}
    </ol>
  );
  return (
    <>
      <nav aria-label="En esta página" className="toc toc-d">
        <p className="toc__title">En esta página</p>
        {list}
      </nav>
      <nav aria-label="En esta página" className="toc toc-m">
        <details>
          <summary>En esta página</summary>
          {list}
        </details>
      </nav>
    </>
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
      <div className="wrap" style={{ paddingBlock: 56 }}>
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
  const toc: [string, string][] = [
    ["hechos", "Los datos del proceso"],
    ["senales", "Señales de riesgo"],
    ...(contextSignals.length ? ([["contexto", "Contexto del proveedor"]] as [string, string][]) : []),
    ["investigacion", "Investigación con agentes"],
    ["similares", "Procesos parecidos"],
    ["texto", "Texto del expediente"],
    ["fuentes", "Fuentes"],
    ["verificar", "Cómo verificar"],
    ["revision", "Revisión humana"],
  ];
  const winnerName = w && (w.ruc || w.name) ? partyName(w.name, w.kind) : null;

  return (
    <>
      <header className="phead" style={{ paddingBottom: 28 }}>
        <div className="wrap">
          <div className="phead__circle" aria-hidden="true" />
          <div className="phead__text">
            <Link href="/procesos" className="crumb">
              ← Todos los procesos
            </Link>
            <p className="eyebrow" style={{ marginTop: 18 }}>
              Proceso de contratación
            </p>
            <h1 className="h1 h1--sm">
              <Num>{f.process_code ?? shortCode(ocid)}</Num>
            </h1>
          </div>
        </div>
      </header>

      <div className="wrap">
        <section className="summary" aria-label="Resumen del proceso">
          <div className="summary__cell summary__cell--what">
            <p className="summary__q">Qué se compró</p>
            <p className="summary__a summary__a--text">
              {f.description ? f.description : detail.facts?.description_withheld ? "Descripción omitida por contener datos personales." : NA}
            </p>
            {f.main_cpc_description || f.category ? (
              <p className="summary__sub">{[fmtCategory(f.category), f.main_cpc_description].filter(Boolean).join(" · ")}</p>
            ) : null}
          </div>
          <div className="summary__cell summary__cell--who">
            <p className="summary__q">Quién compró</p>
            <p className="summary__a">
              {canLinkBuyer(f.buyer_ruc) ? (
                <Link href={`/entidades/${f.buyer_ruc}`} className="cell-link">
                  {f.buyer_name ?? NA}
                </Link>
              ) : (
                (f.buyer_name ?? NA)
              )}
            </p>
            <p className="summary__sub">
              {f.method ?? NA}
              {f.release_date ? ` · publicado el ${fmtDate(f.release_date)}` : ""}
            </p>
          </div>
          <div className="summary__cell summary__cell--won">
            <p className="summary__q">Quién ganó</p>
            <p className="summary__a">
              {winnerName ? (
                w && canLinkSupplier(w.ruc, w.kind) ? (
                  <Link href={`/proveedores/${w.ruc}`} className="cell-link">
                    {winnerName}
                  </Link>
                ) : (
                  winnerName
                )
              ) : (
                "Sin adjudicatario registrado"
              )}
            </p>
            <p className="summary__sub">
              {w?.ruc ? (
                <>
                  RUC <Num>{w.ruc}</Num> ·{" "}
                </>
              ) : null}
              {f.n_tenderers != null ? `${fmtInt(f.n_tenderers)} ${f.n_tenderers === 1 ? "oferente" : "oferentes"}` : "Oferentes: no disponible"}
            </p>
          </div>
          <div className="summary__cell summary__cell--much">
            <p className="summary__q">Cuánto</p>
            <p className="summary__a summary__a--big">{fmtUsd(f.award_total)}</p>
            <p className="summary__sub">Presupuesto referencial: {fmtUsd(f.budget)}</p>
          </div>
          <div className="summary__cell summary__cell--score">
            <p className="summary__q">Puntaje</p>
            {score ? (
              <>
                <RiskScore score={score.risk_score} big />
                <p className="summary__sub" style={{ marginTop: 10 }}>
                  {riskSignals.length === 1 ? "1 señal de riesgo" : `${fmtInt(riskSignals.length)} señales de riesgo`}. El puntaje es una guía
                  para decidir qué mirar primero, no un veredicto.
                </p>
                {score.anomaly_score != null ? (
                  <p className="summary__sub">
                    Puntaje de anomalía: <Num>{fmtNum(score.anomaly_score)}</Num>. Se informa por separado y no cambia el puntaje.
                  </p>
                ) : null}
              </>
            ) : (
              <p className="summary__a">No disponible</p>
            )}
          </div>
        </section>

        <div className="doc">
          <Toc items={toc} />
          <div className="doc__main">
            <Section title="Los datos del proceso" id="hechos" note="Estos son los datos tal como los publica el SERCOP. Compáralos con el registro original.">
              <dl className="facts">
                <Fact label="Entidad contratante">
                  {canLinkBuyer(f.buyer_ruc) ? (
                    <Link href={`/entidades/${f.buyer_ruc}`} className="cell-link">
                      {f.buyer_name ?? NA}
                    </Link>
                  ) : (
                    (f.buyer_name ?? NA)
                  )}
                  {f.buyer_ruc ? (
                    <>
                      {" "}
                      · <Num>{f.buyer_ruc}</Num>
                    </>
                  ) : null}
                </Fact>
                <Fact label="Quién ganó">
                  {winnerName ? (
                    <>
                      {w && canLinkSupplier(w.ruc, w.kind) ? (
                        <Link href={`/proveedores/${w.ruc}`} className="cell-link">
                          {winnerName}
                        </Link>
                      ) : (
                        winnerName
                      )}
                      {w?.ruc ? (
                        <>
                          {" "}
                          · <Num>{w.ruc}</Num>
                        </>
                      ) : null}
                    </>
                  ) : (
                    "Sin adjudicatario registrado"
                  )}
                </Fact>
                <Fact label="Método">{f.method ?? NA}</Fact>
                <Fact label="Categoría">{fmtCategory(f.category) ?? NA}</Fact>
                <Fact label="Estado">{fmtStatus(f.status) ?? NA}</Fact>
                <Fact label="Fecha de publicación">{fmtDate(f.release_date)}</Fact>
                <Fact label="Presupuesto referencial">
                  <Num>{fmtUsd(f.budget)}</Num>
                </Fact>
                <Fact label="Monto adjudicado">
                  <Num>{fmtUsd(f.award_total)}</Num>
                </Fact>
                <Fact label="Empresas que ofertaron">
                  {detail.tenderers.length ? (
                    <ul>
                      {detail.tenderers.map((t, i) => (
                        <li key={`${t.ruc}-${i}`}>
                          {partyName(t.name, t.kind)}
                          {t.ruc ? (
                            <>
                              {" "}
                              · <Num>{t.ruc}</Num>
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
                  <Num>
                    {fmtInt(f.n_tenderers)} / {fmtInt(f.n_bids)}
                  </Num>
                </Fact>
                <Fact label="Periodo de ofertas">
                  {f.tender_start || f.tender_end ? `${fmtDate(f.tender_start)} a ${fmtDate(f.tender_end)}` : NA}
                </Fact>
                <Fact label="Fecha de firma">{fmtDate(f.date_signed)}</Fact>
                <Fact label="Tipo de bien o servicio (CPC)">
                  {f.main_cpc ? (
                    <>
                      <Num>{f.main_cpc}</Num>
                      {f.main_cpc_description ? ` · ${f.main_cpc_description}` : ""}
                    </>
                  ) : (
                    NA
                  )}
                </Fact>
                <Fact label="Identificador OCDS">
                  <Num>{ocid}</Num>
                </Fact>
              </dl>
            </Section>

            <Section
              title="Señales de riesgo"
              id="senales"
              note="Una señal es un patrón atípico, no una conclusión. Cada tarjeta responde tres preguntas: qué se observó, por qué puede importar y cómo puede ser normal."
              aside={<p className="tag">{riskSignals.length === 1 ? "1 señal" : `${fmtInt(riskSignals.length)} señales`}</p>}
            >
              {riskSignals.length === 0 ? (
                <EmptyState>
                  <p className="empty__t">Este proceso no activó ninguna señal de riesgo.</p>
                  <p style={{ marginTop: 8 }}>Eso no significa que esté libre de problemas: solo que ninguna regla disponible lo marcó.</p>
                </EmptyState>
              ) : (
                <div className="sigs sigs--2">
                  {riskSignals.map((s) => (
                    <SignalCard key={s.code} signal={s} def={defByCode.get(s.code)} />
                  ))}
                </div>
              )}
            </Section>

            {contextSignals.length ? (
              <Section title="Contexto del proveedor" id="contexto" note="Estos datos describen el registro del proveedor en relación con el proceso. Son solo contexto: no suman puntos.">
                <div className="sigs sigs--2">
                  {contextSignals.map((s) => (
                    <SignalCard key={s.code} signal={s} def={defByCode.get(s.code)} quiet />
                  ))}
                </div>
              </Section>
            ) : null}

            <Section title="Investigación con agentes" id="investigacion">
              <Suspense fallback={<Skeleton style={{ height: 256 }} />}>
                <InvestigationSection ocid={ocid} />
              </Suspense>
            </Section>

            <Section
              title="Procesos parecidos"
              id="similares"
              aside={<SameBuyerToggle checked={sameBuyer} />}
              note="Se parecen por el tipo de bien o servicio y por su descripción. Que se parezcan no significa que estén relacionados: es una ayuda para buscar, no una señal de riesgo."
            >
              <Suspense fallback={<Skeleton style={{ height: 288 }} />}>
                <SimilarBody ocid={ocid} sameBuyer={sameBuyer} />
              </Suspense>
            </Section>

            <Suspense fallback={<Skeleton style={{ height: 256, marginTop: 64 }} />}>
              <DossierText ocid={ocid} />
            </Suspense>

            <Section title="Cómo verificar" id="verificar" note="Veedor no es la última palabra. Estos pasos te llevan a la fuente oficial.">
              <Card>
                <ol className="stack">
                  {[
                    <>
                      Copia el identificador OCDS (<Num>{ocid}</Num>) y búscalo en el portal de datos abiertos del SERCOP o en el archivo de liberaciones OCDS de la fuente.
                    </>,
                    <>Compara los campos de «Los datos del proceso» con el registro original: presupuesto, monto adjudicado, número de oferentes y fechas.</>,
                    <>Revisa el valor observado y el umbral de cada señal; la evidencia lista los campos usados en el cálculo.</>,
                    <>Para quien ganó, contrasta su estado con la consulta pública del SRI. El estado del registro es el de hoy, no el que tenía cuando se adjudicó.</>,
                  ].map((t, i) => (
                    <li key={i} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                      <span className="pin pin--inline" aria-hidden="true">
                        {i + 1}
                      </span>
                      <span style={{ paddingTop: 6 }}>{t}</span>
                    </li>
                  ))}
                </ol>
                <p className="muted small" style={{ marginTop: 18, paddingTop: 14, borderTop: "2px solid var(--ice-deep)" }}>
                  Un indicador no es un hallazgo. Si algo no concuerda con la fuente, regístralo en el panel de revisión.
                </p>
              </Card>
            </Section>

            <Section title="Revisión humana" id="revision">
              <Suspense fallback={<Skeleton style={{ height: 192 }} />}>
                <Reviews ocid={ocid} />
              </Suspense>
            </Section>
            <div className="page-end" />
          </div>
        </div>
      </div>
    </>
  );
}

async function InvestigationSection({ ocid }: { ocid: string }) {
  const r = await getInvestigation(ocid).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) return <ErrorState title="No pudimos cargar la investigación" detail={r.e instanceof Error ? r.e.message : undefined} />;
  if (!r.v) return <p className="muted">Todavía no hay una investigación con agentes para este proceso.</p>;
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
            <p className="empty__t">El texto del expediente no está disponible para este proceso.</p>
            <p style={{ marginTop: 8 }}>Los datos y las señales de arriba sí están disponibles.</p>
          </EmptyState>
        ) : (
          <ErrorState title="No pudimos cargar el texto del expediente" detail={r.e instanceof Error ? r.e.message : undefined} />
        )}
      </Section>
    );
  }
  const d = r.v;
  const grounded = d.grounding_report?.passed === true;
  const modeLabel =
    d.mode === "llm"
      ? "Redactado con un modelo de lenguaje y verificado"
      : d.mode === "template_minimal"
        ? "Plantilla mínima: solo los datos del proceso"
        : "Escrito por una plantilla fija a partir de los datos";
  return (
    <>
      <Section
        title="Texto del expediente"
        id="texto"
        note="Un resumen escrito a partir de los datos. Cada cifra, fecha y nombre se comprueba contra la evidencia antes de mostrarse."
      >
        <Card>
          <div className="dossier__meta">
            <span className={`verified ${grounded ? "" : "verified--no"}`}>
              {grounded ? "Texto verificado contra los datos" : "Texto sin verificación disponible"}
            </span>
            {d.grounding_report ? <span className="muted">{fmtInt(d.grounding_report.n_checked)} elementos comprobados</span> : null}
            <span className="muted">{modeLabel}</span>
            {d.generated_at ? <span className="muted">Generado: {fmtDateTime(d.generated_at)}</span> : null}
          </div>
          {d.summary_es ? <p style={{ marginTop: 18, fontSize: "1.125rem", lineHeight: 1.55 }}>{d.summary_es}</p> : null}
          <DossierIndex sections={d.sections} />
          {d.sections.map((s) => (
            <DossierSectionView key={s.title} section={s} />
          ))}
        </Card>
      </Section>
      <Section title="Fuentes" id="fuentes" note="De dónde salen los datos de este expediente.">
        {d.sources.length === 0 ? (
          <EmptyState>No hay fuentes registradas para este expediente.</EmptyState>
        ) : (
          <ul className="sources">
            {d.sources.map((s, i) => (
              <li key={`${s.dataset}-${i}`} className="card card--tight">
                <p className="h4">{s.dataset}</p>
                <dl className="stack small" style={{ marginTop: 10 }}>
                  <div>
                    <dt className="tag">Licencia</dt>
                    <dd>{s.licence ?? NA}</dd>
                  </div>
                  <div>
                    <dt className="tag">Obtenido</dt>
                    <dd>{fmtDate(s.retrieved_at)}</dd>
                  </div>
                  <div style={{ overflowWrap: "anywhere" }}>
                    <dt className="tag">Registro</dt>
                    <dd>{s.record_id ? <Num>{s.record_id}</Num> : NA}</dd>
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
    <div className="grid2">
      <div>
        <h3 className="h4" style={{ marginBottom: 12 }}>Revisiones registradas</h3>
        {!reviews.ok ? (
          <p role="alert" className="err">No pudimos cargar el historial de revisiones.</p>
        ) : reviews.v.length === 0 ? (
          <p className="muted">Todavía no hay revisiones humanas para este proceso.</p>
        ) : (
          <ul className="reviews">
            {reviews.v.map((r) => (
              <li key={r.id} className="review">
                <div className="review__top">
                  <span>{REVIEW_LABELS[r.status]}</span>
                  <time dateTime={r.created_at}>{fmtDateTime(r.created_at)}</time>
                </div>
                {r.note ? <p style={{ marginTop: 6, whiteSpace: "pre-line" }}>{r.note}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="card card--quiet card--tight small" style={{ alignSelf: "start" }}>
        {meta.reviews_enabled
          ? "Las revisiones las registran revisores autorizados; aquí solo se pueden leer."
          : "El registro de revisiones está desactivado en esta instancia."}
      </p>
    </div>
  );
}
