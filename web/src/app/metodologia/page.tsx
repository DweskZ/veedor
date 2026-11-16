import type { Metadata } from "next";
import { Suspense } from "react";
import { getSignals } from "@/lib/api";
import { RISK_LEVELS } from "@/lib/risk";
import { EvaluationText } from "@/components/Evaluation";
import { Card, ErrorState, Mono, PageHeader, RiskLegend, Section, Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Metodología" };

const LIMITS = [
  "Un indicador no es un hallazgo ni una acusación. Señala un patrón atípico que requiere revisión humana y puede tener explicaciones legítimas.",
  "No se cubren las contrataciones de emergencia ni las compras por catálogo electrónico: los datos disponibles de esos procesos no permiten calcular las señales.",
  "El estado de un proveedor en el SRI es el estado actual, no el que tenía al momento de la adjudicación.",
  "Los umbrales estadísticos se calculan sobre los propios datos (por método y año); los pesos del puntaje son decisiones de criterio pendientes de calibración.",
  "Los datos abiertos pueden tener errores u omisiones de origen. Veedor no los corrige: si un campo falta, se muestra como no disponible.",
  "Las personas naturales no se nombran: se muestran como persona natural con el RUC enmascarado.",
];

const SOURCES = [
  { name: "SERCOP, datos abiertos de contratación (OCDS)", use: "Procesos, oferentes, adjudicaciones, montos y fechas.", licence: "CC BY 3.0 EC" },
  { name: "SRI, registro de contribuyentes", use: "Estado y fecha de inicio de actividades del adjudicatario.", licence: "Según los términos de publicación de la fuente" },
  { name: "Superintendencia de Compañías", use: "Datos de compañías y, cuando existen, estados financieros.", licence: "Según los términos de publicación de la fuente" },
];

export default function MethodologyPage() {
  return (
    <>
      <PageHeader
        title="Metodología"
        lead="Cómo se calculan los indicadores, qué significan y qué no pueden decir. Cada regla es pública, determinista y se aplica igual a todos los procesos."
      />
      <Section title="Cómo se calcula el puntaje" id="puntaje">
        <Card>
          <div className="space-y-3 text-sm leading-relaxed text-ink">
            <p>
              El puntaje de riesgo va de 0 a 100 y es una suma ponderada de las señales activadas por el proceso, con tope en
              100. Los pesos son decisiones de criterio, documentadas y pendientes de calibración; el puntaje ordena la
              revisión, no mide responsabilidad.
            </p>
            <p>
              Aparte se informa un puntaje de anomalía (<Mono>Isolation Forest</Mono> sobre variables numéricas del proceso).
              Se muestra por separado y nunca modifica el puntaje de riesgo.
            </p>
            <p>En la interfaz, el puntaje se agrupa en bandas de presentación que no son umbrales estadísticos:</p>
            <RiskLegend />
            <p className="text-muted">Bandas: {RISK_LEVELS.map((l) => (l.min === l.max ? `${l.label} ${l.min}` : `${l.label} ${l.min}–${l.max}`)).join(", ")}.</p>
          </div>
        </Card>
      </Section>

      <Section title="Evaluación" id="evaluacion">
        <Card>
          <div className="space-y-3 text-sm leading-relaxed text-ink">
            <EvaluationText />
          </div>
        </Card>
      </Section>

      <Section title="Catálogo de señales" id="senales">
        <Suspense fallback={<Skeleton className="h-64" />}>
          <Catalogue />
        </Suspense>
      </Section>

      <Section title="Limitaciones" id="limitaciones">
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-ink">
          {LIMITS.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </Section>

      <Section title="Fuentes de datos y licencias" id="fuentes">
        <div className="overflow-x-auto rounded-lg border border-line bg-surface" tabIndex={0} role="region" aria-label="Fuentes de datos (tabla desplazable)">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <caption className="sr-only">Fuentes de datos, uso y licencia</caption>
            <thead>
              <tr className="border-b border-line bg-surface-2 text-xs uppercase tracking-wide text-muted">
                <th scope="col" className="px-4 py-3 font-medium">Fuente</th>
                <th scope="col" className="px-4 py-3 font-medium">Uso</th>
                <th scope="col" className="px-4 py-3 font-medium">Licencia</th>
              </tr>
            </thead>
            <tbody>
              {SOURCES.map((s) => (
                <tr key={s.name} className="border-b border-line last:border-b-0">
                  <th scope="row" className="px-4 py-3 text-left font-medium text-ink">{s.name}</th>
                  <td className="px-4 py-3 text-muted">{s.use}</td>
                  <td className="px-4 py-3">{s.licence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}

async function Catalogue() {
  const result = await getSignals().then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  if (!result.ok) return <ErrorState detail={result.e instanceof Error ? result.e.message : undefined} />;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {result.v.map((d) => (
        <article key={d.code} className="rounded-lg border border-line bg-surface p-5">
          <h3 className="font-semibold text-ink">{d.label_es}</h3>
          <p className="mt-0.5 text-xs text-muted">
            <Mono>{d.code}</Mono>
          </p>
          <p className="mt-3 text-sm leading-relaxed text-ink">{d.description_es}</p>
          <dl className="mt-3 space-y-1.5 text-sm">
            <div>
              <dt className="inline text-muted">Regla: </dt>
              <dd className="inline">{d.threshold_rule_es}</dd>
            </div>
            <div>
              <dt className="inline text-muted">Alcance: </dt>
              <dd className="inline">{d.scope}</dd>
            </div>
            <div>
              <dt className="inline text-muted">Umbral: </dt>
              <dd className="inline">{d.statistical ? "calculado sobre la distribución de los datos" : "fijo"}</dd>
            </div>
            {d.needs_registry ? <p className="text-muted">Requiere registro externo (SRI o Superintendencia de Compañías).</p> : null}
          </dl>
        </article>
      ))}
    </div>
  );
}
