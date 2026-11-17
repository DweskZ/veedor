import { NextResponse, type NextRequest } from "next/server";

const RUC = /^\d{13}$/;
// OCDS identifiers are "ocds-<publisher>-<process>"; "sample-ocid-" is the mock fixture prefix.
const OCID = /^(?:ocds-[a-z0-9]+|sample-ocid)-[A-Za-z0-9._-]{1,100}$/;
const API = (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";
const IS_DEV = process.env.NODE_ENV === "development";
const API_ORIGIN = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").origin;
  } catch {
    return "http://localhost:8000";
  }
})();

/**
 * Content Security Policy with a per-request nonce (node_modules/next/dist/docs/01-app/02-guides/content-security-policy.md).
 * Next.js reads the nonce from this header while rendering and puts it on its own scripts; the root layout puts it on the
 * one inline script it writes. `style-src` keeps 'unsafe-inline': the pages use style attributes, which a nonce cannot cover.
 */
function policy(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${IS_DEV ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self' ${API_ORIGIN}${IS_DEV ? " ws:" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

/** Continues (or rewrites) with the nonce on the request, so rendering sees it, and the policy on the response. */
function withPolicy(request: NextRequest, rewriteTo?: URL): NextResponse {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = policy(nonce);
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const res = rewriteTo ? NextResponse.rewrite(rewriteTo, { request: { headers } }) : NextResponse.next({ request: { headers } });
  res.headers.set("Content-Security-Policy", csp);
  return res;
}

const DETAIL_SECTIONS = new Set(["proveedores", "entidades", "procesos"]);

const notFound = (request: NextRequest) => withPolicy(request, new URL("/not-found-route", request.url));

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
  if (!DETAIL_SECTIONS.has(section) || (section === "procesos" && rawId === undefined)) return withPolicy(request);
  let id: string;
  try {
    id = decodeURIComponent(rawId ?? "");
  } catch {
    return notFound(request);
  }
  const path = apiPath(section, id, extra);
  if (!path) return notFound(request);
  if (USE_MOCKS) return withPolicy(request);
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
  return withPolicy(request);
}

// Every page (the policy is per request); assets, icons and the robots/sitemap files do not need it.
export const config = {
  matcher: [
    {
      source: "/((?!_next/|icon|apple-icon|opengraph-image|robots\\.txt|sitemap\\.xml|fonts/|art/).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
