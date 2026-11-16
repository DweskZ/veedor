import * as mocks from "./mocks";
import type {
  BuyerDetail,
  Dossier,
  Paginated,
  ProcessDetail,
  ProcessQuery,
  ProcessSummary,
  Review,
  ApiMeta,
  SignalDef,
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
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
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

/** Whether review registration is enabled. Unknown (field absent or request failed) counts as disabled. */
export async function getMeta(): Promise<ApiMeta> {
  if (USE_MOCKS) return mocks.meta;
  for (const path of ["/meta", "/health"]) {
    try {
      const body = await request<{ reviews_enabled?: unknown }>(path);
      if (typeof body.reviews_enabled === "boolean") return { reviews_enabled: body.reviews_enabled };
    } catch {
      /* try the next endpoint */
    }
  }
  return { reviews_enabled: null };
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
