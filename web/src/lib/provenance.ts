/**
 * Provenance and source quotes of one process (`GET /processes/{ocid}/provenance` and `/quotes`).
 * Everything here is data from the API, shown as text: never HTML, never linkified.
 */

export interface ProvSource {
  id: string;
  name: string;
  publisher: string | null;
  licence: string | null;
  retrieved_at: string | null;
  url: string | null;
}

export interface ProvFact {
  key: string;
  label_es: string;
  value: string;
  source_id: string;
  source_field: string | null;
  derived: boolean;
  derivation_es: string | null;
  verify_es: string | null;
}

export interface Provenance {
  ocid: string;
  sources: ProvSource[];
  facts: ProvFact[];
}

export type QuoteKind = "enquiry_question" | "enquiry_answer" | "award_text";

export interface QuotePart {
  kind: QuoteKind;
  text: string;
  source_field: string | null;
}

export interface QuoteItem extends QuotePart {
  date: string | null;
  author_kind: "oferente" | "entidad" | null;
  similarity: number | null;
  truncated: boolean;
  pair: QuotePart | null;
}

export interface Quotes {
  ocid: string;
  items: QuoteItem[];
  available_total: number;
  omitted: { personal_data: number; unsafe: number; below_relevance: number };
  note_es: string | null;
}

const KINDS = new Set<QuoteKind>(["enquiry_question", "enquiry_answer", "award_text"]);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);
const num = (v: unknown, d = 0): number => (typeof v === "number" && Number.isFinite(v) ? v : d);
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * A 13-digit RUC whose third digit is 0 to 5 belongs to a natural person (docs/CONTRACT.md, rule 4).
 * Quotes and provenance values are masked here as a last guard, whatever the API sent.
 */
export function maskNaturalRuc(text: string): string {
  return text.replace(/(?<!\d)\d{2}[0-5]\d{10}(?!\d)/g, (m) => `${m.slice(0, 4)}*********`);
}

/** A published value as text: lists joined, booleans in Spanish, null as empty (the UI then says "No disponible"). */
function showValue(v: unknown): string {
  if (v == null) return "";
  if (Array.isArray(v)) return v.filter((x) => x != null).map(showValue).join(", ");
  if (typeof v === "boolean") return v ? "Sí" : "No";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function normalizeProvenance(raw: unknown): Provenance | null {
  if (!isObj(raw) || typeof raw.ocid !== "string") return null;
  const sources: ProvSource[] = (Array.isArray(raw.sources) ? raw.sources : []).flatMap((s) => {
    if (!isObj(s) || !str(s.id) || !str(s.name)) return [];
    return [{ id: s.id as string, name: s.name as string, publisher: str(s.publisher), licence: str(s.licence), retrieved_at: str(s.retrieved_at), url: safeUrl(s.url) }];
  });
  const facts: ProvFact[] = (Array.isArray(raw.facts) ? raw.facts : []).flatMap((f) => {
    if (!isObj(f) || !str(f.key) || !str(f.label_es)) return [];
    const value = maskNaturalRuc(showValue(f.value));
    return [
      {
        key: f.key as string,
        label_es: f.label_es as string,
        value,
        source_id: String(f.source_id ?? ""),
        source_field: str(f.source_field),
        derived: f.derived === true,
        derivation_es: str(f.derivation_es),
        verify_es: str(f.verify_es),
      },
    ];
  });
  return { ocid: raw.ocid, sources, facts };
}

/** Only http(s) links are kept. */
function safeUrl(v: unknown): string | null {
  const s = str(v);
  if (!s) return null;
  try {
    const u = new URL(s);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null;
  } catch {
    return null;
  }
}

function part(v: unknown): QuotePart | null {
  if (!isObj(v) || !KINDS.has(v.kind as QuoteKind) || !str(v.text)) return null;
  return { kind: v.kind as QuoteKind, text: maskNaturalRuc(v.text as string), source_field: str(v.source_field) };
}

export function normalizeQuotes(raw: unknown): Quotes | null {
  if (!isObj(raw) || typeof raw.ocid !== "string") return null;
  const items: QuoteItem[] = (Array.isArray(raw.items) ? raw.items : []).flatMap((it) => {
    const p = part(it);
    if (!p || !isObj(it)) return [];
    return [
      {
        ...p,
        date: str(it.date),
        author_kind: it.author_kind === "oferente" || it.author_kind === "entidad" ? it.author_kind : null,
        similarity: typeof it.similarity === "number" ? it.similarity : null,
        truncated: it.truncated === true,
        pair: part(it.pair),
      },
    ];
  });
  const om = isObj(raw.omitted) ? raw.omitted : {};
  return {
    ocid: raw.ocid,
    items,
    available_total: num(raw.available_total, items.length),
    omitted: { personal_data: num(om.personal_data), unsafe: num(om.unsafe), below_relevance: num(om.below_relevance) },
    note_es: str(raw.note_es),
  };
}

/** At most three passages; an answer already shown as the pair of a question is not repeated. */
export function pickQuotes(q: Quotes, max = 3): QuoteItem[] {
  const shown = new Set<string>();
  const out: QuoteItem[] = [];
  for (const it of q.items) {
    if (shown.has(it.text)) continue;
    out.push(it);
    shown.add(it.text);
    if (it.pair) shown.add(it.pair.text);
    if (out.length === max) break;
  }
  return out;
}

export function sourceById(p: Provenance, id: string): ProvSource | undefined {
  return p.sources.find((s) => s.id === id);
}

/** A ready-to-paste citation line for one fact. */
export function citationFor(p: Provenance, f: ProvFact, dateFmt: (v: string | null) => string): string {
  const s = sourceById(p, f.source_id);
  const bits = [
    `${f.label_es}: ${f.value || "no disponible"}`,
    s ? `Fuente: ${s.name}${s.publisher ? ` (${s.publisher})` : ""}` : null,
    f.source_field ? `campo «${f.source_field}»` : null,
    s?.retrieved_at ? `obtenido el ${dateFmt(s.retrieved_at)}` : null,
    s?.licence ? `licencia ${s.licence}` : null,
    s?.url ? s.url : null,
    `Proceso ${p.ocid}, consultado en Veedor (un producto de ruray.)`,
  ];
  return bits.filter(Boolean).join(". ").replace(/\.\s+(https?:)/, ". $1");
}
