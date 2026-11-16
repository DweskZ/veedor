import { SPECIALISTS } from "@/lib/investigation";

/**
 * The investigation pipeline drawn in code (docs/AGENTS.md "Graph") in the Ruray line style: ink strokes,
 * white fills, one terracotta element (the supervisor). Wide screens get the SVG; narrower screens get the
 * same stages as a numbered vertical list.
 */

const SPEC_ORDER = ["company", "tax_registry", "history", "audit"] as const;
const SPEC_TOOLS: Record<(typeof SPEC_ORDER)[number], string> = {
  company: "get_compania_info · get_financials",
  tax_registry: "get_sri_ruc_info",
  history: "pair_awards · similar_processes",
  audit: "list_catalogo · get_contraloria_informe",
};

const STAGES = [
  { name: "Evidencia del proceso", note: "Hechos, señales y registros ya cargados" },
  { name: "Supervisor", note: "Elige especialistas y orden entre opciones cerradas (hasta 6 despachos)" },
  { name: "Especialistas (4)", note: "Cada uno ejecuta acciones enumeradas con herramientas de solo lectura" },
  { name: "Evidencia ampliada", note: "Hechos tipados con su fuente, o «la fuente no respondió»" },
  { name: "Redactor", note: "Una plantilla escribe cada frase; el modelo, si existe, solo ordena hechos" },
  { name: "Verificador", note: "Cada cifra, fecha y nombre debe existir en la evidencia" },
  { name: "Expediente", note: "Si falla: un reintento y luego plantilla determinista" },
];

const INK = "#1A1F36";
const TC = "#D9480F";
const MUTED = "#5B6384";

function Box({ x, y, w, h, title, sub, accent = false }: { x: number; y: number; w: number; h: number; title: string; sub?: string; accent?: boolean }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={20} fill="#fff" stroke={accent ? TC : INK} strokeWidth={accent ? 5 : 3} />
      <text x={x + 18} y={y + 30} fontSize={18} fontWeight={800} letterSpacing={-0.3}>
        {title}
      </text>
      {sub ? (
        <text x={x + 18} y={y + 54} fontSize={13.5} fontWeight={600} style={{ fill: MUTED }}>
          {sub}
        </text>
      ) : null}
    </g>
  );
}

function Wide() {
  const line = { stroke: INK, strokeWidth: 3, fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;
  const specY = (i: number) => i * 90;
  return (
    <svg
      viewBox="0 0 1000 566"
      role="img"
      aria-labelledby="diagram-title diagram-desc"
      className="only-xl"
    >
      <title id="diagram-title">Flujo de una investigación con agentes</title>
      <desc id="diagram-desc">
        La evidencia del proceso llega al supervisor, que despacha a cuatro especialistas y recibe su informe. La evidencia ampliada pasa al
        redactor, luego al verificador y finalmente al expediente; si la verificación falla se usa una plantilla determinista.
      </desc>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M1 1 L9 5 L1 9" fill="none" stroke={INK} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </marker>
      </defs>

      <Box x={0} y={133} w={160} h={80} title="Evidencia" sub="del proceso" />
      <path d="M160 173 H208" {...line} markerEnd="url(#arrow)" />
      <Box x={208} y={93} w={200} h={160} title="Supervisor" sub="sin herramientas" accent />
      <text x={226} y={184} fontSize={13.5} fontWeight={600} style={{ fill: INK }}>
        <tspan x={226}>Máx. 6 despachos;</tspan>
        <tspan x={226} dy={19}>cada especialista,</tspan>
        <tspan x={226} dy={19}>hasta 2 veces.</tspan>
      </text>
      {SPEC_ORDER.map((id, i) => {
        const cy = specY(i) + 38;
        return (
          <g key={id}>
            <path d={`M408 173 C 450 173, 450 ${cy}, 500 ${cy}`} {...line} markerStart="url(#arrow)" markerEnd="url(#arrow)" />
            <Box x={500} y={specY(i)} w={500} h={76} title={SPECIALISTS[id].name} sub={`${SPEC_TOOLS[id]} · máx. 4 consultas`} />
          </g>
        );
      })}

      <path d="M750 346 V394 H115 V434" {...line} markerEnd="url(#arrow)" />
      <text x={766} y={384} fontSize={14} fontWeight={700}>
        hechos tipados, con su fuente
      </text>

      <Box x={0} y={434} w={230} h={86} title="Evidencia ampliada" sub="hechos + fallos visibles" />
      <path d="M230 477 H272" {...line} markerEnd="url(#arrow)" />
      <Box x={272} y={434} w={220} h={86} title="Redactor" sub="plantilla determinista" />
      <path d="M492 477 H534" {...line} markerEnd="url(#arrow)" />
      <Box x={534} y={434} w={230} h={86} title="Verificador" sub="cada cifra, contra datos" />
      <path d="M764 477 H806" {...line} markerEnd="url(#arrow)" />
      <Box x={806} y={434} w={194} h={86} title="Expediente" sub="borrador para revisión" />
      <text x={534} y={552} fontSize={14} fontWeight={700}>
        Si falla: un reintento y luego plantilla determinista.
      </text>
    </svg>
  );
}

function Narrow() {
  return (
    <ol className="stages not-xl" aria-label="Etapas de una investigación con agentes">
      {STAGES.map((s, i) => (
        <li key={s.name}>
          <div className={`stage-card ${s.name === "Supervisor" ? "stage-card--tc" : ""}`}>
            <p className="h4">
              <span className="num">{i + 1}.</span> {s.name}
            </p>
            <p className="small" style={{ marginTop: 2 }}>{s.note}</p>
            {s.name.startsWith("Especialistas") ? (
              <ul className="ticks" style={{ marginTop: 8 }}>
                {SPEC_ORDER.map((id) => (
                  <li key={id} className="small">
                    {SPECIALISTS[id].name} · máx. 4 consultas
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          {i < STAGES.length - 1 ? (
            <p aria-hidden="true" className="stage-arrow">
              ↓
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export function AgentDiagram() {
  return (
    <div className="diagram">
      <Wide />
      <Narrow />
    </div>
  );
}
