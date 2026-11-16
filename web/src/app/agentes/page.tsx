import type { Metadata } from "next";
import Link from "next/link";
import { AgentDiagram } from "@/components/AgentDiagram";
import { Card, Mono, PageHeader, Section } from "@/components/ui";
import snapshot from "@/data/eval-snapshot.json";
import { fmtInt } from "@/lib/format";
import { SPECIALISTS } from "@/lib/investigation";

export const metadata: Metadata = {
  title: "Agentes",
  description: "Cómo funciona la investigación multiagente de Veedor: qué hace cada agente, sus límites y los resultados medidos.",
};

interface Ci {
  mean: number;
  ci95_low: number;
  ci95_high: number;
}
interface Est {
  estimate: number;
  low: number;
  high: number;
}

const pct = new Intl.NumberFormat("es-EC", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dec3 = new Intl.NumberFormat("es-EC", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const dec1 = new Intl.NumberFormat("es-EC", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isCi = (v: unknown): v is Ci => !!v && isNum((v as Ci).mean) && isNum((v as Ci).ci95_low) && isNum((v as Ci).ci95_high);
const isEst = (v: unknown): v is Est => !!v && isNum((v as Est).estimate) && isNum((v as Est).low) && isNum((v as Est).high);
const pctCi = (c: Ci) => `${pct.format(c.mean * 100)} %`;
const pctRange = (c: Ci) => `IC 95 %: ${pct.format(c.ci95_low * 100)} a ${pct.format(c.ci95_high * 100)} %`;

const AGENTS: { name: string; tools: string; can: string; cannot: string }[] = [
  {
    name: "Supervisor",
    tools: "Ninguna. Hasta 6 despachos por investigación; cada especialista, como máximo dos veces.",
    can: "Elegir qué especialistas corren y en qué orden, con un motivo tomado de una lista cerrada. Sin modelo, una tabla fija ordena según las señales.",
    cannot: "Consultar fuentes, escribir texto o nombrar un objetivo distinto de ganador, entidad o proceso. Una elección inválida se reintenta una vez y luego pasa a la tabla.",
  },
  {
    name: SPECIALISTS.company.name,
    tools: "get_compania_info, get_financials. Hasta 4 consultas.",
    can: "Consultar constitución, capital, situación legal y último ejercicio con estados financieros del ganador, solo si es compañía o entidad pública.",
    cannot: "Consultar personas naturales ni declarar nombres de representantes legales: esos campos se descartan al validar la respuesta.",
  },
  {
    name: SPECIALISTS.tax_registry.name,
    tools: "get_sri_ruc_info, sin establecimientos. Hasta 4 consultas.",
    can: "Leer el estado vigente del RUC y comprobar si coincide con la tabla descargada.",
    cannot: "Cambiar el RUC consultado: el argumento lo construye el código y debe superar un patrón estricto.",
  },
  {
    name: SPECIALISTS.history.name,
    tools: "pair_awards, similar_processes. Hasta 4 consultas.",
    can: "Contar otras adjudicaciones entre la entidad y el proveedor y compras similares de la misma entidad en ±180 días entre los 50 vecinos más cercanos.",
    cannot: "Afirmar relación entre procesos: la similitud es una ayuda de búsqueda. Si falta el índice, la consulta se omite con un motivo cerrado.",
  },
  {
    name: SPECIALISTS.audit.name,
    tools: "list_catalogo, get_contraloria_informe. Hasta 4 consultas.",
    can: "Confirmar «al menos N» informes aprobados cuya entidad auditada coincide con la entidad contratante por comparación exacta de nombre normalizado.",
    cannot: "Descartar informes: lee 3 archivos de 200 filas como máximo. Lo habitual es «no se pudo establecer». Una coincidencia ambigua nunca cuenta.",
  },
  {
    name: "Redactor y verificador",
    tools: "Plantilla determinista; el verificador es una función pura.",
    can: "El modelo, si existe, elige qué hechos van y en qué orden. Cada frase la escribe la plantilla y el verificador comprueba cada cifra, fecha y nombre contra la evidencia.",
    cannot: "Ocultar la sección «Investigación realizada» ni ningún fallo listado en ella, ni tocar las limitaciones, ni ver texto proveniente de una herramienta.",
  },
];

const SAFETY: { title: string; body: string }[] = [
  { title: "Acciones enumeradas", body: "Las decisiones del modelo son identificadores de una lista cerrada, validados en código. Nombres, motivos, acciones y presupuestos se comprueban; un valor fuera de la lista se descarta." },
  { title: "Herramientas de solo lectura", body: "Un único ejecutor llama a las fuentes y rechaza cualquier herramienta fuera de la lista permitida del especialista. Los argumentos los construye el código, nunca el modelo." },
  { title: "Resultados tratados como datos", body: "Todo resultado de una fuente es no confiable. Se valida con un modelo tipado que declara solo los campos usados, se mapea a vocabularios cerrados y nunca se muestra al modelo de lenguaje." },
  { title: "Presupuestos", body: "Cada especialista tiene un tope de consultas, el supervisor un tope de despachos y cada lote un tope de llamadas al modelo. Superado el tope de llamadas al modelo, decide la política determinista." },
  { title: "Personas naturales", body: "No se consultan registros de personas naturales y no se declaran, guardan, muestran ni envían a un modelo nombres de representantes legales. El almacén rechaza un registro que contenga el RUC de una persona natural." },
  { title: "Revisión humana", body: "El expediente es un borrador. Los indicadores señalan patrones atípicos que pueden tener explicaciones legítimas y requieren verificación humana; no constituyen acusaciones." },
];

function Metric({ label, value, range, note, source }: { label: string; value: string; range?: string; note?: string; source: string }) {
  return (
    <Card>
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-2xl font-medium tracking-tight text-ink">{value}</dd>
      {range ? <p className="mt-1 font-mono text-xs text-muted">{range}</p> : null}
      {note ? <p className="mt-2 text-xs leading-relaxed text-muted">{note}</p> : null}
      <p className="mt-2 text-xs text-muted">
        Fuente: <Mono>{source}</Mono>
      </p>
    </Card>
  );
}

function Results() {
  const { investigations: inv, grounding, vector, backtest } = snapshot;
  const llm = inv?.with_llm;
  const noLlm = inv?.no_llm;
  const llmTools = llm?.tool_calls_by_outcome ?? {};
  const tiles: React.ReactNode[] = [];

  if (noLlm && isNum(noLlm.investigations) && noLlm.investigations > 0 && isNum(noLlm.dossiers_passing_verification)) {
    tiles.push(
      <Metric
        key="inv-det"
        label="Investigaciones sin modelo"
        value={`${fmtInt(noLlm.dossiers_passing_verification)} de ${fmtInt(noLlm.investigations)}`}
        note={`Expedientes que superaron la verificación${isNum(noLlm.errors) ? `; errores: ${fmtInt(noLlm.errors)}` : ""}.`}
        source="eval/investigations_run.json"
      />,
    );
  }
  if (llm && isNum(llm.investigations) && llm.investigations > 0 && isNum(llm.dossiers_passing_verification)) {
    tiles.push(
      <Metric
        key="inv-llm"
        label="Investigaciones asistidas por modelo"
        value={`${fmtInt(llm.dossiers_passing_verification)} de ${fmtInt(llm.investigations)}`}
        range={
          llm.model && isNum(llm.model.calls)
            ? `${fmtInt(llm.model.calls)} llamadas · ${fmtInt(llm.model.prompt_tokens)} tokens de entrada · ${fmtInt(llm.model.completion_tokens)} de salida · ${fmtInt(llm.model.invalid_choices)} elecciones inválidas`
            : undefined
        }
        note={`Expedientes que superaron la verificación${isNum(llm.errors) ? `; errores: ${fmtInt(llm.errors)}` : ""}${isNum(llmTools.ok) ? `. Consultas: ${fmtInt(llmTools.ok)} respondieron` : ""}${isNum(llmTools.upstream_error) ? `, ${fmtInt(llmTools.upstream_error)} sin respuesta de la fuente` : ""}${isNum(llmTools.ok) ? "." : ""}`}
        source="eval/investigations_run.json"
      />,
    );
  }
  if (isCi(vector?.agreement_embedding)) {
    const rnd = isCi(vector.agreement_random) ? ` Azar: ${pctCi(vector.agreement_random)} (${pctRange(vector.agreement_random)}).` : "";
    tiles.push(
      <Metric
        key="vec-full"
        label="Coincidencia de CPC (5 dígitos) entre los 10 vecinos más cercanos"
        value={pctCi(vector.agreement_embedding)}
        range={pctRange(vector.agreement_embedding)}
        note={`${isNum(vector.queries) ? `${fmtInt(vector.queries)} consultas sobre el índice completo` : "Índice completo"}${isNum(vector.index_rows) ? ` (${fmtInt(vector.index_rows)} procesos)` : ""}.${rnd} Es optimista: el texto indexado incluye la descripción del CPC.`}
        source="eval/vector_search.json"
      />,
    );
  }
  if (isCi(vector?.pool_description_only)) {
    const withCpc = isCi(vector.pool_with_cpc_text) ? ` Con el texto del CPC en el mismo conjunto: ${pctCi(vector.pool_with_cpc_text)}.` : "";
    tiles.push(
      <Metric
        key="vec-desc"
        label="Coincidencia de CPC, solo con la descripción"
        value={pctCi(vector.pool_description_only)}
        range={pctRange(vector.pool_description_only)}
        note={`${isNum(vector.pool_size) ? `Conjunto de ${fmtInt(vector.pool_size)} procesos con descripción segura` : "Conjunto de prueba"}.${withCpc} La coincidencia de CPC es un indicador indirecto, no relevancia: compras similares pueden tener CPC distintos.`}
        source="eval/vector_search.json"
      />,
    );
  }
  if (isNum(vector?.latency_p50_ms) && isNum(vector?.latency_p95_ms)) {
    tiles.push(
      <Metric
        key="vec-lat"
        label="Latencia de la búsqueda de similares"
        value={`${dec1.format(vector.latency_p50_ms)} ms`}
        range={`mediana · p95: ${dec1.format(vector.latency_p95_ms)} ms`}
        source="eval/vector_search.json"
      />,
    );
  }
  if (isEst(backtest?.auc)) {
    const includesHalf = backtest.auc.low <= 0.5 && backtest.auc.high >= 0.5;
    tiles.push(
      <Metric
        key="auc"
        label="Resultado nulo: AUC del puntaje frente al listado del SRI"
        value={dec3.format(backtest.auc.estimate)}
        range={`IC 95 %: ${dec3.format(backtest.auc.low)} a ${dec3.format(backtest.auc.high)}`}
        note={`${isNum(backtest.n_positives) && isNum(backtest.n_unlabelled) ? `${fmtInt(backtest.n_positives)} empresas listadas frente a ${fmtInt(backtest.n_unlabelled)} no listadas. ` : ""}${includesHalf ? "El intervalo incluye 0,5, el nivel del azar: la evidencia no muestra que el puntaje distinga a las empresas del listado. " : ""}`}
        source="eval/backtest.json · docs/EVALUATION.md"
      />,
    );
  }

  const g = (grounding?.runs ?? []).filter((r) => isNum(r.runs) && isNum(r.final_dossiers_passing_grounding));

  return (
    <>
      {tiles.length ? <dl className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">{tiles}</dl> : <p className="text-sm text-muted">No hay resultados medidos disponibles en esta compilación.</p>}
      {g.length ? (
        <div className="mt-6">
          <h3 className="text-sm font-semibold text-ink">Redacción verificada: dos diseños sobre los mismos procesos</h3>
          <div className="mt-2 overflow-x-auto rounded-lg border border-line bg-surface" tabIndex={0} role="region" aria-label="Resultados de redacción verificada (tabla desplazable)">
            <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
              <caption className="sr-only">Resultados de la verificación de expedientes redactados con modelo</caption>
              <thead>
                <tr className="border-b border-line bg-surface-2 text-xs uppercase tracking-wide text-muted">
                  <th scope="col" className="px-4 py-3 font-medium">Ejecución</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Procesos</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Pasó al primer intento</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Pasó tras reintento</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Plantilla de respaldo</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Expedientes finales verificados</th>
                </tr>
              </thead>
              <tbody>
                {g.map((r, i) => (
                  <tr key={i} className="border-b border-line align-top last:border-b-0">
                    <th scope="row" className="px-4 py-3 text-left font-normal text-ink">
                      {i === 0 ? "El modelo redacta; el verificador rechaza lo no respaldado" : "El modelo elige hechos; la plantilla redacta todo el texto"}
                      <span className="mt-0.5 block font-mono text-xs text-muted">{r.label}</span>
                    </th>
                    <td className="px-4 py-3 text-right font-mono">{fmtInt(r.runs)}</td>
                    <td className="px-4 py-3 text-right font-mono">{fmtInt(r.llm_passed_first_attempt)}</td>
                    <td className="px-4 py-3 text-right font-mono">{fmtInt(r.llm_passed_after_retry)}</td>
                    <td className="px-4 py-3 text-right font-mono">{fmtInt(r.fell_back_to_template)}</td>
                    <td className="px-4 py-3 text-right font-mono">{fmtInt(r.final_dossiers_passing_grounding)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted">
            Fuente: <Mono>eval/llm_grounding_runs.json</Mono>. Que todos los expedientes finales pasen la verificación no significa que el modelo acierte: los que fallan se sustituyen por la plantilla determinista.
          </p>
        </div>
      ) : null}
      <p className="mt-4 max-w-3xl text-xs leading-relaxed text-muted">
        Las cifras de porcentaje se muestran con un decimal, como en <Mono>docs/VECTOR_SEARCH.md</Mono>; los valores provienen de los archivos generados del repositorio
        y se copian a esta página con <Mono>pnpm sync:eval</Mono>.
        {typeof vector?.generated_on === "string" ? ` Medición del índice: ${vector.generated_on}.` : ""}
      </p>
    </>
  );
}

export default function AgentsPage() {
  return (
    <>
      <PageHeader
        title="Cómo funcionan los agentes"
        lead="Un supervisor y cuatro especialistas reúnen evidencia adicional sobre un proceso mediante herramientas de solo lectura. Esa evidencia pasa por el mismo redactor y verificador del expediente. Las investigaciones las produce la línea de comandos y se almacenan; la web solo muestra las almacenadas y nunca inicia una."
      >
        <p className="mt-3 text-sm">
          <Link href="/metodologia" className="text-accent underline underline-offset-2">
            Metodología del puntaje
          </Link>
        </p>
      </PageHeader>

      <Section title="Flujo" id="flujo">
        <AgentDiagram />
        <p className="mt-3 max-w-3xl text-sm text-muted">
          Cada especialista es un subgrafo: primero ordena sus acciones enumeradas y luego ejecuta una por una. Sin modelo, el orden es una secuencia fija.
        </p>
      </Section>

      <Section title="Qué puede y qué no puede hacer cada agente" id="alcance">
        <div className="grid gap-4 lg:grid-cols-2">
          {AGENTS.map((a) => (
            <Card key={a.name}>
              <h3 className="text-base font-semibold text-ink">{a.name}</h3>
              <p className="mt-1 text-xs text-muted">
                <span className="font-medium">Herramientas y presupuesto:</span> {a.tools}
              </p>
              <dl className="mt-3 space-y-2 text-sm leading-relaxed">
                <div>
                  <dt className="font-medium text-ink">Puede</dt>
                  <dd className="text-muted">{a.can}</dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">No puede</dt>
                  <dd className="text-muted">{a.cannot}</dd>
                </div>
              </dl>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Reglas de seguridad" id="seguridad">
        <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {SAFETY.map((s) => (
            <li key={s.title} className="rounded-lg border border-line bg-surface p-5">
              <h3 className="text-sm font-semibold text-ink">{s.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">{s.body}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Resultados medidos" id="resultados">
        <Results />
      </Section>

      <Section title="Límites conocidos" id="limites">
        <Card>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-ink">
            <li>Los datos en vivo provienen de un servidor no oficial sobre fuentes públicas; sus esquemas pueden cambiar. Una interrupción se registra como fallo y se muestra como tal.</li>
            <li>La situación legal y el capital provienen de un directorio instantáneo: la situación no es la vigente al momento de la adjudicación.</li>
            <li>El conteo de compras similares depende del índice vectorial y se limita a los 50 vecinos examinados.</li>
            <li>La búsqueda de informes de la Contraloría puede confirmar «al menos N» informes, pero no descartar ninguno.</li>
            <li>El comportamiento del modelo no se revisó de forma adversarial con un modelo real más allá de un lote de 10 investigaciones.</li>
          </ul>
        </Card>
      </Section>
    </>
  );
}
