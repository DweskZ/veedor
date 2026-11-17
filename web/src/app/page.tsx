import Link from "next/link";
import { PageFrame } from "@/components/PageFrame";
import { cache } from "react";
import { getProcesses, getRegions, getSignalIndex, getStats } from "@/lib/api";
import { fmtDate, fmtInt, fmtPct, NA } from "@/lib/format";
import { SPECIALISTS, SPECIALIST_ORDER } from "@/lib/investigation";
import type { Stats } from "@/lib/types";
import { Art } from "@/components/Art";
import { EvaluationBlock } from "@/components/Evaluation";
import { RandomProcessButton } from "@/components/RandomProcessButton";
import { RegionExplorer } from "@/components/RegionExplorer";
import { Term } from "@/components/Term";
import { ProcessTable } from "@/components/ProcessTable";
import { BarList, ErrorState, Fig, RiskLegend } from "@/components/ui";

const loadStats = cache(getStats);

export default function Home() {
  return (
    <PageFrame>
      <Hero />
      <WhatItIs />
      <HowToRead />
      <section className="sec sec--ice sec--compact" aria-labelledby="numeros-h">
        <div className="wrap">
          <header className="sec__head reveal">
            <p className="eyebrow">Los datos, hasta hoy</p>
            <h2 className="h2 h2--sm" id="numeros-h">
              Lo que Veedor <em>ha leído.</em>
            </h2>
            <p className="lead">
              Estas cifras cuentan datos atípicos según reglas públicas, no problemas comprobados. Una señal no acusa a
              nadie.
            </p>
          </header>
          <Headline />
          <Charts />
        </div>
      </section>
      <section className="sec sec--ice sec--compact" aria-labelledby="mapa-h" style={{ paddingTop: 0 }}>
        <div className="wrap">
          <header className="sec__head reveal">
            <p className="eyebrow">Mapa</p>
            <h2 className="h2 h2--sm" id="mapa-h">
              Señales <em>por provincia.</em>
            </h2>
            <p className="lead">Por provincia, qué parte de los procesos competitivos tiene alguna señal.</p>
          </header>
          <HomeMap />
        </div>
      </section>
      <Agents />
      <Evaluation />
      <section className="sec sec--ice sec--compact" aria-labelledby="top-h">
        <div className="wrap">
          <header className="sec__head reveal">
            <p className="eyebrow">Para empezar</p>
            <h2 className="h2 h2--sm" id="top-h">
              Los procesos con <em>mayor puntaje.</em>
            </h2>
            <p className="lead">
              Un puntaje alto no es una culpa: es una guía para decidir qué mirar primero. Aquí está cómo se lee la escala.
            </p>
            <div style={{ marginTop: 20 }}>
              <RiskLegend large />
            </div>
          </header>
          <div className="top-procs">
            <TopProcesses />
          </div>
          <div className="actions">
            <Link href="/procesos" className="btn btn--tc">
              Ver todos los procesos
            </Link>
          </div>
        </div>
      </section>
    </PageFrame>
  );
}

function Hero() {
  return (
    <section className="hero sec--ice" aria-labelledby="hero-h">
      <div className="wrap hero__grid">
        <div>
          <p className="eyebrow">Compras públicas · Ecuador</p>
          <h1 className="display" id="hero-h">
            <span>Mira cómo</span>
            <span>compra el</span>
            <span>
              <em>Estado.</em>
            </span>
          </h1>
          <p className="hero__sub">
            Veedor lee los <b>datos abiertos</b> de las compras públicas y marca los procesos con <b>señales atípicas.</b> Una señal no
            acusa a nadie: invita a mirar mejor.
          </p>
          <div className="actions">
            <Link href="/procesos" className="btn btn--tc">
              Explorar procesos
            </Link>
            <a href="#como" className="btn btn--line">
              Cómo funciona
            </a>
            <RandomProcessButton className="link hero__rnd" label="Proceso al azar" />
          </div>
        </div>
        <div className="stage">
          <Art name="hero" priority sizes="(min-width: 900px) 40vw, 92vw" className="stage__img" />
        </div>
      </div>
    </section>
  );
}

function WhatItIs() {
  return (
    <section className="sec sec--ice sec--compact" aria-labelledby="que-h" style={{ paddingTop: 0 }}>
      <div className="wrap">
        <header className="sec__head reveal">
          <p className="eyebrow">En pocas palabras</p>
          <h2 className="h2 h2--sm" id="que-h">
            Qué es y qué <em>no es.</em>
          </h2>
        </header>
        <div className="is-grid">
          <article className="card is is--yes reveal">
            <div className="is__head">
              <span className="is__mark" aria-hidden="true">
                ✓
              </span>
              <h3>Qué es</h3>
            </div>
            <p>Una forma de leer cómo compra el Estado, con los datos abiertos de contratación pública del SERCOP.</p>
            <ul className="ticks">
              <li>Cada proceso recibe un <Term t="puntaje">puntaje</Term> de 0 a 100, a partir de reglas públicas.</li>
              <li>Cada <Term t="señal de riesgo">señal</Term> te muestra lo que se observó, el umbral de la regla y de dónde salen los datos.</li>
              <li>Tú puedes comprobarlo en la fuente oficial.</li>
            </ul>
          </article>
          <article className="card is is--no reveal" style={{ "--d": "0.1s" } as React.CSSProperties}>
            <div className="is__head">
              <span className="is__mark" aria-hidden="true">
                ✕
              </span>
              <h3>Qué no es</h3>
            </div>
            <p>Una acusación. Ni una conclusión sobre nadie.</p>
            <ul className="ticks">
              <li>Una señal marca algo atípico que merece una segunda mirada; casi siempre tiene explicaciones normales.</li>
              <li>No muestra <Term t="persona natural">personas naturales</Term>: aparecen como «Persona natural», con el RUC tapado.</li>
              <li>No cubre emergencias ni compras por <Term t="catálogo electrónico">catálogo electrónico</Term>.</li>
            </ul>
            <Link href="/metodologia#limitaciones" className="link">
              Ver todos los límites
            </Link>
          </article>
        </div>
      </div>
    </section>
  );
}

function HowToRead() {
  return (
    <section className="sec sec--ink sec--compact" id="como" aria-labelledby="como-h">
      <div className="wrap">
        <header className="sec__head reveal">
          <p className="eyebrow">Cómo funciona</p>
          <h2 className="h2 h2--sm" id="como-h">
            Cómo usar Veedor <em>en tres pasos</em>.
          </h2>
        </header>
        <ol className="steps">
          <li className="step">
            <div className="step__media">
              <span className="pin pin--corner" aria-hidden="true">1</span>
              <div style={{ position: "relative", width: "100%", maxWidth: 340 }}>
                <Art name="datos" priority sizes="340px" alt="Dibujo isométrico de un archivo con estantes de carpetas: los procesos de contratación." />
              </div>
            </div>
            <div className="step__text">
              <p className="tag">Paso 1 de 3</p>
              <h3 className="h3">
                <span className="sr-only">Paso 1. </span>Elige un proceso
              </h3>
              <p>Filtra por año, método o tipo de señal. Cada fila es una compra del Estado, con su puntaje.</p>
              <Link href="/procesos" className="link step__go">Abrir el explorador <span aria-hidden="true">→</span></Link>
            </div>
          </li>
          <li className="step">
            <div className="step__media">
              <span className="pin pin--corner" aria-hidden="true">2</span>
              <div style={{ position: "relative", width: "100%", maxWidth: 320 }}>
                <div className="mock" aria-label="Ejemplo ilustrativo de una señal">
                  <p className="mock__t">Oferente único</p>
                  <div className="mock__row">
                    <b>Qué se observó</b>
                    Una sola empresa presentó oferta.
                    <div className="mock__bar" aria-hidden="true" />
                  </div>
                  <div className="mock__row">
                    <b>Por qué puede importar</b>
                    Sin competencia de precios.
                  </div>
                  <div className="mock__row">
                    <b>Cómo puede ser normal</b>
                    Es el único distribuidor.
                  </div>
                  <p className="mock__note">Ejemplo ilustrativo, no es un proceso real.</p>
                </div>
              </div>
            </div>
            <div className="step__text">
              <p className="tag">Paso 2 de 3</p>
              <h3 className="h3">
                <span className="sr-only">Paso 2. </span>Mira las señales y de dónde salen
              </h3>
              <p>Cada señal responde tres preguntas: qué se observó, por qué puede importar y cómo puede ser normal. La evidencia va al lado.</p>
              <RandomProcessButton className="link step__go step__btn" label="Ver un proceso de ejemplo →" />
              <Link href="/procesos?signal=SINGLE_BIDDER" className="link step__go nojs-only">Ver procesos con la señal «oferente único» <span aria-hidden="true">→</span></Link>
            </div>
          </li>
          <li className="step">
            <div className="step__media">
              <span className="pin pin--corner" aria-hidden="true">3</span>
              <div style={{ position: "relative", width: "100%", maxWidth: 340 }}>
                <Art name="verificacion" priority sizes="340px" alt="Dibujo isométrico de una oficina de registro público con un mostrador y un sello: la fuente oficial." />
              </div>
            </div>
            <div className="step__text">
              <p className="tag">Paso 3 de 3</p>
              <h3 className="h3">
                <span className="sr-only">Paso 3. </span>Verifica en la fuente oficial
              </h3>
              <p>Cada proceso trae su código y sus fuentes para que lo compruebes en el portal de datos abiertos del SERCOP y en el SRI. Veedor no es la última palabra.</p>
              <Link href="/metodologia#fuentes" className="link step__go">Ver de dónde salen los datos <span aria-hidden="true">→</span></Link>
            </div>
          </li>
        </ol>
      </div>
    </section>
  );
}

function Agents() {
  const names = SPECIALIST_ORDER.map((id) => SPECIALISTS[id].name);
  return (
    <section className="sec sec--ink sec--compact" aria-labelledby="ag-h">
      <div className="wrap agents__grid">
        <div className="reveal">
          <p className="eyebrow">Investiga con agentes</p>
          <h2 className="h2 h2--sm" id="ag-h">
            Un supervisor. <em>Cinco</em> especialistas.
          </h2>
          <p className="lead">
            Cuando un proceso lo merece, un supervisor manda a cinco especialistas a consultar fuentes oficiales, solo para leer. Todo lo
            que encuentran pasa por un verificador: cada cifra tiene que existir en los datos.
          </p>
          <div className="actions">
            <Link href="/agentes" className="btn btn--tc">
              Cómo funcionan los agentes
            </Link>
          </div>
        </div>
        <div className="agents__panel reveal" style={{ "--d": "0.1s" } as React.CSSProperties}>
          <Art name="investigacion" crop sizes="(min-width: 900px) 55vw, 90vw" alt="Dibujo isométrico de una oficina, sin personas: una mesa redonda con sillas y un escritorio con un portátil, donde se consultan las fuentes." />
          <div className="mini" role="img" aria-label={`Un supervisor envía a cinco especialistas a consultar fuentes oficiales: ${names.join(", ")}.`}>
            <div className="mini__sup" aria-hidden="true">Supervisor</div>
            <div className="mini__line" aria-hidden="true" />
            <div className="mini__row" aria-hidden="true">
              {names.map((n) => (
                <div key={n} className="mini__spec">
                  {n}
                </div>
              ))}
            </div>
            <div className="mini__line" aria-hidden="true" />
            <div className="mini__src" aria-hidden="true">Fuentes oficiales, de solo lectura</div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Evaluation() {
  return (
    <section className="sec sec--tc sec--compact" aria-labelledby="ev-h">
      <div className="wrap">
        <p className="eyebrow">Qué tan bien funciona</p>
        <EvaluationBlock />
      </div>
    </section>
  );
}

async function HomeMap() {
  const r = await getRegions().then(
    (v) => ({ ok: true as const, v }),
    () => ({ ok: false as const }),
  );
  if (!r.ok || r.v.items.length === 0)
    return (
      <p className="muted">
        El mapa no está disponible ahora.{" "}
        <Link href="/mapa" className="inline-link">
          Intentar en su página
        </Link>
        .
      </p>
    );
  return <RegionExplorer rows={r.v.items} national={r.v.national} compact />;
}

async function Headline() {
  const r = await loadStats().then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) return <ErrorState detail={r.e instanceof Error ? r.e.message : undefined} />;
  const stats = r.v;
  const fired = stats.signal_counts.reduce((a, c) => a + c.count, 0);
  const years = stats.first_year && stats.last_year ? `${stats.first_year}–${stats.last_year}` : NA;
  return (
    <dl className="figs figs--4">
      <Fig label="procesos analizados" value={fmtInt(stats.processes_total)} />
      <Fig
        label="procesos con al menos una señal"
        value={fmtInt(stats.processes_with_signals)}
        hint={
          stats.processes_total && stats.processes_with_signals != null
            ? `${fmtPct(stats.processes_with_signals / stats.processes_total)} del total`
            : undefined
        }
      />
      <Fig label="señales encontradas" value={fmtInt(fired)} hint={`de ${stats.signal_counts.length} tipos distintos`} />
      <Fig label="años de datos" value={years} medium hint={`Último dato: ${fmtDate(stats.last_data_date)}`} />
    </dl>
  );
}

/** 10-point buckets among processes with at least one signal. The 0-9 bucket is derived: with-signal total minus the other buckets. */
function signalBuckets(stats: Stats) {
  const withSignals = stats.processes_with_signals ?? 0;
  const rest = stats.score_distribution.filter((b) => b.lower >= 10);
  const counts = new Map(rest.map((b) => [b.lower, b.count]));
  counts.set(0, Math.max(0, withSignals - rest.reduce((a, b) => a + b.count, 0)));
  const top = Math.max(...[...counts].filter(([, c]) => c > 0).map(([l]) => l), 0);
  const bottom = Math.min(...[...counts].filter(([, c]) => c > 0).map(([l]) => l), top);
  return Array.from({ length: (top - bottom) / 10 + 1 }, (_, i) => {
    const lower = bottom + i * 10;
    return { key: String(lower), label: lower === 90 ? "90–100 puntos" : `${lower}–${lower + 9} puntos`, value: counts.get(lower) ?? 0 };
  });
}

async function Charts() {
  const r = await loadStats().then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) return null;
  const stats = r.v;
  const withSignals = stats.processes_with_signals ?? 0;
  const none = stats.processes_total != null ? stats.processes_total - withSignals : null;
  const buckets = signalBuckets(stats);
  return (
    <div className="grid2 stats-charts">
      <section aria-labelledby="dist" className="card">
        <h3 className="h3" id="dist">
          Cuántos procesos hay por puntaje
        </h3>
        <p className="small" style={{ marginTop: 10, marginBottom: 20 }}>
          <b>{fmtInt(none)}</b>
          {none != null && stats.processes_total ? ` (${fmtPct(none / stats.processes_total)})` : ""} procesos no tienen ninguna señal y quedan en 0. El gráfico
          muestra los {fmtInt(withSignals)} que sí tienen al menos una.
        </p>
        <BarList total={withSignals} format={fmtInt} items={buckets} />
        <p className="muted small" style={{ marginTop: 18, paddingTop: 12, borderTop: "2px solid var(--ice-deep)" }}>
          Intervalos de 10 puntos sobre el puntaje de 0 a 100 (el último incluye 100).
        </p>
      </section>
      <section aria-labelledby="bytype" className="card">
        <h3 className="h3" id="bytype">
          Qué señales aparecen más
        </h3>
        <div style={{ marginTop: 20 }}>
          {stats.signal_counts.length ? (
            <BarList
              format={fmtInt}
              highlightTop
              items={[...stats.signal_counts].sort((a, b) => b.count - a.count).map((c) => ({ key: c.code, label: c.label_es ?? c.code, value: c.count }))}
            />
          ) : (
            <p className="muted">Todavía no hay señales calculadas.</p>
          )}
        </div>
      </section>
    </div>
  );
}

async function TopProcesses() {
  const result = await Promise.all([getProcesses({ sort: "-risk_score", page_size: "8" }), getSignalIndex()]).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!result.ok) return <ErrorState detail={result.e instanceof Error ? result.e.message : undefined} />;
  const [page, index] = result.v;
  if (!page.items.length) return <p className="muted">No hay procesos con puntaje para mostrar.</p>;
  return <ProcessTable rows={page.items} labels={index.labels} context={index.context} caption="Procesos con mayor puntaje de riesgo" />;
}
