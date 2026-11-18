import { isIP } from "node:net";

/**
 * Pure helpers for the server-side calls to the API (no framework imports, so they run under `node --test`).
 *
 * How the visitor's address reaches the API: Caddy sets `X-Forwarded-For` to the TCP peer it sees (it discards
 * any client-supplied value, deploy/Caddyfile) and proxies to this server; Next.js keeps that header on the
 * incoming request; the server-side `fetch` forwards it; the API honours it only when the direct peer is one of
 * the two fixed addresses in its `FORWARDED_ALLOW_IPS` (Caddy and this container). See docs/SECURITY.md.
 */

/**
 * The visitor's address from an `X-Forwarded-For` value, or null when there is none or it is not an IP address.
 * The LAST entry is used: it is the one the nearest proxy (Caddy) wrote, so an entry a client put in front of it
 * is never read. Nothing but a bare IPv4 or IPv6 address is accepted, so no other text reaches the API.
 */
export function visitorAddress(forwardedFor: string | null | undefined): string | null {
  if (!forwardedFor || forwardedFor.length > 512) return null;
  const last = forwardedFor.split(",").at(-1)?.trim() ?? "";
  return isIP(last) !== 0 ? last : null;
}

/** Headers to add to a server-side API call made for a visitor; empty when the visitor is unknown. */
export function visitorHeaders(forwardedFor: string | null | undefined): Record<string, string> {
  const address = visitorAddress(forwardedFor);
  return address ? { "x-forwarded-for": address } : {};
}

/** Whether a URL can be fetched from the server: relative URLs only resolve in a browser. */
export function isFetchableServerUrl(url: string): boolean {
  return /^https?:\/\//.test(url);
}

/** A message when `API_INTERNAL_URL` is set but not an absolute http(s) URL (every server-side call would fail). */
export function internalUrlProblem(value: string | undefined): string | null {
  if (value === undefined || value === "" || isFetchableServerUrl(value)) return null;
  return `API_INTERNAL_URL is set to "${value}", which is not an absolute http(s) URL (for example http://api:8000/api/v1). Server-side requests to the API will all fail until it is fixed.`;
}

/**
 * Origin to add to the CSP `connect-src` for the browser's API calls: nothing when the public API URL is relative
 * (same origin, already covered by 'self') or invalid; the development default when the variable is unset.
 */
export function connectOrigin(publicApiUrl: string | undefined): string | null {
  const raw = publicApiUrl ?? "http://localhost:8000/api/v1";
  if (!isFetchableServerUrl(raw)) return null;
  try {
    return new URL(raw).origin;
  } catch {
    return null;
  }
}

const warned = Symbol.for("veedor.warned");
type Warned = { [warned]?: Set<string> };

/** Logs once per process and message, even when several bundles (pages, proxy) load this module separately. */
export function warnOnce(message: string, log: (message: string) => void = console.error): void {
  const seen = ((globalThis as Warned)[warned] ??= new Set<string>());
  if (seen.has(message)) return;
  seen.add(message);
  log(message);
}
