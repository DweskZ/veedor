/**
 * "Pregunta sobre este proceso": types, validation and normalisation for `POST /processes/{ocid}/ask`.
 * Pure (no React, no fetch) so it can be tested. Everything the API sends is shown as text, never as HTML.
 */
import { maskNaturalRuc } from "./provenance.ts";

export const QUESTION_MIN = 3;
export const QUESTION_MAX = 300;
/** The character counter appears from here on. */
export const COUNTER_FROM = 240;

export interface AskSentence {
  text: string;
  fact_id: string;
  source_id: string;
  source_field: string;
}

export interface AskQuote {
  quote_id: string;
  text: string;
  kind: "enquiry_question" | "enquiry_answer" | "award_text";
  date: string | null;
  source_field: string | null;
  truncated: boolean;
}

export interface AskAnswer {
  ocid: string;
  answerable: boolean;
  mode: "model" | "retrieval";
  reason: string;
  sentences: AskSentence[];
  quotes: AskQuote[];
  note_es: string | null;
}

/** Why a question could not be answered with a result. */
export type AskFailure =
  | { kind: "limit"; retryAfterSeconds: number | null }
  | { kind: "invalid"; message: string }
  | { kind: "disabled" }
  | { kind: "error"; message: string };

export class AskError extends Error {
  readonly failure: AskFailure;
  constructor(failure: AskFailure) {
    super(failure.kind);
    this.name = "AskError";
    this.failure = failure;
  }
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);
const KINDS = new Set(["enquiry_question", "enquiry_answer", "award_text"]);

/** Length in characters as a person counts them (an accented letter or an emoji is one). */
export const questionLength = (q: string): number => Array.from(q.trim()).length;

/** A message for the visitor when the question cannot be sent, or null when it can. */
export function checkQuestion(q: string): string | null {
  const n = questionLength(q);
  if (n < QUESTION_MIN) return `Escribe al menos ${QUESTION_MIN} caracteres.`;
  if (n > QUESTION_MAX) return `La pregunta puede tener hasta ${QUESTION_MAX} caracteres.`;
  if (/[\u0000-\u001f\u007f]/.test(q.trim())) return "Escribe la pregunta en una sola línea, sin saltos de línea.";
  return null;
}

/** Keeps well-formed sentences and quotes only; masks a natural-person RUC as a last guard. Null when the body is not an answer. */
export function normalizeAsk(raw: unknown): AskAnswer | null {
  if (!isObj(raw) || typeof raw.ocid !== "string" || typeof raw.answerable !== "boolean") return null;
  const sentences = (Array.isArray(raw.sentences) ? raw.sentences : []).flatMap((s): AskSentence[] =>
    isObj(s) && str(s.text)
      ? [{ text: maskNaturalRuc(s.text as string), fact_id: String(s.fact_id ?? ""), source_id: String(s.source_id ?? ""), source_field: String(s.source_field ?? "") }]
      : [],
  );
  const quotes = (Array.isArray(raw.quotes) ? raw.quotes : []).flatMap((q): AskQuote[] =>
    isObj(q) && str(q.text) && KINDS.has(String(q.kind))
      ? [
          {
            quote_id: String(q.quote_id ?? ""),
            text: maskNaturalRuc(q.text as string),
            kind: q.kind as AskQuote["kind"],
            date: str(q.date),
            source_field: str(q.source_field),
            truncated: q.truncated === true,
          },
        ]
      : [],
  );
  return {
    ocid: raw.ocid,
    answerable: raw.answerable,
    mode: raw.mode === "model" ? "model" : "retrieval",
    reason: typeof raw.reason === "string" ? raw.reason : "",
    sentences,
    quotes,
    note_es: str(raw.note_es),
  };
}

/** Seconds from a `Retry-After` header (number of seconds or an HTTP date), or null. */
export function parseRetryAfter(value: string | null, now = Date.now()): number | null {
  if (!value) return null;
  const n = Number(value);
  if (Number.isFinite(n)) return n >= 0 ? Math.ceil(n) : null;
  const t = Date.parse(value);
  return Number.isFinite(t) ? Math.max(0, Math.ceil((t - now) / 1000)) : null;
}

/** "unos segundos", "1 minuto", "3 minutos"... for the rate-limit message. */
export function waitPhrase(seconds: number): string {
  if (seconds <= 45) return "unos segundos";
  const m = Math.round(seconds / 60);
  if (m < 60) return m <= 1 ? "1 minuto" : `${m} minutos`;
  const h = Math.round(m / 60);
  return h <= 1 ? "1 hora" : `${h} horas`;
}

/**
 * Provenance keys (`/provenance`) behind each fact id of an answer, so the marker can open the same panel the rest of the
 * page uses. Mirrors the catalogue on the API side; a fact id not listed here is shown with its source name and field inline.
 */
const FACT_KEYS: Record<string, string[]> = {
  "process.object": ["facts.main_cpc_description"],
  "process.entity": ["facts.buyer_name", "facts.buyer_ruc", "facts.buyer_region", "facts.buyer_locality"],
  "process.procedure": ["facts.method", "facts.category", "facts.status"],
  "process.amounts": ["facts.award_total", "facts.budget"],
  "process.tenderers": ["facts.n_tenderers", "facts.tender_start", "facts.tender_end"],
  "process.award_dates": ["facts.first_award_date", "facts.date_signed"],
  "process.cpc": ["facts.main_cpc", "facts.main_cpc_description"],
  "signals.none": ["score.n_signals"],
  "signals.unavailable": ["score.n_signals"],
  "winner.identity": ["winner.name", "winner.ruc", "winner.kind"],
  "winner.sri": ["registry.sri_status", "registry.sri_taxpayer_type", "registry.sri_activity_start"],
  "winner.ghost": ["registry.sri_ghost_listed"],
  "winner.company": ["registry.supercias_company_type"],
  "winner.revenue": ["registry.supercias_revenue_latest", "registry.supercias_revenue_year"],
};

export function provenanceKeysFor(factId: string): string[] {
  if (factId.startsWith("signal:")) return [`signal.${factId.slice("signal:".length)}`];
  return FACT_KEYS[factId] ?? [factId];
}

export interface SuggestionInput {
  nRiskSignals: number;
  hasTenderers: boolean;
  hasAmounts: boolean;
  hasBuyer: boolean;
  hasWinner: boolean;
  hasObject: boolean;
}

/** Three to five questions this process can actually answer, from what it has. */
export function suggestQuestions(i: SuggestionInput): string[] {
  const out: string[] = [];
  if (i.nRiskSignals > 0) out.push(i.nRiskSignals === 1 ? "¿Por qué tiene esta señal?" : "¿Por qué tiene estas señales?");
  if (i.hasTenderers) out.push("¿Cuántos oferentes hubo?");
  if (i.hasAmounts) out.push("¿Cuánto se adjudicó y cuál era el presupuesto?");
  if (i.hasBuyer) out.push("¿Quién compró?");
  if (i.hasWinner) out.push("¿Quién ganó?");
  if (i.hasObject) out.push("¿Qué se contrató?");
  return out.slice(0, 5);
}

/** Examples of what can be asked, for an answer the stored evidence does not give. */
export function examplesFor(suggestions: string[], count = 2): string[] {
  const base = ["¿Cuántos oferentes hubo?", "¿Quién compró?", "¿Cuánto se adjudicó y cuál era el presupuesto?", "¿Quién ganó?"];
  return [...new Set([...suggestions, ...base])].slice(0, count);
}

/** How the API says it answers. Anything else (absent, unknown) is treated as the cautious case. */
export type AskMode = "retrieval" | "model" | null;

/**
 * The notice shown before a question is sent. The external-provider text is the default: the plain "search inside Veedor"
 * text appears only when the API says so (`ask_mode: "retrieval"`), so the page never claims more privacy than the API gives.
 */
export function askNotice(mode: AskMode): { external: boolean; text: string } {
  if (mode === "retrieval")
    return { external: false, text: "La respuesta se encuentra con una búsqueda dentro de Veedor, sin modelo de lenguaje. La pregunta no se guarda. Aun así, no escribas datos personales." };
  return {
    external: true,
    text: "Tu pregunta puede enviarse a un proveedor externo de modelos de lenguaje, que elige qué datos guardados mostrar. No escribas datos personales. La pregunta no se guarda.",
  };
}

/** Seconds the button stays off after a 429: what the API says, or a short default when it sent no `Retry-After`. */
export const DEFAULT_WAIT_SECONDS = 30;
export function blockSeconds(retryAfter: number | null): number {
  return Math.max(1, retryAfter ?? DEFAULT_WAIT_SECONDS);
}
