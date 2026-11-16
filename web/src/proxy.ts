import { NextResponse, type NextRequest } from "next/server";

const RUC = /^\d{13}$/;
// OCDS identifiers are "ocds-<publisher>-<process>"; "sample-ocid-" is the mock fixture prefix.
const OCID = /^(?:ocds-[a-z0-9]+|sample-ocid)-[A-Za-z0-9._-]{1,100}$/;
const API = (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

const notFound = (request: NextRequest) => NextResponse.rewrite(new URL("/not-found-route", request.url));

/** Resource path on the API for a detail route, or null when the identifier is malformed. */
function apiPath(section: string, id: string, extra: string[]): string | null {
  if (extra.length) return null;
  if ((section === "proveedores" || section === "entidades") && RUC.test(id)) {
    return `${section === "proveedores" ? "suppliers" : "buyers"}/${id}`;
  }
  if (section === "procesos" && OCID.test(id)) return `processes/${encodeURIComponent(id)}`;
  return null;
}

/**
 * Real 404 status for unknown detail routes. A page that streams cannot change its status after the
 * shell is sent, so malformed identifiers and resources the API reports as missing are rejected here.
 * Any other API outcome (down, 5xx) passes through and the page renders its own error state.
 */
export async function proxy(request: NextRequest) {
  const [, section, rawId, ...extra] = request.nextUrl.pathname.split("/");
  let id: string;
  try {
    id = decodeURIComponent(rawId ?? "");
  } catch {
    return notFound(request);
  }
  const path = apiPath(section, id, extra);
  if (!path) return notFound(request);
  if (USE_MOCKS) return NextResponse.next();
  try {
    const res = await fetch(`${API}/${path}`, { method: "GET", cache: "no-store", signal: AbortSignal.timeout(4000) });
    if (res.status === 404) return notFound(request);
    if (res.ok && section === "proveedores") {
      // Supplier pages exist only for identified companies and public entities.
      const kind = ((await res.json()) as { profile?: { kind?: string } }).profile?.kind;
      if (kind !== "company" && kind !== "public_entity") return notFound(request);
    }
  } catch {
    /* API unreachable: let the page show its error state */
  }
  return NextResponse.next();
}

export const config = { matcher: ["/proveedores/:path*", "/entidades/:path*", "/procesos/:path+"] };
