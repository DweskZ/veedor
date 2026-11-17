/** Public base URL (build time). */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000").replace(/\/$/, "");

/** Search engines are kept out until the owner opts in with NEXT_PUBLIC_ALLOW_INDEXING=1 (or "true"), set at build time. */
export const ALLOW_INDEXING = ["1", "true"].includes((process.env.NEXT_PUBLIC_ALLOW_INDEXING ?? "").trim().toLowerCase());

/** Static routes only. Process, supplier and entity pages are never listed. */
export const STATIC_ROUTES = ["/", "/procesos", "/mapa", "/tendencias", "/agentes", "/metodologia", "/glosario"] as const;
