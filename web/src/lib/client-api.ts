import { AskError, normalizeAsk, parseRetryAfter, type AskAnswer } from "./ask";
import type { BuyerHit } from "./types";

/** Browser-side calls to the API (CSP allows only this origin). No server-only code or mock layer is pulled in. */
const API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

const SAMPLE_BUYERS: BuyerHit[] = [
  { ruc: "0000000000001", name: "Entidad de ejemplo A", region_label: "Región de ejemplo 1", processes_total: 3 },
  { ruc: "0000000000002", name: "Entidad de ejemplo B", region_label: "Región de ejemplo 2", processes_total: 2 },
  { ruc: "0000000000003", name: "Entidad de ejemplo C", region_label: "Región de ejemplo 1", processes_total: 1 },
];

const isRec = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

/** Suggestions for the header search. Throws on network errors and aborts; callers handle both. */
export async function searchBuyers(q: string, signal: AbortSignal): Promise<BuyerHit[]> {
  if (MOCKS) {
    const n = q.toLowerCase();
    return SAMPLE_BUYERS.filter((b) => b.name.toLowerCase().includes(n) || n.includes("ejemplo"));
  }
  const res = await fetch(`${API}/buyers/search?q=${encodeURIComponent(q)}&limit=8`, { signal });
  if (!res.ok) throw new Error(String(res.status));
  const body: unknown = await res.json();
  const items = isRec(body) && Array.isArray(body.items) ? body.items : [];
  return items.flatMap((i): BuyerHit[] =>
    isRec(i) && typeof i.ruc === "string" && typeof i.name === "string"
      ? [
          {
            ruc: i.ruc,
            name: i.name,
            region_label: typeof i.region_label === "string" ? i.region_label : null,
            processes_total: typeof i.processes_total === "number" ? i.processes_total : null,
          },
        ]
      : [],
  );
}

/** OCID of one random process, or null when none matches. */
export async function randomProcess(withSignals: boolean): Promise<string | null> {
  if (MOCKS) return "sample-ocid-0001";
  const res = await fetch(`${API}/processes/random?with_signals=${withSignals}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(String(res.status));
  const body: unknown = await res.json();
  const item = isRec(body) && isRec(body.item) ? body.item : body;
  return isRec(item) && typeof item.ocid === "string" ? item.ocid : null;
}

/**
 * Asks one question about one process. The question travels only in the POST body (never in a URL), with no cookies and no
 * referrer. Throws `AskError` (limit, invalid, disabled, error) and lets an abort propagate as is.
 */
export async function askProcess(ocid: string, question: string, signal: AbortSignal): Promise<AskAnswer> {
  let status = 200;
  let body: unknown;
  let retryAfter: number | null = null;
  if (MOCKS) {
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, 900);
      signal.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
    });
    const mocks = await import("./mocks");
    const m = mocks.ask(ocid, question) as { __status?: number; retryAfter?: number };
    if (m.__status) { status = m.__status; retryAfter = m.retryAfter ?? null; } else body = m;
  } else {
    let res: Response;
    try {
      res = await fetch(`${API}/processes/${encodeURIComponent(ocid)}/ask`, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json" },
        body: JSON.stringify({ question }),
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
        signal,
      });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") throw e;
      throw new AskError({ kind: "error", message: "No se pudo conectar con el servicio de datos." });
    }
    status = res.status;
    retryAfter = parseRetryAfter(res.headers.get("retry-after"));
    try {
      body = await res.json();
    } catch {
      body = null;
    }
  }
  if (status === 404) throw new AskError({ kind: "disabled" });
  if (status === 429) throw new AskError({ kind: "limit", retryAfterSeconds: retryAfter });
  if (status === 422) {
    const msg = isRec(body) && isRec(body.error) && typeof body.error.message === "string" ? body.error.message : "La pregunta no es válida.";
    throw new AskError({ kind: "invalid", message: msg });
  }
  if (status < 200 || status >= 300) throw new AskError({ kind: "error", message: "El servicio de datos no pudo responder ahora." });
  const answer = normalizeAsk(body);
  if (!answer) throw new AskError({ kind: "error", message: "La respuesta del servicio no tiene el formato esperado." });
  return answer;
}
