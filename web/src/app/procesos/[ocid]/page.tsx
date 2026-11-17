import type { Metadata } from "next";
import { PageShell } from "@/components/PageFrame";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { ApiError, getContext, getDossier as fetchDossier, getInvestigation, getMeta, getProcess, getProvenance, getQuotes, getReviews, getSignals } from "@/lib/api";
import { citationFor, sourceById, type Provenance } from "@/lib/provenance";
import { fmtCategory, fmtDate, fmtDateTime, fmtInt, fmtNum, fmtStatus, fmtUsd, NA, shortCode } from "@/lib/format";
import type { ProcessFacts, SignalDef } from "@/lib/types";
import { SignalCard } from "@/components/SignalCard";
import { DossierIndex, DossierSectionView } from "@/components/DossierSections";
import { ContextCharts } from "@/components/ContextCharts";
import { Term } from "@/components/Term";
import { InvestigationPanel } from "@/components/Investigation";
import { SameBuyerToggle } from "@/components/SameBuyerToggle";
import { SimilarBody } from "@/components/SimilarProcesses";
import { canLinkBuyer, canLinkSupplier, isOcid } from "@/lib/validate";
import { REVIEW_LABELS } from "@/lib/reviews";
import { Card, EmptyState, ErrorState, Name, Num, partyName, RiskScore, Section, TabPanel } from "@/components/ui";
import { displayName } from "@/lib/names";
import { ProcessTabs, type TabItem } from "@/components/ProcessTabs";
import { ProvenanceProvider, SourceMarker, SourcesToggle } from "@/components/Provenance";
import { QuotesBlock } from "@/components/Quotes";
import { AskSection } from "@/components/AskProcess";
import { suggestQuestions } from "@/lib/ask";
import { CopyButton } from "@/components/CopyButton";
import { BackToTop } from "@/components/BackToTop";

const getDossier = cache(fetchDossier);

export const metadata: Metadata = { title: "Expediente de proceso" };

const EMPTY_FACTS: ProcessFacts = {
  process_code: null, release_date: null, year: null, buyer_ruc: null, buyer_name: null, buyer_region: null,
  buyer_locality: null, method: null, method_group: null, category: null, status: null, description: null,
  budget: null, tender_start: null, tender_end: null, n_tenderers: null, n_bids: null, n_awards: null,
  award_total: null, first_award_date: null, date_signed: null, main_cpc: null, main_cpc_description: null,
};

export default function ProcessPage({ params, searchParams }: PageProps<"/procesos/[ocid]">) {
  return (
    <Dossier params={params} searchParams={searchParams} />
  );
}

/** Smaller title for long descriptions, so the header stays compact. */
const titleSize = (t: string | null | undefined): string => {
  const n = t?.length ?? 0;
  return n > 140 ? "h1--xl" : n > 80 ? "h1--lg" : "";
};

function Fact({ label, keys, children }: { label: React.ReactNode; keys?: string[]; children: React.ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>
        {children}
        {keys ? <SourceMarker keys={keys} /> : null}
      </dd>
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
      <PageShell>
        <div className="wrap" style={{ paddingBlock: 56 }}>
          <ErrorState detail={e instanceof Error ? e.message : undefined} />
        </div>
      </PageShell>
    );
  }
  const f = detail.facts ?? EMPTY_FACTS;
  const w = detail.winner;
  const score = detail.score;
  const defByCode = new Map(defs.map((d) => [d.code, d]));
  const isContext = (s: { code: string; kind?: string }) => (s.kind ?? defByCode.get(s.code)?.kind) === "context";
  const riskSignals = detail.signals.filter((s) => !isContext(s));
  const contextSignals = detail.signals.filter(isContext);
  // Every part is loaded here, before anything is rendered: a part still pending while the page is being sent would be
  // streamed after the footer, which is the wrong reading order without JavaScript (see PageFrame).
  const provPromise = getProvenance(ocid).catch(() => null);
  const metaPromise = getMeta();
  const [prov, quotes, apiMeta, comparison, investigation, similar, reviewsBlock, dossierText] = await Promise.all([
    provPromise,
    // Quotes are requested only when the API says they are on; a missing flag, a 404 or any failure hides the section silently.
    metaPromise.then((m) => (m.quotes_enabled === true ? getQuotes(ocid).catch(() => null) : null)),
    metaPromise,
    ComparisonSection({ ocid }),
    InvestigationSection({ ocid }),
    SimilarBody({ ocid, sameBuyer }),
    Reviews({ ocid }),
    provPromise.then((p) => DossierText({ ocid, prov: p })),
  ]);
  // The question box exists only when the API says the route is on (absent or unknown counts as off).
  const askEnabled = apiMeta.ask_enabled === true;
  const suggestions = suggestQuestions({
    nRiskSignals: riskSignals.length,
    hasTenderers: f.n_tenderers != null || detail.tenderers.length > 0,
    hasAmounts: f.budget != null || f.award_total != null,
    hasBuyer: Boolean(f.buyer_name),
    hasWinner: Boolean(w && (w.ruc || w.name)),
    hasObject: Boolean(f.description || f.main_cpc_description),
  });
  const quotesShown = apiMeta.quotes_enabled === true && quotes !== null;
  const nSig = riskSignals.length;
  const tabs: TabItem[] = [
    { id: "resumen", label: "Resumen" },
    { id: "hechos", label: "Datos" },
    { id: "senales", label: "Señales", badge: nSig ? String(nSig) : undefined },
    ...(quotesShown ? [{ id: "citas", label: "Citas" }] : []),
    ...(askEnabled ? [{ id: "preguntar", label: "Preguntar" }] : []),
    { id: "investigacion", label: "Investigación" },
    { id: "similares", label: "Parecidos" },
    { id: "texto", label: "Expediente" },
    { id: "verificar", label: "Verificar" },
    ...(dossierText.fuentes ? [{ id: "fuentes", label: "Fuentes" }] : []),
  ];
  const winnerNode =
    w && (w.ruc || w.name) ? (w.kind === "natural_person" || !w.name ? partyName(w.name, w.kind) : <Name value={w.name} />) : null;
  const code = f.process_code ?? shortCode(ocid);
  const hasTitle = Boolean(f.description);
  const meta = [fmtCategory(f.category), displayName(f.main_cpc_description)].filter(Boolean).join(" · ");

  return (
    <ProvenanceProvider prov={prov}>
      <PageShell>
      <header className="phead phead--page phead--proc">
        <div className="wrap">
          <div className="phead__circle" aria-hidden="true" />
          <div className="phead__text">
            <Link href="/procesos" className="crumb">
              ← Todos los procesos
            </Link>
            <h1 className={`h1 h1--page ${titleSize(f.description)}`}>{hasTitle ? <Name value={f.description} /> : <Num>{code}</Num>}</h1>
            {!hasTitle && detail.facts?.description_withheld ? <p className="phead__meta">Descripción omitida por contener datos personales.</p> : null}
            <div className="phead__row">
              {meta ? <p className="phead__meta">{meta}</p> : null}
              <p className="pcode">
                <span className="tag">Código</span>
                <span className="pcode__v">
                  <Num>{code}</Num>
                  <CopyButton text={code} label="Copiar código" iconOnly />
                </span>
              </p>
            </div>
          </div>
        </div>
      </header>

      <ProcessTabs items={tabs}>
        <TabPanel id="resumen">
          <Section title="Resumen" id="resumen" hideTitle>
            <section className="summary" aria-label="Lo esencial de este proceso">
          <div className="summary__cell summary__cell--what">
              <p className="summary__q">Qué se compró</p>
              <p className="summary__a summary__a--text">{meta || "Sin categoría publicada"}</p>
            </div>
            <div className="summary__cell summary__cell--who">
            <p className="summary__q">Quién compró</p>
            <p className="summary__a">
              {canLinkBuyer(f.buyer_ruc) ? (
                <Link href={`/entidades/${f.buyer_ruc}`} className="cell-link">
                  <Name value={f.buyer_name} />
                </Link>
              ) : (
                <Name value={f.buyer_name} />
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
              {winnerNode ? (
                w && canLinkSupplier(w.ruc, w.kind) ? (
                  <Link href={`/proveedores/${w.ruc}`} className="cell-link">
                    {winnerNode}
                  </Link>
                ) : (
                  winnerNode
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
            <p className="summary__a summary__a--big">{fmtUsd(f.award_total)}<SourceMarker keys={["facts.award_total"]} /></p>
            <p className="summary__sub">Presupuesto referencial: {fmtUsd(f.budget)}</p>
          </div>
          <div className="summary__cell summary__cell--score">
            <p className="summary__q"><Term t="puntaje">Puntaje</Term></p>
            {score ? (
              <>
                <RiskScore score={score.risk_score} big /><SourceMarker keys={["score.risk_score"]} />
                <p className="summary__sub" style={{ marginTop: 10 }}>
                  {riskSignals.length === 1 ? "1 señal de riesgo" : `${fmtInt(riskSignals.length)} señales de riesgo`}. Es una guía para decidir qué mirar primero,
                  no un veredicto.
                </p>
              </>
            ) : (
              <p className="summary__a">No disponible</p>
            )}
          </div>
        </section>
            <div className="rsum">
              <h3 className="h4">Señales de riesgo</h3>
              {riskSignals.length === 0 ? (
                <p className="rsum__none">Ninguna regla marcó este proceso. Eso no significa que esté libre de problemas.</p>
              ) : (
                <ul className="rsig">
                  {riskSignals.map((s) => (
                    <li key={s.code}>
                      <a href={`#sig-${s.code}`} className="rsig__name">
                        {s.label_es ?? defByCode.get(s.code)?.label_es ?? s.code}
                      </a>
                      <span className="rsig__val">
                        observado <b>{fmtNum(s.value)}</b> · umbral <b>{fmtNum(s.threshold)}</b>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {contextSignals.length ? (
                <p className="rsum__ctx">
                  Además, {contextSignals.length === 1 ? "1 dato de contexto" : `${fmtInt(contextSignals.length)} datos de contexto`} del proveedor que no suma{contextSignals.length === 1 ? "" : "n"} puntos:{" "}
                  {contextSignals.map((s, i) => (
                    <span key={s.code}>
                      {i ? ", " : ""}
                      <a href={`#sig-${s.code}`} className="inline-link">{s.label_es ?? defByCode.get(s.code)?.label_es ?? s.code}</a>
                    </span>
                  ))}
                  .
                </p>
              ) : null}
              <p className="rsum__go">
                <a href="#senales" className="link">Cada señal, con su explicación <span aria-hidden="true">→</span></a>
                <a href="#hechos" className="link">Todos los datos del proceso <span aria-hidden="true">→</span></a>
                <a href="#verificar" className="link">Cómo verificarlo en la fuente <span aria-hidden="true">→</span></a>
              </p>
            </div>
          </Section>
        </TabPanel>

        <TabPanel id="hechos">
          <Section
              title="Los datos del proceso"
              id="hechos"
              note="Estos son los datos tal como los publica el SERCOP. Compáralos con el registro original."
              aside={<SourcesToggle />}
            >
              <dl className="facts">
                <Fact label={<Term t="entidad contratante">Entidad contratante</Term>} keys={["facts.buyer_name", "facts.buyer_ruc"]}>
                  {canLinkBuyer(f.buyer_ruc) ? (
                    <Link href={`/entidades/${f.buyer_ruc}`} className="cell-link">
                      <Name value={f.buyer_name} />
                    </Link>
                  ) : (
                    <Name value={f.buyer_name} />
                  )}
                  {f.buyer_ruc ? (
                    <>
                      {" "}
                      · <Num>{f.buyer_ruc}</Num>
                    </>
                  ) : null}
                </Fact>
                <Fact label="Quién ganó" keys={["winner.name", "winner.ruc", "awards.supplier_name"]}>
                  {winnerNode ? (
                    <>
                      {w && canLinkSupplier(w.ruc, w.kind) ? (
                        <Link href={`/proveedores/${w.ruc}`} className="cell-link">
                          {winnerNode}
                        </Link>
                      ) : (
                        winnerNode
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
                <Fact label="Método" keys={["facts.method"]}>{f.method ?? NA}</Fact>
                <Fact label="Categoría" keys={["facts.category"]}>{fmtCategory(f.category) ?? NA}</Fact>
                <Fact label="Estado" keys={["facts.status"]}>{fmtStatus(f.status) ?? NA}</Fact>
                <Fact label="Fecha de publicación" keys={["facts.release_date"]}>{fmtDate(f.release_date)}</Fact>
                <Fact label={<Term t="presupuesto referencial">Presupuesto referencial</Term>} keys={["facts.budget"]}>
                  <Num>{fmtUsd(f.budget)}</Num>
                </Fact>
                <Fact label={<>Monto <Term t="adjudicación">adjudicado</Term></>} keys={["facts.award_total"]}>
                  <Num>{fmtUsd(f.award_total)}</Num>
                </Fact>
                <Fact label={<>Empresas que ofertaron (<Term t="oferente">oferentes</Term>)</>} keys={["tenderers.name", "tenderers.ruc"]}>
                  {detail.tenderers.length ? <TendererList tenderers={detail.tenderers} /> : NA}
                </Fact>
                <Fact label="Oferentes / ofertas" keys={["facts.n_tenderers", "facts.n_bids"]}>
                  <Num>
                    {fmtInt(f.n_tenderers)} / {fmtInt(f.n_bids)}
                  </Num>
                </Fact>
                <Fact label="Periodo de ofertas" keys={["facts.tender_start", "facts.tender_end"]}>
                  {f.tender_start || f.tender_end ? `${fmtDate(f.tender_start)} a ${fmtDate(f.tender_end)}` : NA}
                </Fact>
                <Fact label="Fecha de firma" keys={["facts.date_signed"]}>{fmtDate(f.date_signed)}</Fact>
                <Fact label={<>Tipo de bien o servicio (<Term t="CPC">CPC</Term>)</>} keys={["facts.main_cpc"]}>
                  {f.main_cpc ? (
                    <>
                      <Num>{f.main_cpc}</Num>
                      {f.main_cpc_description ? ` · ${displayName(f.main_cpc_description)}` : ""}
                    </>
                  ) : (
                    NA
                  )}
                </Fact>
                <Fact label="Identificador del proceso">
                  <Num>{ocid}</Num> <CopyButton text={ocid} label="Copiar identificador del proceso" iconOnly />
                </Fact>
              </dl>
            </Section>
        </TabPanel>

        <TabPanel id="senales">
          <Section
              title="Señales de riesgo"
              id="senales"
              note="Una señal es un patrón atípico, no una conclusión. Cada tarjeta dice qué se observó, por qué puede importar y cómo puede ser normal. En las barras, la barra es lo observado y la marca vertical es el umbral de la regla."
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
          <Section title="Cómo se compara" id="comparacion" note="Para cada dato que se puede comparar, dónde queda este proceso entre los parecidos.">
              {comparison}
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
        </TabPanel>

        {quotesShown ? (
          <TabPanel id="citas">
              <Section
                title="Citas de la fuente"
                id="citas"
                note="Textos del expediente publicado, mostrados tal como se publicaron. No son texto de Veedor y no se presentan como prueba de ninguna señal."
              >
                <QuotesBlock quotes={quotes} />
              </Section>
            </TabPanel>
        ) : null}

        {askEnabled ? (
          <TabPanel id="preguntar">
            <AskSection ocid={ocid} suggestions={suggestions} quotesEnabled={apiMeta.quotes_enabled === true} mode={apiMeta.ask_mode} />
          </TabPanel>
        ) : null}

        <TabPanel id="investigacion">
          <Section title="Investigación con agentes" id="investigacion">
              {investigation}
            </Section>
        </TabPanel>

        <TabPanel id="similares">
          <Section
              title="Procesos parecidos"
              id="similares"
              aside={<SameBuyerToggle checked={sameBuyer} />}
              note="Se parecen por el tipo de bien o servicio y por su descripción. Que se parezcan no significa que estén relacionados: es una ayuda para buscar, no una señal de riesgo."
            >
              {similar}
            </Section>
        </TabPanel>

        <TabPanel id="texto">{dossierText.texto}</TabPanel>

        <TabPanel id="verificar">
          <Section title="Cómo verificar" id="verificar" note="Veedor no es la última palabra. Estos pasos te llevan a la fuente oficial.">
              <Card>
                <ol className="stack">
                  {[
                    <>
                      Copia el identificador del proceso (<Num>{ocid}</Num>) y búscalo en el portal de datos abiertos del SERCOP o en el archivo de datos abiertos de la fuente.
                    </>,
                    <>Compara los campos de «Los datos del proceso» con el registro original: presupuesto, monto adjudicado, número de oferentes y fechas. El botón de documento junto a cada dato dice de dónde sale.</>,
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
              {reviewsBlock}
            </Section>
        </TabPanel>

        {dossierText.fuentes ? <TabPanel id="fuentes">{dossierText.fuentes}</TabPanel> : null}
        <div className="page-end" />
      </ProcessTabs>
      <BackToTop />
      </PageShell>
    </ProvenanceProvider>
  );
}

/** Long lists open on demand (a native disclosure: works without JavaScript). */
function TendererList({ tenderers }: { tenderers: { ruc: string | null; name: string | null; kind: Parameters<typeof partyName>[1] }[] }) {
  const items = tenderers.map((t, i) => (
    <li key={`${t.ruc}-${i}`}>
      {t.kind === "natural_person" || !t.name ? partyName(t.name, t.kind) : <Name value={t.name} />}
      {t.ruc ? (
        <>
          {" "}
          · <Num>{t.ruc}</Num>
        </>
      ) : null}
    </li>
  ));
  if (tenderers.length <= 5) return <ul className="plain">{items}</ul>;
  return (
    <>
      <ul className="plain">{items.slice(0, 3)}</ul>
      <details className="more">
        <summary>Ver las otras {tenderers.length - 3} empresas</summary>
        <ul className="plain">{items.slice(3)}</ul>
      </details>
    </>
  );
}

async function ComparisonSection({ ocid }: { ocid: string }) {
  const r = await getContext(ocid).then(
    (v) => ({ ok: true as const, v }),
    () => ({ ok: false as const, v: null }),
  );
  if (!r.ok) return <p className="muted">La comparación no está disponible ahora. Los datos y las señales del proceso sí lo están.</p>;
  if (!r.v || (!r.v.tenderers && !r.v.ratio && !r.v.window))
    return <p className="muted">No hay datos para comparar este proceso con otros del mismo tipo.</p>;
  return <ContextCharts ctx={r.v} />;
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

/** The dossier text and the sources: two blocks, placed by the page (the sources close the page). */
async function DossierText({ ocid, prov }: { ocid: string; prov: Provenance | null }): Promise<{ texto: React.ReactNode; fuentes: React.ReactNode }> {
  const r = await getDossier(ocid).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) {
    const pending = r.e instanceof ApiError && r.e.status === 503;
    return {
      fuentes: null,
      texto: (
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
      ),
    };
  }
  const d = r.v;
  const grounded = d.grounding_report?.passed === true;
  const modeLabel =
    d.mode === "llm"
      ? "Redactado con un modelo de lenguaje y verificado"
      : d.mode === "template_minimal"
        ? "Plantilla mínima: solo los datos del proceso"
        : "Escrito por una plantilla fija a partir de los datos";
  return {
    texto: (
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
    ),
    fuentes: (
      <Section title="Fuentes" id="fuentes" note="De dónde sale cada dato de este expediente y qué registros se usaron.">
        <ProvenanceList prov={prov} />
        <h3 className="h4" style={{ margin: "28px 0 12px" }}>Registros usados para el expediente</h3>
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
    ),
  };
}

/** Server-rendered, so it reads without JavaScript: each datum with its source, original field and how it was obtained. */
function ProvenanceList({ prov }: { prov: Provenance | null }) {
  if (!prov || prov.facts.length === 0)
    return <p className="muted">El detalle de dónde sale cada dato no está disponible para este proceso.</p>;
  const GROUPS: [string, string][] = [
    ["facts", "Datos del proceso"],
    ["winner", "Quién ganó"],
    ["tenderers", "Oferentes"],
    ["awards", "Adjudicaciones"],
    ["registry", "Registros del proveedor (SRI y Superintendencia de Compañías)"],
    ["signal", "Señales de riesgo"],
    ["score", "Puntaje"],
    ["investigation", "Investigación con agentes"],
  ];
  const groups = GROUPS.map(([id, title]) => ({
    id,
    title,
    facts: prov.facts.filter((f) => f.key.split(".")[0] === id && (id !== "investigation" || f.value)),
  })).filter((g) => g.facts.length);
  const other = prov.facts.filter((f) => !GROUPS.some(([id]) => f.key.split(".")[0] === id));
  if (other.length) groups.push({ id: "other", title: "Otros datos", facts: other });
  return (
    <div className="provlist">
      <ul className="provsrc">
        {prov.sources.map((s) => (
          <li key={s.id} className="card card--tight">
            <p className="h4">{s.name}</p>
            <p className="small muted">
              {[s.publisher, s.licence ? `Licencia: ${s.licence}` : null, s.retrieved_at ? `Obtenido el ${fmtDate(s.retrieved_at)}` : null].filter(Boolean).join(" · ")}
            </p>
            {s.url ? (
              <p className="small" style={{ overflowWrap: "anywhere" }}>
                <a href={s.url} className="inline-link" target="_blank" rel="noopener noreferrer">
                  {s.url}
                  <span className="sr-only"> (se abre en una pestaña nueva)</span>
                </a>
              </p>
            ) : null}
          </li>
        ))}
      </ul>
      {groups.map((g, gi) => (
        <details key={g.id} className="provgroup" open={gi < 1}>
          <summary>
            {g.title} <span className="muted">({g.facts.length})</span>
          </summary>
          <div className="tbl-wrap provtbl" tabIndex={0} role="region" aria-label={`De dónde sale cada dato: ${g.title} (tabla desplazable)`}>
            <table className="tbl">
              <caption className="sr-only">{g.title}: cada dato con su fuente, campo original y forma de obtenerlo</caption>
              <thead>
                <tr>
                  <th scope="col">Dato</th>
                  <th scope="col">Valor publicado</th>
                  <th scope="col">Fuente y campo</th>
                  <th scope="col">Cómo se obtuvo</th>
                  <th scope="col"><span className="sr-only">Copiar cita</span></th>
                </tr>
              </thead>
              <tbody>
                {g.facts.map((f) => (
                  <tr key={f.key}>
                    <th scope="row">{f.label_es}</th>
                    <td data-l="Valor">{f.value || NA}</td>
                    <td data-l="Fuente">
                      {sourceById(prov, f.source_id)?.name ?? NA}
                      {f.source_field ? <div className="cell-sub"><Num>{f.source_field}</Num></div> : null}
                    </td>
                    <td data-l="Cómo se obtuvo">
                      {f.derived ? `Calculado por Veedor. ${f.derivation_es ?? ""}` : "Tal como lo publica la fuente."}
                      {f.verify_es ? <div className="cell-sub">Verificar: {f.verify_es}</div> : null}
                    </td>
                    <td>
                      <CopyButton text={citationFor(prov, f, fmtDate)} label={`Copiar cita: ${f.label_es}`} iconOnly />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </div>
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
