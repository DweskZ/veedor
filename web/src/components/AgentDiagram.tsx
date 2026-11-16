import { SPECIALISTS } from "@/lib/investigation";

/**
 * The investigation pipeline drawn in code (docs/AGENTS.md "Graph"). Colours come from the theme tokens, so it
 * follows light/dark. Wide screens get the SVG; narrow screens get the same stages as a vertical list.
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

function Box({ x, y, w, h, title, sub, strong = false }: { x: number; y: number; w: number; h: number; title: string; sub?: string; strong?: boolean }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill="var(--surface)" stroke={strong ? "var(--accent)" : "var(--line)"} strokeWidth={strong ? 2 : 1.25} />
      <text x={x + 14} y={y + 26} fontSize={15} fontWeight={600} fill="var(--ink)">
        {title}
      </text>
      {sub ? (
        <text x={x + 14} y={y + 46} fontSize={12} fill="var(--muted)" fontFamily="var(--font-plex-mono), ui-monospace, monospace">
          {sub}
        </text>
      ) : null}
    </g>
  );
}

function Wrapped({ x, y, lines, anchor = "start" }: { x: number; y: number; lines: string[]; anchor?: "start" | "middle" }) {
  return (
    <text x={x} y={y} fontSize={12} fill="var(--muted)" textAnchor={anchor}>
      {lines.map((l, i) => (
        <tspan key={l} x={x} dy={i === 0 ? 0 : 16}>
          {l}
        </tspan>
      ))}
    </text>
  );
}

function Desktop() {
  const line = { stroke: "var(--muted)", strokeWidth: 1.5, fill: "none" } as const;
  const specY = (i: number) => 4 + i * 86;
  return (
    <svg
      viewBox="0 0 960 520"
      role="img"
      aria-labelledby="diagram-title diagram-desc"
      className="hidden h-auto w-full md:block"
      fontFamily="var(--font-grotesk), ui-sans-serif, system-ui, sans-serif"
    >
      <title id="diagram-title">Flujo de una investigación multiagente</title>
      <desc id="diagram-desc">
        La evidencia del proceso llega al supervisor, que despacha a cuatro especialistas y recibe su informe. La evidencia ampliada pasa al redactor, luego al verificador y finalmente al expediente; si la verificación falla se usa una plantilla determinista.
      </desc>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--muted)" />
        </marker>
      </defs>

      {/* Row 1: evidence -> supervisor <-> specialists */}
      <Box x={0} y={134} w={150} h={64} title="Evidencia" sub="del proceso" />
      <path d="M150 166 H210" {...line} markerEnd="url(#arrow)" />
      <Box x={210} y={104} w={170} h={124} title="Supervisor" sub="sin herramientas" strong />
      <Wrapped x={224} y={176} lines={["Máx. 6 despachos;", "cada especialista,", "hasta 2 veces"]} />
      {SPEC_ORDER.map((id, i) => {
        const cy = specY(i) + 32;
        return (
          <g key={id}>
            <path d={`M380 166 C 420 166, 410 ${cy}, 470 ${cy}`} {...line} markerStart="url(#arrow)" markerEnd="url(#arrow)" />
            <Box x={470} y={specY(i)} w={490} h={64} title={SPECIALISTS[id].name} sub={`${SPEC_TOOLS[id]} · máx. 4 consultas`} />
          </g>
        );
      })}

      {/* connector down to row 2 */}
      <path d="M715 354 V386 H110 V410" {...line} markerEnd="url(#arrow)" />
      <text x={725} y={376} fontSize={12} fill="var(--muted)">
        hechos tipados, con su fuente
      </text>

      {/* Row 2: evidence -> renderer -> verifier -> dossier */}
      <Box x={0} y={410} w={220} h={78} title="Evidencia ampliada" sub="hechos + fallos visibles" />
      <path d="M220 449 H262" {...line} markerEnd="url(#arrow)" />
      <Box x={262} y={410} w={210} h={78} title="Redactor" sub="plantilla determinista" />
      <path d="M472 449 H514" {...line} markerEnd="url(#arrow)" />
      <Box x={514} y={410} w={210} h={78} title="Verificador" sub="cada cifra, contra datos" strong />
      <path d="M724 449 H766" {...line} markerEnd="url(#arrow)" />
      <Box x={766} y={410} w={194} h={78} title="Expediente" sub="borrador para revisión" />
      <Wrapped x={619} y={508} anchor="middle" lines={["Si falla: un reintento y luego plantilla determinista."]} />
    </svg>
  );
}

function Mobile() {
  return (
    <ol className="space-y-2 md:hidden" aria-label="Etapas de una investigación multiagente">
      {STAGES.map((s, i) => (
        <li key={s.name}>
          <div className={`rounded-lg border bg-surface p-3 ${s.name === "Supervisor" || s.name === "Verificador" ? "border-accent" : "border-line"}`}>
            <p className="text-sm font-semibold text-ink">{s.name}</p>
            <p className="mt-0.5 text-xs text-muted">{s.note}</p>
            {s.name.startsWith("Especialistas") ? (
              <ul className="mt-2 space-y-1 text-xs text-ink">
                {SPEC_ORDER.map((id) => (
                  <li key={id}>
                    {SPECIALISTS[id].name} <span className="font-mono text-muted">· máx. 4 consultas</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          {i < STAGES.length - 1 ? (
            <p aria-hidden="true" className="py-0.5 text-center text-muted">
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
    <div className="rounded-lg border border-line bg-bg p-4 sm:p-6">
      <Desktop />
      <Mobile />
    </div>
  );
}
