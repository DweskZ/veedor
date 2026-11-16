import Link from "next/link";
import { cache, Suspense } from "react";
import { getProcesses, getSignalIndex, getStats } from "@/lib/api";
import { fmtDate, fmtInt, fmtPct, NA } from "@/lib/format";
import type { Stats } from "@/lib/types";
import { EvaluationCard } from "@/components/Evaluation";
import { ProcessTable } from "@/components/ProcessTable";
import { BarList, Card, ErrorState, PageHeader, Section, Skeleton, Stat } from "@/components/ui";

const loadStats = cache(getStats);

export default function Home() {
  return (
    <>
      <PageHeader
        title="Radar abierto de riesgo en la contratación pública del Ecuador"
        lead="Indicadores de riesgo, con su evidencia. Veedor calcula señales transparentes sobre los datos abiertos de contratación y muestra de dónde sale cada una."
      />
      <Suspense fallback={<Skeleton className="h-28" />}>
        <Headline />
      </Suspense>
      <Section title="Qué es y qué no es" id="alcance">
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <h3 className="font-semibold text-ink">Qué es</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Un instrumento de análisis. Cada proceso recibe un puntaje a partir de reglas documentadas y cada señal muestra
              los valores observados, el umbral y la fuente. Cualquier persona puede revisar la evidencia y verificarla.
            </p>
          </Card>
          <Card>
            <h3 className="font-semibold text-ink">Qué no es</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              No es una acusación ni una determinación de responsabilidades. Un indicador señala un patrón atípico que merece
              revisión humana; puede tener explicaciones legítimas. No cubre emergencias ni catálogo electrónico.{" "}
              <Link href="/metodologia" className="text-accent underline underline-offset-2">
                Ver limitaciones
              </Link>
              .
            </p>
          </Card>
        </div>
        <div className="mt-4">
          <EvaluationCard />
        </div>
      </Section>
      <Section title="Cómo funciona" id="como-funciona">
        <div className="grid gap-4 md:grid-cols-2">
          <Link href="/metodologia" className="group rounded-lg border border-line bg-surface p-5 hover:border-accent">
            <h3 className="font-semibold text-ink group-hover:underline">Metodología</h3>
            <p className="mt-1 text-sm leading-relaxed text-muted">Cómo se calcula el puntaje, qué significa cada señal y qué no puede decir.</p>
          </Link>
          <Link href="/agentes" className="group rounded-lg border border-line bg-surface p-5 hover:border-accent">
            <h3 className="font-semibold text-ink group-hover:underline">Agentes de investigación</h3>
            <p className="mt-1 text-sm leading-relaxed text-muted">Un supervisor y cuatro especialistas consultan fuentes públicas de solo lectura. Qué pueden hacer, sus límites y resultados medidos.</p>
          </Link>
        </div>
      </Section>
      <Suspense fallback={<Skeleton className="mt-12 h-72" />}>
        <Charts />
      </Suspense>
      <Section
        title="Procesos con mayor puntaje"
        id="top"
        aside={
          <Link href="/procesos" className="text-sm text-accent underline underline-offset-2">
            Ver todos los procesos
          </Link>
        }
      >
        <Suspense fallback={<Skeleton className="h-96" />}>
          <TopProcesses />
        </Suspense>
      </Section>
    </>
  );
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
    <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Stat label="Procesos analizados" value={fmtInt(stats.processes_total)} />
      <Stat
        label="Procesos con al menos una señal"
        value={fmtInt(stats.processes_with_signals)}
        hint={
          stats.processes_total && stats.processes_with_signals != null
            ? `${fmtPct(stats.processes_with_signals / stats.processes_total)} del total`
            : undefined
        }
      />
      <Stat label="Señales activadas" value={fmtInt(fired)} hint={`${stats.signal_counts.length} tipos`} />
      <Stat label="Período de datos" value={<span className="text-xl">{years}</span>} hint={`Último dato: ${fmtDate(stats.last_data_date)}`} />
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
    return { key: String(lower), label: lower === 90 ? "90–100" : `${lower}–${lower + 9}`, value: counts.get(lower) ?? 0 };
  });
}

async function Charts() {
  const r = await loadStats().then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!r.ok) {
    return (
      <div className="mt-12">
        <ErrorState title="No se pudieron cargar los gráficos" detail={r.e instanceof Error ? r.e.message : undefined} />
      </div>
    );
  }
  const stats = r.v;
  const withSignals = stats.processes_with_signals ?? 0;
  const none = stats.processes_total != null ? stats.processes_total - withSignals : null;
  const buckets = signalBuckets(stats);
  return (
    <div className="mt-12 grid gap-8 lg:grid-cols-2">
      <section aria-labelledby="dist">
        <h2 id="dist" className="mb-4 text-xl font-semibold tracking-tight text-ink">
          Distribución del puntaje de riesgo
        </h2>
        <Card>
          <p className="text-sm text-muted">
            Sin señales:{" "}
            <span className="font-mono text-ink">
              {fmtInt(none)}
              {none != null && stats.processes_total ? ` (${fmtPct(none / stats.processes_total)})` : ""}
            </span>{" "}
            procesos tienen puntaje 0. El gráfico muestra solo los {fmtInt(withSignals)} procesos con al menos una señal.
          </p>
          <div className="mt-4">
            <BarList total={withSignals} format={fmtInt} items={buckets} />
          </div>
          <p className="mt-4 border-t border-line pt-3 text-xs text-muted">
            Intervalos de 10 puntos sobre el puntaje de 0 a 100 (el último incluye 100).
          </p>
        </Card>
      </section>
      <section aria-labelledby="bytype">
        <h2 id="bytype" className="mb-4 text-xl font-semibold tracking-tight text-ink">
          Señales por tipo
        </h2>
        <Card>
          {stats.signal_counts.length ? (
            <BarList
              format={fmtInt}
              items={[...stats.signal_counts]
                .sort((a, b) => b.count - a.count)
                .map((c) => ({ key: c.code, label: c.label_es ?? c.code, value: c.count }))}
            />
          ) : (
            <p className="text-sm text-muted">Aún no hay señales calculadas.</p>
          )}
        </Card>
      </section>
    </div>
  );
}

async function TopProcesses() {
  const result = await Promise.all([getProcesses({ sort: "-risk_score", page_size: "10" }), getSignalIndex()]).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!result.ok) return <ErrorState detail={result.e instanceof Error ? result.e.message : undefined} />;
  const [page, index] = result.v;
  if (!page.items.length) return <p className="text-sm text-muted">No hay procesos con puntaje para mostrar.</p>;
  return <ProcessTable rows={page.items} labels={index.labels} context={index.context} caption="Procesos con mayor puntaje de riesgo" />;
}
