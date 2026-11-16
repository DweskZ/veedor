/**
 * SAMPLE DATA. Fictional entities, fictional figures. Used only when NEXT_PUBLIC_USE_MOCKS=1.
 * Nothing here describes a real process, buyer or supplier.
 */
import type { Provenance, Quotes } from "./provenance";
import type {
  BuyerDetail,
  Dossier,
  Investigation,
  Paginated,
  PartyKind,
  ProcessDetail,
  ProcessQuery,
  ProcessSummary,
  ProcessContext,
  RegionStats,
  Review,
  SignalDef,
  SimilarProcesses,
  Stats,
  SupplierDetail,
  YearStats,
} from "./types";

const BUYERS = [
  { ruc: "0000000000001", name: "Entidad de ejemplo A", region: "Región de ejemplo 1" },
  { ruc: "0000000000002", name: "Entidad de ejemplo B", region: "Región de ejemplo 2" },
  { ruc: "0000000000003", name: "Entidad de ejemplo C", region: "Región de ejemplo 1" },
];
const SUPPLIERS: { ruc: string; name: string; kind: PartyKind }[] = [
  { ruc: "0000000000101", name: "Proveedor de ejemplo S.A.", kind: "company" },
  { ruc: "0000000000102", name: "Proveedor de ejemplo Cía. Ltda.", kind: "company" },
  { ruc: "0000*********", name: "Persona natural", kind: "natural_person" },
  { ruc: "0000000000104", name: "Suministros de ejemplo S.A.", kind: "company" },
];
const METHODS = ["Subasta Inversa Electrónica", "Menor Cuantía", "Cotización", "Licitación"];

const SIGNAL_ROWS: [string, string, string, string, string][] = [
  ["SINGLE_BIDDER", "Oferente único", "El proceso competitivo recibió una sola oferta.", "Exactamente un oferente registrado.", "Procesos competitivos"],
  ["SHORT_TENDER_WINDOW", "Plazo de ofertas atípicamente corto", "El plazo entre inicio y cierre de ofertas es menor al habitual para su método y año.", "Duración por debajo del percentil 5 de su método y año.", "Procesos con ambas fechas"],
  ["LOW_SAVING", "Ahorro atípicamente bajo", "El monto adjudicado es casi igual al presupuesto referencial.", "Adjudicado/presupuesto en el percentil 95 de su método y año y al menos 0,99.", "Competitivos con presupuesto"],
  ["NEW_SUPPLIER", "Proveedor de reciente creación", "El ganador inició actividades poco antes de su primera adjudicación.", "Menos de 180 días entre inicio de actividades y primera adjudicación.", "Adjudicaciones con registro asociado"],
  ["SUPPLIER_NOT_ACTIVE", "Proveedor no activo en el SRI", "El estado actual del ganador en el SRI no es activo. Es el estado actual, no el vigente al momento de la adjudicación.", "Estado actual distinto de activo.", "Registro asociado"],
  ["BUYER_CONCENTRATION", "Concentración de adjudicaciones", "Un proveedor concentra una parte alta de lo adjudicado por la entidad en el año.", "Al menos 30 % del monto, total de la entidad-año de al menos USD 100 000 y 3 o más adjudicaciones.", "Procesos no de catálogo"],
  ["REPEATED_DIRECT_AWARDS", "Adjudicaciones directas repetidas", "Misma entidad, mismo proveedor y mismo CPC repetidos en poco tiempo.", "3 o más procesos directos en 90 días.", "Contratación directa"],
  ["RECURRING_COBIDDERS", "Coincidencia recurrente de oferentes", "El ganador y un mismo oferente perdedor coinciden repetidamente en la misma entidad.", "5 o más procesos competitivos en común.", "Procesos competitivos"],
];
export const signals: SignalDef[] = [
  ...SIGNAL_ROWS.map(([code, label_es, description_es, threshold_rule_es, scope]): SignalDef => ({
    code, kind: "risk", label_es, description_es, threshold_rule_es, scope, fields: [], statistical: false, needs_registry: false,
  })),
  {
    code: "SUPPLIER_LISTED_AFTER_PROCESS", kind: "context", label_es: "Proveedor incluido en un listado registral después del proceso",
    description_es: "El proveedor fue incluido en un listado del registro con fecha posterior al proceso. Es contexto: no afecta el puntaje.",
    threshold_rule_es: "Fecha de inclusión posterior a la fecha del proceso.", scope: "Registro asociado", fields: [], statistical: false, needs_registry: true,
  },
];

// [score, buyerIdx, supplierIdx, methodIdx, year, amount, signals]
const SEEDS: [number, number, number, number, number, number, string[]][] = [
  [82, 0, 0, 1, 2024, 48210.5, ["SINGLE_BIDDER", "NEW_SUPPLIER", "BUYER_CONCENTRATION"]],
  [71, 1, 1, 0, 2025, 129800, ["SINGLE_BIDDER", "LOW_SAVING"]],
  [64, 0, 3, 2, 2023, 76450.25, ["SHORT_TENDER_WINDOW", "SINGLE_BIDDER"]],
  [58, 2, 2, 1, 2024, 19990, ["REPEATED_DIRECT_AWARDS", "SUPPLIER_LISTED_AFTER_PROCESS"]],
  [47, 1, 0, 3, 2022, 842000, ["BUYER_CONCENTRATION", "LOW_SAVING"]],
  [41, 2, 1, 2, 2025, 33120, ["SHORT_TENDER_WINDOW"]],
  [33, 0, 3, 0, 2024, 15400, ["SUPPLIER_NOT_ACTIVE"]],
  [28, 1, 2, 1, 2023, 8800, ["SINGLE_BIDDER"]],
  [22, 2, 0, 0, 2021, 4650.9, ["LOW_SAVING"]],
  [18, 0, 1, 2, 2025, 61200, ["RECURRING_COBIDDERS"]],
  [12, 1, 3, 3, 2022, 245000, ["NEW_SUPPLIER"]],
  [0, 2, 0, 0, 2024, 12300, []],
];

const processes: ProcessSummary[] = SEEDS.map(([score, b, s, m, year, amount, codes], i) => ({
  ocid: `sample-ocid-${String(i + 1).padStart(4, "0")}`,
  risk_score: score,
  n_signals: codes.length,
  signal_codes: codes,
  anomaly_score: Math.round((0.1 + ((i * 37) % 80) / 100) * 100) / 100,
  award_total: amount,
  year,
  buyer_ruc: BUYERS[b].ruc,
  buyer_name: BUYERS[b].name,
  method: METHODS[m],
  winner_ruc: SUPPLIERS[s].ruc,
  winner_name: SUPPLIERS[s].name,
  winner_kind: SUPPLIERS[s].kind,
}));

const code = (p: ProcessSummary) => `EJEMPLO-${p.year}-${p.ocid.slice(-4)}`;

export const stats: Stats = {
  processes_total: 1200,
  processes_by_method_group: { competitive: 700, direct: 300, catalogue: 200 },
  processes_scored: 1200,
  processes_with_signals: 480,
  mean_risk_score: 4.2,
  score_distribution: [
    { lower: 0, upper: 10, count: 900 },
    { lower: 10, upper: 20, count: 120 },
    { lower: 20, upper: 30, count: 100 },
    { lower: 30, upper: 40, count: 50 },
    { lower: 50, upper: 60, count: 20 },
    { lower: 80, upper: 90, count: 10 },
  ],
  signal_counts: signals
    .map((s, i) => ({ code: s.code, label_es: s.label_es, count: 142 - i * 17 }))
    .filter((c) => c.count > 0),
  first_year: 2021,
  last_year: 2025,
  last_data_date: "2025-11-28",
  available_tables: { processes: true },
};

export function listProcesses(q: ProcessQuery): Paginated<ProcessSummary> {
  const text = (q.q ?? "").toLowerCase();
  let rows = processes.filter(
    (p) =>
      (!q.year || String(p.year) === q.year) &&
      (!q.method || p.method === q.method) &&
      (!q.signal || p.signal_codes.includes(q.signal)) &&
      (!q.min_score || p.risk_score >= Number(q.min_score)) &&
      (!q.buyer_ruc || p.buyer_ruc === q.buyer_ruc) &&
      (!text || [code(p), p.buyer_name, p.winner_name, p.ocid].join(" ").toLowerCase().includes(text)),
  );
  const sort = q.sort || "-risk_score";
  const key = sort.replace(/^-/, "") as "risk_score" | "award_total";
  const dir = sort.startsWith("-") ? -1 : 1;
  rows = [...rows].sort((a, b) => ((a[key] ?? -1) - (b[key] ?? -1)) * dir);
  const size = Number(q.page_size) || 25;
  const page = Math.max(1, Number(q.page) || 1);
  return { items: rows.slice((page - 1) * size, page * size), page, page_size: size, total: rows.length };
}

function find(ocid: string): ProcessSummary {
  const p = processes.find((r) => r.ocid === ocid);
  if (!p) throw new Error("not found");
  return p;
}

const supplierProfile = (ruc: string) => {
  const s = SUPPLIERS.find((x) => x.ruc === ruc);
  if (!s) throw new Error("not found");
  const mine = processes.filter((p) => p.winner_ruc === ruc);
  return {
    s,
    mine,
    profile: {
      ruc: s.ruc,
      name: s.name,
      kind: s.kind,
      n_processes: mine.length + 3,
      n_wins: mine.length,
      total_awarded: mine.reduce((a, p) => a + (p.award_total ?? 0), 0),
      first_award_date: "2022-02-10",
      last_award_date: "2025-09-30",
      n_buyers: new Set(mine.map((p) => p.buyer_ruc)).size,
      top_buyer_ruc: mine[0]?.buyer_ruc ?? null,
      top_buyer_share: 0.52,
      single_bidder_wins: mine.filter((p) => p.signal_codes.includes("SINGLE_BIDDER")).length,
      mean_risk_score: mine.length ? mine.reduce((a, p) => a + p.risk_score, 0) / mine.length : null,
    },
  };
};

export function processDetail(ocid: string): ProcessDetail {
  const p = find(ocid);
  const budget = Math.round((p.award_total ?? 0) * 1.012 * 100) / 100;
  const single = p.signal_codes.includes("SINGLE_BIDDER");
  return {
    ocid,
    facts: {
      process_code: code(p),
      release_date: `${p.year}-06-14T09:30:00-05:00`,
      year: p.year,
      buyer_ruc: p.buyer_ruc,
      buyer_name: p.buyer_name,
      buyer_region: BUYERS.find((b) => b.ruc === p.buyer_ruc)?.region ?? null,
      buyer_locality: null,
      method: p.method,
      method_group: "competitive",
      category: "goods",
      status: "complete",
      description: p.winner_kind === "natural_person" ? null : "Adquisición de bienes de ejemplo para fines de demostración.",
      description_withheld: p.winner_kind === "natural_person",
      budget,
      tender_start: `${p.year}-06-14T09:30:00-05:00`,
      tender_end: `${p.year}-06-19T17:00:00-05:00`,
      n_tenderers: single ? 1 : 4,
      n_bids: single ? 1 : 4,
      n_awards: 1,
      award_total: p.award_total,
      first_award_date: null,
      date_signed: `${p.year}-07-02`,
      main_cpc: "0000000",
      main_cpc_description: "Categoría de ejemplo",
    },
    score: { risk_score: p.risk_score, n_signals: p.n_signals, anomaly_score: p.anomaly_score },
    signals: p.signal_codes.map((c, i) => ({
      code: c,
      kind: signals.find((x) => x.code === c)?.kind ?? "risk",
      label_es: signals.find((s) => s.code === c)?.label_es ?? c,
      value: c === "SINGLE_BIDDER" ? 1 : c === "LOW_SAVING" ? 0.988 + i / 1000 : 4 + i,
      threshold: c === "SINGLE_BIDDER" ? 1 : c === "LOW_SAVING" ? 0.99 : 6,
      evidence: { n_tenderers: single ? 1 : 4, method: p.method, budget, award_total: p.award_total },
    })),
    winner: p.winner_ruc ? supplierProfile(p.winner_ruc).profile : null,
    tenderers: p.winner_ruc ? [{ ruc: p.winner_ruc, name: p.winner_name, kind: p.winner_kind ?? "unknown" }] : [],
    awards: [{ award_id: "ejemplo-1", award_date: null, supplier_ruc: p.winner_ruc, supplier_name: p.winner_name, amount: p.award_total }],
    notice_es: "Los indicadores son señales de riesgo calculadas a partir de datos públicos. No constituyen una acusación.",
  };
}

export function dossier(ocid: string): Dossier {
  const p = find(ocid);
  return {
    ocid,
    generated_at: "2025-11-28T10:00:00-05:00",
    mode: "template",
    summary_es: `Expediente de ejemplo para el proceso ${code(p)}. Presenta ${p.n_signals} indicador(es) con valores ficticios. No describe un proceso real.`,
    sections: [
      { title: "Hechos del proceso", body: `Proceso de ejemplo ${code(p)}, convocado por ${p.buyer_name} mediante ${p.method}.` },
      { title: "Indicadores", body: "Los indicadores de esta vista son datos de ejemplo y no tienen relación con ningún proceso real." },
    ],
    sources: [{ dataset: "Datos de ejemplo (SAMPLE)", licence: "Sin licencia: datos ficticios", retrieved_at: "2025-11-28", record_id: ocid }],
    grounding_report: { passed: true, n_checked: 12, supported: [], unsupported: [], forbidden: [] },
  };
}

export function supplier(ruc: string): SupplierDetail {
  const { s, mine, profile } = supplierProfile(ruc);
  return {
    profile,
    registry: {
      sri:
        s.kind === "company"
          ? { ruc: s.ruc, legal_name: s.name, status: "ACTIVO", taxpayer_type: "Sociedad", activity_start_date: "2022-03-15", suspension_date: null, restart_date: null, ciiu_code: null, activity: null, province: "Provincia de ejemplo" }
          : null,
      ghost_company_listed: s.kind === "company" ? false : null,
      supercias: null,
      financials: [],
    },
    recent_processes: mine,
  };
}

export function buyer(ruc: string): BuyerDetail {
  const b = BUYERS.find((x) => x.ruc === ruc);
  if (!b) throw new Error("not found");
  const mine = processes.filter((p) => p.buyer_ruc === ruc);
  const total = mine.reduce((a, p) => a + (p.award_total ?? 0), 0);
  const mix = new Map<string, number>();
  for (const p of mine) for (const c of p.signal_codes) mix.set(c, (mix.get(c) ?? 0) + 1);
  return {
    ruc: b.ruc,
    name: b.name,
    n_processes: mine.length,
    n_flagged: mine.filter((p) => p.n_signals > 0).length,
    total_awarded: total,
    mean_risk_score: mine.length ? mine.reduce((a, p) => a + p.risk_score, 0) / mine.length : null,
    first_year: Math.min(...mine.map((p) => p.year ?? 9999)),
    last_year: Math.max(...mine.map((p) => p.year ?? 0)),
    top_suppliers: SUPPLIERS.map((s) => {
      const w = mine.filter((p) => p.winner_ruc === s.ruc);
      const amount = w.reduce((a, p) => a + (p.award_total ?? 0), 0);
      return { ruc: s.ruc, name: s.name, kind: s.kind, n_awards: w.length, total_awarded: amount, share_of_awarded: total ? amount / total : null, mean_risk_score: null };
    })
      .filter((s) => s.n_awards > 0)
      .sort((a, b2) => (b2.total_awarded ?? 0) - (a.total_awarded ?? 0)),
    signal_mix: [...mix].map(([c, count]) => ({ code: c, label_es: signals.find((s) => s.code === c)?.label_es ?? null, count })),
  };
}

/** Fictional provenance for the mock server. The names, publisher and URL do not exist. */
export function provenance(ocid: string): Provenance | null {
  if (!ocid.startsWith("sample-ocid")) return null;
  const p = find(ocid);
  const fact = (key: string, label_es: string, value: string, source_field: string | null, derived = false, derivation_es: string | null = null) => ({
    key, label_es, value, source_id: "ejemplo-ocds", source_field, derived, derivation_es,
    verify_es: "Busca el identificador del proceso en el portal de datos de ejemplo y compara el campo indicado.",
  });
  return {
    ocid,
    sources: [{ id: "ejemplo-ocds", name: "Datos abiertos de ejemplo (ficticio)", publisher: "Institución de ejemplo", licence: "Licencia de ejemplo", retrieved_at: "2026-01-15", url: "https://ejemplo.invalid/datos" }],
    facts: [
      fact("facts.buyer_name", "Entidad contratante", p.buyer_name ?? "", "buyer.name"),
      fact("facts.method", "Método", p.method ?? "", "tender.procurementMethodDetails"),
      fact("facts.budget", "Presupuesto referencial", String(Math.round((p.award_total ?? 0) * 1.012 * 100) / 100), "tender.value.amount"),
      fact("facts.award_total", "Monto adjudicado", String(p.award_total ?? ""), "awards[].value.amount", true, "Suma de los montos de todas las adjudicaciones del proceso."),
      fact("facts.n_tenderers", "Número de oferentes", p.signal_codes.includes("SINGLE_BIDDER") ? "1" : "4", "tender.numberOfTenderers"),
    ],
  };
}

export function quotes(ocid: string): Quotes | null {
  if (!ocid.startsWith("sample-ocid")) return null;
  const base = { truncated: false, similarity: 0.71, related_signal: null, related_signal_label_es: null, pair: null };
  if (ocid === "sample-ocid-0001")
    return {
      ocid,
      items: [
        { ...base, kind: "enquiry_question", text: "Texto ficticio de una pregunta: ¿el plazo para entregar las ofertas puede ampliarse unos días?", date: "2019-03-12", author_kind: "oferente", source_field: "tender.enquiries[].description", related_signal: "SHORT_TENDER_WINDOW", related_signal_label_es: "Plazo de ofertas corto", pair: { kind: "enquiry_answer", text: "Texto ficticio de una respuesta: el plazo se mantiene según el cronograma publicado.", source_field: "tender.enquiries[].answer" } },
      ],
      available_total: 4,
      omitted: { personal_data: 1, unsafe: 0, below_relevance: 2 },
      note_es: "Texto de ejemplo, no real.",
    };
  if (ocid === "sample-ocid-0002")
    return {
      ocid,
      items: [{ ...base, kind: "award_text", text: "Texto ficticio de adjudicación: se adjudica el contrato al único oferente calificado.", date: "2024-07-01", author_kind: "entidad", source_field: "awards[].description", related_signal: "SINGLE_BIDDER", related_signal_label_es: "Un solo oferente" }],
      available_total: 1,
      omitted: { personal_data: 0, unsafe: 0, below_relevance: 0 },
      note_es: null,
    };
  return { ocid, items: [], available_total: 0, omitted: { personal_data: 0, unsafe: 0, below_relevance: 0 }, note_es: null };
}

export const meta = { reviews_enabled: false, ask_enabled: true };
export const reviews = (): Review[] => [];

/** Sample investigation (fictional): only the first two sample processes have one. */
export function investigation(ocid: string): Investigation | null {
  if (!["sample-ocid-0001", "sample-ocid-0002"].includes(ocid)) return null;
  const t0 = "2025-11-28T10:00:00Z";
  const look = (specialist: string, tool: string, target: string, duration_ms: number, outcome = "ok", reason: string | null = null) => ({
    specialist, tool, target, started_at: t0, duration_ms, outcome, attempts: 1, reason,
  });
  const failed = ocid.endsWith("0002");
  return {
    ocid,
    started_at: t0,
    finished_at: "2025-11-28T10:00:07Z",
    specialists: [
      { specialist: "company", dispatch_reason: "company_size_signal", decided_by: "policy", action_plan_by: "policy", n_tool_calls: 2, outcomes: { ok: 2 },
        facts_added: ["investigation.company.legal_status", "investigation.company.incorporation", "investigation.company.capital", "investigation.financials.latest"] },
      { specialist: "history", dispatch_reason: "buyer_concentration_signal", decided_by: "policy", action_plan_by: "policy", n_tool_calls: 2, outcomes: { ok: 2 },
        facts_added: ["investigation.pair.others", "investigation.similar.window"] },
      { specialist: "audit", dispatch_reason: "baseline_check", decided_by: "policy", action_plan_by: "policy", n_tool_calls: 2, outcomes: failed ? { ok: 1, upstream_error: 1 } : { ok: 2 },
        facts_added: [failed ? "investigation.audit.unavailable" : "investigation.audit.count"] },
    ],
    lookups: [
      look("company", "get_compania_info", "winner", 1.4),
      look("company", "get_financials", "winner", 2.1),
      look("history", "pair_awards", "buyer", 85),
      look("history", "similar_processes", "process", 41),
      look("audit", "list_catalogo", "buyer", 310),
      failed ? look("audit", "get_contraloria_informe", "buyer", 4200, "upstream_error", "server_unavailable") : look("audit", "get_contraloria_informe", "buyer", 920),
    ],
    facts_added: [],
    model_usage: { model: null, calls: 0, prompt_tokens: 0, completion_tokens: 0, invalid_choices: 0 },
  };
}

export function similar(ocid: string, sameBuyer: boolean, k: number): SimilarProcesses {
  const base = find(ocid);
  const items = processes
    .filter((p) => p.ocid !== ocid && (!sameBuyer || p.buyer_ruc === base.buyer_ruc))
    .slice(0, k)
    .map((p, i) => ({
      ocid: p.ocid,
      similarity: Math.max(0.5, 0.93 - i * 0.04),
      year: p.year,
      buyer_ruc: p.buyer_ruc,
      buyer_name: p.buyer_name,
      method: p.method,
      award_total: p.award_total,
      main_cpc: "0000000",
    }));
  return {
    ocid, k, same_buyer: sameBuyer, items,
    notice_es: "Datos de ejemplo: la similitud es ficticia.",
  };
}

/** SAMPLE aggregates for the map and the trends page: fictional figures. */
const SAMPLE_REGIONS: [string, string, number, number, number][] = [
  ["AZUAY", "Azuay", 1900, 24, 18], ["BOLIVAR", "Bolívar", 310, 33, 31], ["CARCHI", "Carchi", 400, 29, 22],
  ["CAÑAR", "Cañar", 520, 31, 26], ["CHIMBORAZO", "Chimborazo", 1000, 28, 20], ["COTOPAXI", "Cotopaxi", 770, 26, 19],
  ["EL ORO", "El Oro", 940, 27, 21], ["ESMERALDAS", "Esmeraldas", 600, 38, 34], ["GALAPAGOS", "Galápagos", 190, 35, 30],
  ["GUAYAS", "Guayas", 4000, 25, 17], ["IMBABURA", "Imbabura", 840, 27, 20], ["LOJA", "Loja", 990, 30, 25],
  ["LOS RIOS", "Los Ríos", 760, 32, 27], ["MANABI", "Manabí", 1700, 31, 24], ["MORONA SANTIAGO", "Morona Santiago", 590, 36, 33],
  ["NAPO", "Napo", 430, 34, 30], ["ORELLANA", "Orellana", 610, 37, 32], ["PASTAZA", "Pastaza", 390, 35, 31],
  ["PICHINCHA", "Pichincha", 6200, 23, 15], ["SANTA ELENA", "Santa Elena", 370, 30, 25],
  ["SANTO DOMINGO DE LOS TSACHILAS", "Santo Domingo de los Tsáchilas", 340, 29, 23], ["SUCUMBIOS", "Sucumbíos", 660, 39, 35],
  ["TUNGURAHUA", "Tungurahua", 1000, 26, 19], ["ZAMORA CHINCHIPE", "Zamora Chinchipe", 440, 33, 29],
];
const regionRow = (region: string, region_label: string, n: number, a: number, b: number) => ({
  region, region_label, competitive_processes: n, with_signal: Math.round((n * a) / 100), pct_with_signal: a / 100,
  single_bidder: Math.round((n * b) / 100), pct_single_bidder: b / 100, mean_score: 8 + a / 5, processes_total: n * 6, awarded_total: n * 90000,
  small_sample: n < 500,
});
export const regions: RegionStats = {
  items: SAMPLE_REGIONS.map((r) => regionRow(...r)),
  national: regionRow("NACIONAL", "Nacional", 26700, 27, 20),
  basis: "competitive",
  notes: ["Datos de ejemplo: la provincia es la de la entidad contratante."],
  data_built_at: "2025-11-28T00:00:00Z",
};

export const years: YearStats = {
  items: Array.from({ length: 12 }, (_, i) => {
    const year = 2015 + i;
    const competitive = 55 - i * 2;
    const direct = 25 + i * 1.5;
    return {
      year,
      processes_total: 9000 + i * 400,
      competitive_processes: 2000 + i * 100,
      pct_single_bidder: 18 + Math.sin(i) * 3,
      pct_with_signal: 25 + i * 0.4,
      single_bidder_base: 900 + i * 40,
      awarded_total: 1e9,
      mix: { competitive, direct, catalogue: 100 - competitive - direct - 2, other: 2 },
      partial_year: year === 2026,
    };
  }),
  notes: ["Datos de ejemplo: el año 2022 simula tener menos procesos publicados.", "Los nombres de los procedimientos cambiaron alrededor de 2025."],
  data_built_at: "2025-11-28T00:00:00Z",
};

export function context(ocid: string): ProcessContext | null {
  if (!ocid.startsWith("sample-ocid")) return null;
  return {
    method: "Subasta Inversa Electrónica", year: 2024, comparable: 1234,
    tenderers: { counts: [260, 410, 280, 150, 80, 54], position: { value: 1, percentile: 0.21 } },
    ratio: { median: 0.93, q1: 0.88, q3: 0.97, position: { value: 0.995, percentile: 0.96 } },
    window: { median: 9, q1: 7, q3: 12, position: { value: 6, percentile: 0.12 } },
  };
}

/**
 * Fictional answers for the question box (mock mode only). Triggers: "culpable", "corrup" or "juicio" give a question the
 * data does not answer; "límite" gives a rate-limit; "falla" gives a server error. Anything else is answered.
 */
export function ask(ocid: string, question: string): unknown {
  const q = question.toLowerCase();
  if (/límite|limite/.test(q)) return { __status: 429, retryAfter: 45 };
  if (/falla/.test(q)) return { __status: 503 };
  if (/culpable|corrup|juicio/.test(q))
    return {
      ocid,
      answerable: false,
      mode: "retrieval",
      reason: "judgement",
      sentences: [],
      quotes: [],
      note_es: "Texto de ejemplo: Veedor describe registros y no emite juicios sobre las personas ni sobre las entidades.",
    };
  return {
    ocid,
    answerable: true,
    mode: q.includes("modelo") ? "model" : "retrieval",
    reason: "answered",
    sentences: [
      { text: "Texto ficticio: este proceso registra 4 oferentes.", fact_id: "process.tenderers", source_id: "ejemplo-ocds", source_field: "tender.numberOfTenderers" },
      { text: "Texto ficticio: se adjudicó un monto de ejemplo frente a un presupuesto referencial de ejemplo.", fact_id: "process.amounts", source_id: "ejemplo-ocds", source_field: "awards[].value.amount" },
      { text: "Texto ficticio sin marcador de procedencia en la página.", fact_id: "context.count", source_id: "veedor_indicators", source_field: "processes (mismo método y año)" },
    ],
    quotes: [
      {
        quote_id: "q1",
        text: "Texto ficticio de una cita: ¿el plazo para entregar las ofertas puede ampliarse unos días? " + "Esta frase se repite para comprobar cómo se ve una cita larga. ".repeat(6),
        kind: "enquiry_question",
        date: "2019-03-12",
        source_field: "tender.enquiries[0].description",
        truncated: false,
      },
      { quote_id: "q2", text: "Texto ficticio de una respuesta: el plazo se mantiene.", kind: "enquiry_answer", date: "2019-03-14", source_field: "tender.enquiries[0].answer", truncated: false },
    ],
    note_es: "Respuesta de ejemplo, no real.",
  };
}
