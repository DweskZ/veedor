/**
 * SAMPLE DATA. Fictional entities, fictional figures. Used only when NEXT_PUBLIC_USE_MOCKS=1.
 * Nothing here describes a real process, buyer or supplier.
 */
import type {
  BuyerDetail,
  Dossier,
  Paginated,
  PartyKind,
  ProcessDetail,
  ProcessQuery,
  ProcessSummary,
  Review,
  SignalDef,
  Stats,
  SupplierDetail,
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

export const meta = { reviews_enabled: false };
export const reviews = (): Review[] => [];
