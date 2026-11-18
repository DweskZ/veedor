import { revalidateSeconds } from "./cache-policy";
import { normalizeInvestigation } from "./investigation";
import { normalizeContext, normalizeProcessThreshold, normalizeRegions, normalizeThresholds, normalizeYears } from "./normalize";
import * as mocks from "./mocks";
import { normalizeProvenance, normalizeQuotes, type Provenance, type Quotes } from "./provenance";
import type {
  BuyerDetail,
  Dossier,
  Investigation,
  Paginated,
  ProcessContext,
  ProcessThreshold,
  ThresholdStats,
  RegionStats,
  YearStats,
  ProcessDetail,
  ProcessQuery,
  ProcessSummary,
  Review,
  ApiMeta,
  SignalDef,
  SimilarProcesses,
  Stats,
  SupplierDetail,
} from "./types";

const PUBLIC_API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
/** Browser calls use the public URL (inlined at build time); server-side calls may use a runtime-only internal URL. */
export const API_URL =
  typeof window === "undefined" && process.env.API_INTERNAL_URL
    ? process.env.API_INTERNAL_URL.replace(/\/$/, "")
    : PUBLIC_API_URL;
export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly code: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // A relative API URL only resolves in a browser. On the server it means no API is reachable (an image build
  // without API_INTERNAL_URL), so fail at once instead of handing the framework a URL it cannot fetch.
  if (typeof window === "undefined" && !/^https?:\/\//.test(API_URL)) {
    throw new ApiError("No se pudo conectar con el servicio de datos.", null);
  }
  let res: Response;
  try {
    const ttl = revalidateSeconds(path);
    const cache: RequestInit = ttl === null ? { cache: "no-store" } : ({ next: { revalidate: ttl } } as RequestInit);
    res = await fetch(`${API_URL}${path}`, { ...cache, ...init });
  } catch {
    throw new ApiError("No se pudo conectar con el servicio de datos.", null);
  }
  if (!res.ok) {
    let code: string | null = null;
    let message = res.status === 404 ? "No se encontró el recurso solicitado." : `El servicio respondió con error (${res.status}).`;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      code = body.error?.code ?? null;
      if (body.error?.message) message = body.error.message;
    } catch {
      /* body is not the standard error envelope */
    }
    throw new ApiError(message, res.status, code);
  }
  return (await res.json()) as T;
}

function qs(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) sp.set(k, v);
  const s = sp.toString();
  return s ? `?${s}` : "";
}

const mock = <T,>(f: () => T): T => {
  try {
    return f();
  } catch {
    throw new ApiError("No se encontró el recurso solicitado.", 404);
  }
};

const enc = encodeURIComponent;

export const getStats = (): Promise<Stats> => (USE_MOCKS ? Promise.resolve(mocks.stats) : request("/stats"));

export const getProcesses = (q: ProcessQuery): Promise<Paginated<ProcessSummary>> =>
  USE_MOCKS ? Promise.resolve(mocks.listProcesses(q)) : request(`/processes${qs({ ...q })}`);

export const getProcess = (ocid: string): Promise<ProcessDetail> =>
  USE_MOCKS ? Promise.resolve(mock(() => mocks.processDetail(ocid))) : request(`/processes/${enc(ocid)}`);

export const getDossier = (ocid: string): Promise<Dossier> =>
  USE_MOCKS ? Promise.resolve(mock(() => mocks.dossier(ocid))) : request(`/processes/${enc(ocid)}/dossier`);

export const getSignals = (): Promise<SignalDef[]> => (USE_MOCKS ? Promise.resolve(mocks.signals) : request("/signals"));

export const getSupplier = (ruc: string): Promise<SupplierDetail> =>
  USE_MOCKS ? Promise.resolve(mock(() => mocks.supplier(ruc))) : request(`/suppliers/${enc(ruc)}`);

export const getBuyer = (ruc: string): Promise<BuyerDetail> =>
  USE_MOCKS ? Promise.resolve(mock(() => mocks.buyer(ruc))) : request(`/buyers/${enc(ruc)}`);

export const getReviews = (ocid: string): Promise<Review[]> =>
  USE_MOCKS ? Promise.resolve(mocks.reviews()) : request(`/processes/${enc(ocid)}/reviews`);

/** Whether review registration and the question box are enabled. Unknown (field absent or request failed) counts as disabled. */
export async function getMeta(): Promise<ApiMeta> {
  if (USE_MOCKS) return mocks.meta;
  for (const path of ["/meta", "/health"]) {
    try {
      const body = await request<{ reviews_enabled?: unknown; ask_enabled?: unknown; quotes_enabled?: unknown; ask_mode?: unknown }>(path);
      if (typeof body.reviews_enabled === "boolean")
        return {
          reviews_enabled: body.reviews_enabled,
          ask_enabled: typeof body.ask_enabled === "boolean" ? body.ask_enabled : null,
          quotes_enabled: typeof body.quotes_enabled === "boolean" ? body.quotes_enabled : null,
          ask_mode: body.ask_mode === "retrieval" || body.ask_mode === "model" ? body.ask_mode : null,
        };
    } catch {
      /* try the next endpoint */
    }
  }
  return { reviews_enabled: null, ask_enabled: null, quotes_enabled: null, ask_mode: null };
}

export interface SignalIndex {
  labels: Record<string, string>;
  /** Codes of context signals (shown apart; they do not affect the score). */
  context: string[];
}

/** Never throws: callers fall back to the code and treat every signal as a risk signal. */
export async function getSignalIndex(): Promise<SignalIndex> {
  try {
    const defs = await getSignals();
    return {
      labels: Object.fromEntries(defs.map((s) => [s.code, s.label_es])),
      context: defs.filter((s) => s.kind === "context").map((s) => s.code),
    };
  } catch {
    return { labels: {}, context: [] };
  }
}

/** Stored investigation, or null when none exists (the API never starts one). Other failures throw. */
export async function getInvestigation(ocid: string): Promise<Investigation | null> {
  if (USE_MOCKS) return mocks.investigation(ocid);
  try {
    return normalizeInvestigation(await request<unknown>(`/processes/${enc(ocid)}/investigation`));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** Throws ApiError: 404 with code `not_indexed` (catalogue or no safe text), 503 `vectors_unavailable`. */
export const getSimilar = (ocid: string, sameBuyer: boolean, k = 10): Promise<SimilarProcesses> =>
  USE_MOCKS
    ? Promise.resolve(mock(() => mocks.similar(ocid, sameBuyer, k)))
    : request(`/processes/${enc(ocid)}/similar${qs({ k: String(k), same_buyer: sameBuyer ? "true" : undefined })}`);

/** New aggregate endpoints. They throw ApiError (the page then shows "no disponible"). */
export const getRegions = async (): Promise<RegionStats> =>
  USE_MOCKS ? mocks.regions : normalizeRegions(await request<unknown>("/stats/by-region"));

export const getYears = async (): Promise<YearStats> =>
  USE_MOCKS ? mocks.years : normalizeYears(await request<unknown>("/stats/by-year"));

/** Comparison data for one process, or null when the API has none (404) or does not offer it. */
export async function getContext(ocid: string): Promise<ProcessContext | null> {
  if (USE_MOCKS) return mocks.context(ocid);
  try {
    return normalizeContext(await request<unknown>(`/processes/${enc(ocid)}/context`));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) return null;
    throw e;
  }
}

/** Where each datum came from. Null when the API has none (404) or does not offer it yet. Other failures throw. */
export async function getProvenance(ocid: string): Promise<Provenance | null> {
  if (USE_MOCKS) return mocks.provenance(ocid);
  try {
    return normalizeProvenance(await request<unknown>(`/processes/${enc(ocid)}/provenance`));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) return null;
    throw e;
  }
}

/** A few passages written by bidders or the buying entity, as published. Null when none or not offered. */
export async function getQuotes(ocid: string): Promise<Quotes | null> {
  if (USE_MOCKS) return mocks.quotes(ocid);
  try {
    return normalizeQuotes(await request<unknown>(`/processes/${enc(ocid)}/quotes`));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) return null;
    throw e;
  }
}

/** Procedure-amount thresholds by year and category, with the counts just below and above. Throws ApiError (the section then says "no disponible"). */
export const getThresholds = async (): Promise<ThresholdStats> => {
  if (USE_MOCKS) throw new ApiError("No se encontró el recurso solicitado.", 404);
  return normalizeThresholds(await request<unknown>("/stats/thresholds"));
};

/** The threshold that applies to one process, or null when the API does not offer it (404) or has nothing for it. Other failures throw. */
export async function getProcessThreshold(ocid: string): Promise<ProcessThreshold | null> {
  if (USE_MOCKS) return null;
  try {
    return normalizeProcessThreshold(await request<unknown>(`/processes/${enc(ocid)}/threshold`));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) return null;
    throw e;
  }
}
