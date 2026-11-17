import { expect, test as base, type Page } from "@playwright/test";

import { API } from "./env";

export { API };

/** Pages covered by the suite. `/procesos/<ocid>` is resolved at run time from the API. */
export const STATIC_PAGES = [
  { name: "home", path: "/" },
  { name: "procesos", path: "/procesos" },
  { name: "mapa", path: "/mapa" },
  { name: "tendencias", path: "/tendencias" },
  { name: "glosario", path: "/glosario" },
  { name: "metodologia", path: "/metodologia" },
  { name: "agentes", path: "/agentes" },
] as const;

export async function randomOcid(page: Page): Promise<string> {
  const res = await page.request.get(`${API}/processes/random?with_signals=true`);
  expect(res.ok(), "random process endpoint").toBeTruthy();
  return ((await res.json()) as { ocid: string }).ocid;
}

/** A supplier (company) and a buyer that the explorer links to, taken from the API's own listing. */
export async function linkedParties(page: Page): Promise<{ supplier: string; buyer: string }> {
  const res = await page.request.get(`${API}/processes?sort=-risk_score&page_size=50`);
  expect(res.ok(), "process list endpoint").toBeTruthy();
  const items = ((await res.json()) as { items: { winner_ruc: string | null; winner_kind: string | null; buyer_ruc: string | null }[] }).items;
  const hit = items.find((i) => i.winner_kind === "company" && i.winner_ruc && i.buyer_ruc);
  expect(hit, "a listed process with a company winner and a buyer").toBeTruthy();
  return { supplier: hit!.winner_ruc!, buyer: hit!.buyer_ruc! };
}

export async function allPages(page: Page) {
  const ocid = await randomOcid(page);
  const { supplier, buyer } = await linkedParties(page);
  return [
    ...STATIC_PAGES,
    { name: "proceso", path: `/procesos/${encodeURIComponent(ocid)}` },
    { name: "proveedor", path: `/proveedores/${supplier}` },
    { name: "entidad", path: `/entidades/${buyer}` },
  ];
}

/**
 * Every test gets a `health` collector. It records console errors, uncaught exceptions, CSP violations
 * and failed or 4xx/5xx requests; the fixture fails the test on teardown if anything was recorded.
 */
export const test = base.extend<{ health: string[] }>({
  health: [
    async ({ page, javaScriptEnabled }, use) => {
      const issues: string[] = [];
      // The API only lists the stack's own web origin for CORS; when the suite runs against another port (for example a
      // local production build on :3100) add the header so the browser lets the page read the API. Nothing else is altered.
      await page.route(`${API}/**`, async (route) => {
        const res = await route.fetch();
        const headers = res.headers();
        if (!headers["access-control-allow-origin"]) headers["access-control-allow-origin"] = "*";
        await route.fulfill({ response: res, headers });
      });
      await page.addInitScript(() => {
        document.addEventListener("securitypolicyviolation", (e) => {
          console.error(`CSP-VIOLATION ${e.violatedDirective} ${e.blockedURI}`);
        });
      });
      page.on("console", (m) => {
        if (m.type() === "error") issues.push(`console.error: ${m.text()}`);
      });
      page.on("pageerror", (e) => {
        // WebKit reports a Next.js router prefetch (?_rsc=) cancelled by a navigation as an "access control checks" error.
        if (/_rsc=.*due to access control checks/.test(e.message)) return;
        issues.push(`pageerror: ${e.message}`);
      });
      page.on("requestfailed", (r) => {
        const why = r.failure()?.errorText ?? "";
        // Navigations and RSC prefetches aborted by a later navigation are not defects.
        if (/abort|cancel/i.test(why)) return;
        // Without JavaScript the browser itself refuses to load scripts: that is the point of such a test, not a defect.
        if (!javaScriptEnabled && r.resourceType() === "script") return;
        issues.push(`requestfailed: ${r.method()} ${r.url()} ${why}`);
      });
      page.on("response", (r) => {
        if (r.status() >= 400) issues.push(`http ${r.status()}: ${r.url()}`);
      });
      await use(issues);
      expect(issues, "console errors, CSP violations and failed requests").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
