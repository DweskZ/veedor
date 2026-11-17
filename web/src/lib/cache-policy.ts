/**
 * How long a server-side read may be reused, in seconds, mirroring the API's own Cache-Control classes
 * (src/veedor/api/http_cache.py). `null` means never reuse: live flags, random picks, privacy-gated or
 * token-gated data, and anything whose state lives outside the data build.
 */
export function revalidateSeconds(path: string): number | null {
  const p = path.split("?")[0];
  if (p === "/glossary" || p === "/signals" || p === "/stats" || p.startsWith("/stats/")) return 300;
  if (p === "/processes") return 30;
  if (/^\/(suppliers|buyers)\/[^/]+$/.test(p) && p !== "/buyers/search") return 60;
  if (/^\/processes\/[^/]+(\/(context|threshold))?$/.test(p) && p !== "/processes/random") return 60;
  return null;
}
