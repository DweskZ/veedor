const LOCALE = "es-EC";
const TZ = "America/Guayaquil";
export const NA = "No disponible";

const int = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const dec = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 });
const usd = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const usd0 = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const pct = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 1 });

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

export const fmtInt = (n: number | null | undefined) => (n == null ? NA : int.format(n));
export const fmtNum = (n: number | null | undefined) => (n == null ? NA : dec.format(n));
export const fmtUsd = (n: number | null | undefined, whole = false) =>
  n == null ? NA : (whole ? usd0 : usd).format(n);
/** Short process code: the OCID without its publisher prefix (e.g. "ocds-5wno2w-"). */
export const shortCode = (ocid: string) => ocid.replace(/^ocds-[a-z0-9]+-/i, "");

export const fmtPct = (n: number | null | undefined) => (n == null ? NA : pct.format(n));

export function fmtDate(value: string | null | undefined): string {
  if (!value) return NA;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return NA;
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: DATE_ONLY.test(value) ? "UTC" : TZ,
  }).format(d);
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return NA;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return NA;
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: TZ,
  }).format(d);
}

const EVIDENCE_LABELS: Record<string, string> = {
  method: "Método",
  year: "Año",
  n_tenderers: "Número de oferentes",
  tender_start: "Inicio de ofertas",
  tender_end: "Cierre de ofertas",
  window_days: "Plazo de ofertas (días)",
  p05_days: "Percentil 5 del plazo (días)",
  n_method_year: "Procesos comparables (método y año)",
  budget: "Presupuesto referencial",
  award_total: "Monto adjudicado",
  award_to_budget: "Adjudicado / presupuesto",
  p95_ratio: "Percentil 95 de la relación",
  threshold: "Umbral",
  supplier_ruc: "RUC del proveedor",
  supplier_name: "Proveedor",
  activity_start_date: "Inicio de actividades",
  first_award_date: "Primera adjudicación",
  days_between: "Días entre ambas fechas",
  sri_status: "Estado en el SRI",
  suspension_date: "Fecha de suspensión",
  restart_date: "Fecha de reinicio",
  status_is_current: "El estado es el actual",
  resolution: "Resolución",
  notification_date: "Fecha de notificación",
  qualification_detail: "Calificación publicada",
  challenge_state: "Estado de impugnación",
  listed_after_award: "Listado después de la adjudicación",
  buyer_ruc: "RUC de la entidad",
  supplier_amount: "Monto del proveedor",
  buyer_total: "Total adjudicado por la entidad",
  share: "Participación",
  n_awards_buyer_year: "Adjudicaciones de la entidad en el año",
  cpc_prefix: "Prefijo CPC",
  n_in_window: "Procesos en la ventana",
  window_start: "Inicio de la ventana",
  window_end: "Fin de la ventana",
  n_same_buyer_supplier_cpc: "Procesos misma entidad, proveedor y CPC",
  winner_ruc: "RUC del ganador",
  winner_name: "Ganador",
  cobidder_ruc: "RUC del coofertante",
  cobidder_name: "Coofertante",
  n_meetings: "Procesos en común",
  n_recurring_cobidders_in_process: "Coofertantes recurrentes en el proceso",
  process_date: "Fecha del proceso",
  timing: "Relación temporal con el proceso",
  revenue: "Ingresos anuales",
  revenue_year: "Año de los ingresos",
  ratio: "Monto / ingresos (veces)",
  factor: "Factor del umbral (veces)",
};
const MONEY_KEYS = new Set(["budget", "award_total", "supplier_amount", "buyer_total", "revenue"]);
const PERCENT_KEYS = new Set(["share"]);
const PLAIN_KEYS = new Set(["year", "revenue_year"]);

export const evidenceLabel = (key: string) => EVIDENCE_LABELS[key] ?? key;

/** Formats an evidence value according to its key, without altering it semantically. */
export function fmtEvidence(key: string, v: unknown): string {
  if (v == null) return NA;
  if (typeof v === "number") {
    if (PLAIN_KEYS.has(key)) return String(v);
    if (MONEY_KEYS.has(key)) return usd.format(v);
    if (PERCENT_KEYS.has(key)) return pct.format(v);
    return Number.isInteger(v) ? int.format(v) : dec.format(v);
  }
  if (typeof v === "boolean") return v ? "Sí" : "No";
  if (typeof v === "string") return /^\d{4}-\d{2}-\d{2}/.test(v) ? (v.length > 10 ? fmtDateTime(v) : fmtDate(v)) : v;
  return JSON.stringify(v);
}
