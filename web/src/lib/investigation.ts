import type {
  Investigation,
  InvestigationLookup,
  InvestigationModelUsage,
  InvestigationSpecialist,
} from "./types";

/** Display metadata per specialist: name, one-line objective (docs/AGENTS.md) and the order of the fixed layout. */
export const SPECIALISTS: Record<string, { name: string; objective: string }> = {
  company: {
    name: "Registro de la compañía",
    objective: "Datos de la compañía adjudicataria: constitución, capital, estado legal y estados financieros.",
  },
  tax_registry: {
    name: "Registro tributario",
    objective: "Estado actual del RUC en la consulta pública del SRI y su coincidencia con la tabla descargada.",
  },
  history: {
    name: "Historial de compras",
    objective: "Otras adjudicaciones entre la entidad y el proveedor, y compras similares cercanas en el tiempo.",
  },
  audit: {
    name: "Informes de control",
    objective: "Informes aprobados de la Contraloría cuya entidad auditada coincide con la entidad contratante.",
  },
  enquiries: {
    name: "Etapa de preguntas y respuestas",
    objective: "Cómo fue la etapa de preguntas y respuestas: cuántas preguntas hubo, cuántas tuvieron respuesta, cuánto tardó y cuántas llegaron cerca del cierre.",
  },
};

/** The five specialists in the order of docs/AGENTS.md (the fixed layout of the diagrams and lists). */
export const SPECIALIST_ORDER = ["company", "tax_registry", "history", "audit", "enquiries"] as const;

export const SOURCES: Record<string, string> = {
  get_compania_info: "Superintendencia de Compañías · registro de la compañía",
  get_financials: "Superintendencia de Compañías · estados financieros",
  pair_awards: "SERCOP · adjudicaciones entre la entidad y el proveedor",
  similar_processes: "Índice de procesos similares de Veedor",
  list_catalogo: "Contraloría General del Estado · catálogo de informes",
  get_contraloria_informe: "Contraloría General del Estado · informes aprobados",
  get_sri_ruc_info: "SRI · consulta en línea del RUC",
  process_texts: "SERCOP · preguntas y respuestas del proceso (solo recuentos y fechas)",
};

export const DISPATCH_REASONS: Record<string, string> = {
  company_size_signal: "señal de tamaño de la compañía frente al contrato",
  buyer_concentration_signal: "señal de concentración de adjudicaciones",
  baseline_check: "verificación básica",
  recurring_cobidders_signal: "señal de oferentes que coinciden",
  supplier_not_active_signal: "señal de proveedor no activo en el SRI",
  ghost_listing_signal: "señal de listado del SRI",
  repeated_awards_signal: "señal de adjudicaciones repetidas",
  single_bidder_signal: "señal de oferente único",
  tender_window_signal: "señal de plazo de ofertas",
  low_saving_signal: "señal de ahorro bajo",
  new_supplier_signal: "señal de proveedor reciente",
  retry_after_transient_failure: "reintento tras un fallo transitorio",
};

export const DECIDERS: Record<string, string> = {
  policy: "política determinista",
  model: "modelo, dentro de opciones cerradas",
};

export interface Outcome {
  label: string;
  tone: "ok" | "failed" | "skipped";
}

export function outcomeOf(outcome: string): Outcome {
  switch (outcome) {
    case "ok":
      return { label: "respondió", tone: "ok" };
    case "skipped":
      return { label: "omitida", tone: "skipped" };
    case "upstream_error":
    case "timeout":
      return { label: "la fuente no respondió", tone: "failed" };
    case "invalid_result":
      return { label: "respuesta no válida, descartada", tone: "failed" };
    default:
      return { label: outcome, tone: "failed" };
  }
}

export const OUTCOME_REASONS: Record<string, string> = {
  tool_reported_error: "la fuente informó un error",
  server_unavailable: "servicio no disponible",
  timeout: "tiempo de espera agotado",
  natural_person: "persona natural: no se consulta",
  no_identifier: "sin identificador utilizable",
  tool_not_allowed: "herramienta fuera de la lista permitida",
};

export const FACT_LABELS: Record<string, string> = {
  "investigation.company.legal_status": "Situación legal de la compañía",
  "investigation.company.incorporation": "Fecha de constitución y días hasta el proceso",
  "investigation.company.capital": "Capital suscrito y relación con el monto adjudicado",
  "investigation.company.filing": "Último ejercicio con balance presentado",
  "investigation.company.unavailable": "Datos de la compañía: no disponibles",
  "investigation.financials.latest": "Últimos estados financieros hasta el año del proceso",
  "investigation.financials.unavailable": "Estados financieros: no disponibles",
  "investigation.tax.live": "Estado en la consulta en línea del SRI",
  "investigation.tax.matches_download": "Coincidencia con la tabla descargada del SRI",
  "investigation.tax.unavailable": "Consulta del SRI: no disponible",
  "investigation.pair.others": "Otras adjudicaciones entre la entidad y el proveedor",
  "investigation.similar.window": "Compras similares de la misma entidad en ±180 días",
  "investigation.audit.count": "Informes de control encontrados",
  "investigation.audit.reports": "Detalle de informes de control",
  "investigation.audit.unavailable": "Informes de control: no se pudo establecer",
  "investigation.enquiries.unavailable": "Etapa de preguntas: sin datos",
  "investigation.enquiries.count": "Preguntas y respuestas del proceso",
  "investigation.enquiries.timing": "Días entre pregunta y respuesta",
  "investigation.enquiries.late": "Preguntas cerca del cierre de ofertas",
  "investigation.enquiries.topics": "Preguntas por tema",
};

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function outcomes(v: unknown): Record<string, number> {
  if (!isRecord(v)) return {};
  return Object.fromEntries(Object.entries(v).flatMap(([k, n]) => (typeof n === "number" ? [[k, n]] : [])));
}

/** Coerces the loosely typed stored record into a typed view. Returns null when it is not a record with an ocid. */
export function normalizeInvestigation(raw: unknown): Investigation | null {
  if (!isRecord(raw) || !str(raw.ocid)) return null;
  const specialists: InvestigationSpecialist[] = (Array.isArray(raw.specialists) ? raw.specialists : [])
    .filter(isRecord)
    .flatMap((s) => {
      const name = str(s.specialist);
      return name
        ? [
            {
              specialist: name,
              dispatch_reason: str(s.dispatch_reason),
              decided_by: str(s.decided_by),
              action_plan_by: str(s.action_plan_by),
              n_tool_calls: num(s.n_tool_calls),
              outcomes: outcomes(s.outcomes),
              facts_added: strs(s.facts_added),
            },
          ]
        : [];
    });
  const lookups: InvestigationLookup[] = (Array.isArray(raw.tool_log) ? raw.tool_log : [])
    .filter(isRecord)
    .flatMap((t) => {
      const specialist = str(t.specialist);
      const tool = str(t.tool);
      return specialist && tool
        ? [
            {
              specialist,
              tool,
              target: str(t.target),
              started_at: str(t.started_at),
              duration_ms: num(t.duration_ms),
              outcome: str(t.outcome) ?? "unknown",
              attempts: num(t.attempts),
              reason: str(t.reason),
            },
          ]
        : [];
    });
  let usage: InvestigationModelUsage | null = null;
  if (isRecord(raw.model_usage)) {
    const u = raw.model_usage;
    usage = {
      model: str(u.model),
      calls: num(u.calls) ?? 0,
      prompt_tokens: num(u.prompt_tokens),
      completion_tokens: num(u.completion_tokens),
      invalid_choices: num(u.invalid_choices),
    };
  }
  return {
    ocid: raw.ocid as string,
    started_at: str(raw.started_at),
    finished_at: str(raw.finished_at),
    specialists,
    lookups,
    facts_added: strs(raw.facts_added),
    model_usage: usage,
  };
}

/** Model-assisted when the run made model calls or any decision came from the model. */
export function isModelAssisted(inv: Investigation): boolean {
  return (
    (inv.model_usage?.calls ?? 0) > 0 ||
    inv.specialists.some((s) => s.decided_by === "model" || s.action_plan_by === "model")
  );
}

export function fmtDuration(ms: number | null): string {
  if (ms == null) return "No disponible";
  if (ms >= 1000) return `${new Intl.NumberFormat("es-EC", { maximumFractionDigits: 1 }).format(ms / 1000)} s`;
  return `${new Intl.NumberFormat("es-EC", { maximumFractionDigits: ms < 10 ? 1 : 0 }).format(ms)} ms`;
}

export function elapsedMs(inv: Investigation): number | null {
  if (!inv.started_at || !inv.finished_at) return null;
  const d = Date.parse(inv.finished_at) - Date.parse(inv.started_at);
  return Number.isFinite(d) && d >= 0 ? d : null;
}

const TARGETS: Record<string, string> = {
  winner: "el proveedor ganador",
  buyer: "la entidad contratante",
  process: "este proceso",
};

/** One lookup of the stored tool log, in plain words, for the step-through. Structured fields only. */
export interface Step {
  n: number;
  specialist: string;
  /** Why the supervisor sent this specialist; set on that specialist's first step only. */
  dispatch: string | null;
  source: string;
  about: string | null;
  outcome: Outcome;
  reason: string | null;
  duration: string;
  attempts: number | null;
}

/** The tool log in the order it happened (by start time when every entry has one, otherwise as stored). */
export function buildSteps(inv: Investigation): Step[] {
  const all = inv.lookups.map((l, i) => ({ l, i }));
  if (all.every(({ l }) => l.started_at && Number.isFinite(Date.parse(l.started_at))))
    all.sort((a, b) => Date.parse(a.l.started_at as string) - Date.parse(b.l.started_at as string) || a.i - b.i);
  const seen = new Set<string>();
  return all.map(({ l }, k) => {
    const first = !seen.has(l.specialist);
    seen.add(l.specialist);
    const sp = inv.specialists.find((s) => s.specialist === l.specialist);
    const reason = sp?.dispatch_reason ? (DISPATCH_REASONS[sp.dispatch_reason] ?? sp.dispatch_reason) : null;
    return {
      n: k + 1,
      specialist: SPECIALISTS[l.specialist]?.name ?? l.specialist,
      dispatch: first ? reason : null,
      source: SOURCES[l.tool] ?? l.tool,
      about: l.target ? (TARGETS[l.target] ?? null) : null,
      outcome: outcomeOf(l.outcome),
      reason: l.reason ? (OUTCOME_REASONS[l.reason] ?? l.reason) : null,
      duration: fmtDuration(l.duration_ms),
      attempts: l.attempts,
    };
  });
}
