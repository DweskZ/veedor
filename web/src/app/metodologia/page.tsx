import type { Metadata } from "next";
import { Suspense } from "react";
import { getSignals } from "@/lib/api";
import { RISK_LEVELS } from "@/lib/risk";
import { EvaluationText } from "@/components/Evaluation";
import { Term } from "@/components/Term";
import { Card, ErrorState, Num, PageHeader, RiskLegend, Section, Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Metodología" };

const LIMITS = [
  "Un indicador no es un hallazgo ni una acusación. Señala un patrón atípico que necesita una revisión humana y puede tener explicaciones legítimas.",
  "No cubre las contrataciones de emergencia ni las compras por catálogo electrónico: los datos disponibles de esos procesos no permiten calcular las señales.",
  "El estado de un proveedor en el SRI es el de hoy, no el que tenía cuando se le adjudicó.",
  "Los umbrales estadísticos se calculan sobre los propios datos (por método y año). Los pesos del puntaje son decisiones de criterio que todavía falta calibrar.",
  "Los datos abiertos pueden traer errores u omisiones de origen. Veedor no los corrige: si un campo falta, se muestra como no disponible.",
  "A las personas naturales no se las nombra: se muestran como «Persona natural», con el RUC tapado.",
];

const SOURCES = [
  { name: "SERCOP, datos abiertos de contratación (OCDS)", use: "Procesos, oferentes, adjudicaciones, montos y fechas.", licence: "CC BY 3.0 EC" },
  { name: "SRI, registro de contribuyentes", use: "Estado y fecha de inicio de actividades de la empresa que ganó.", licence: "Según los términos de publicación de la fuente" },
  { name: "Superintendencia de Compañías", use: "Datos de compañías y, cuando existen, estados financieros.", licence: "Según los términos de publicación de la fuente" },
];

export default function MethodologyPage() {
  return (
    <>
      <PageHeader
        eyebrow="Metodología"
        title={
          <>
            Cómo se hace <em>el puntaje.</em>
          </>
        }
        lead="Qué mide cada señal, qué significa y qué no puede decir. Cada regla es pública, siempre da el mismo resultado y se aplica igual a todos los procesos."
      />
      <div className="wrap">
        <Section title="Cómo se calcula el puntaje" id="puntaje">
          <Card>
            <div className="prose">
              <p>
                El <Term t="puntaje">puntaje</Term> va de 0 a 100. Es la suma de los pesos de las <Term t="señal de riesgo">señales</Term> que activó el proceso, con tope en 100. Los pesos son decisiones de criterio, están
                documentados y todavía falta calibrarlos: el puntaje sirve para ordenar qué revisar primero, no mide responsabilidad de nadie.
              </p>
              <p>
                Aparte se informa un puntaje de anomalía (<Num>Isolation Forest</Num> sobre variables numéricas del proceso). Se muestra por separado y nunca cambia el
                puntaje de riesgo.
              </p>
            </div>
          </Card>
        </Section>

        <Section
          title="Cómo leer la escala"
          id="escala"
          note="En pantalla el puntaje se agrupa en cinco niveles. Son una forma de presentarlo, no umbrales estadísticos. Cada nivel se distingue por tres cosas a la vez: su nombre, el número de barras llenas y el color."
        >
          <Card>
            <RiskLegend large />
            <p className="muted small" style={{ marginTop: 16 }}>
              Niveles: {RISK_LEVELS.map((l) => (l.min === l.max ? `${l.label} ${l.min}` : `${l.label} ${l.min}–${l.max}`)).join(", ")}.
            </p>
          </Card>
        </Section>

        <Section title="¿El puntaje predice algo?" id="evaluacion" note="La prueba que le hicimos al puntaje, con sus números y qué significa cada uno.">
          <Card>
            <div className="prose">
              <EvaluationText />
            </div>
          </Card>
        </Section>

        <Section title="Catálogo de señales" id="senales" note="Todas las reglas, con su umbral y su alcance.">
          <Suspense fallback={<Skeleton style={{ height: 256 }} />}>
            <Catalogue />
          </Suspense>
        </Section>

        <Section title="Límites" id="limitaciones" note="Lo que Veedor no puede decir.">
          <Card>
            <ul className="limits">
              {LIMITS.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </Card>
        </Section>

        <Section title="De dónde salen los datos" id="fuentes">
          <div className="tbl-wrap" tabIndex={0} role="region" aria-label="Fuentes de datos (tabla desplazable)">
            <table className="tbl" style={{ minWidth: "36rem" }}>
              <caption className="sr-only">Fuentes de datos, uso y licencia</caption>
              <thead>
                <tr>
                  <th scope="col">Fuente</th>
                  <th scope="col">Para qué se usa</th>
                  <th scope="col">Licencia</th>
                </tr>
              </thead>
              <tbody>
                {SOURCES.map((s) => (
                  <tr key={s.name}>
                    <th scope="row">{s.name}</th>
                    <td>{s.use}</td>
                    <td>{s.licence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
        <div className="page-end" />
      </div>
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
    <div className="grid2">
      {result.v.map((d) => (
        <article key={d.code} className={`card ${d.kind === "context" ? "card--quiet" : ""}`}>
          {d.kind === "context" ? <p className="tag">Solo contexto · no suma puntos</p> : null}
          <h3 className="h3">{d.label_es}</h3>
          <p className="sig__code">{d.code}</p>
          <p style={{ marginTop: 12 }}>{d.description_es}</p>
          <dl className="stack small" style={{ marginTop: 14 }}>
            <div>
              <dt className="tag">Regla</dt>
              <dd>{d.threshold_rule_es}</dd>
            </div>
            <div>
              <dt className="tag">Alcance</dt>
              <dd>{d.scope}</dd>
            </div>
            <div>
              <dt className="tag">Umbral</dt>
              <dd>{d.statistical ? "calculado sobre la distribución de los datos" : "fijo"}</dd>
            </div>
          </dl>
          {d.needs_registry ? <p className="muted small" style={{ marginTop: 12 }}>Necesita un registro externo (SRI o Superintendencia de Compañías).</p> : null}
        </article>
      ))}
    </div>
  );
}
