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
] as const;

export async function randomOcid(page: Page): Promise<string> {
  const res = await page.request.get(`${API}/processes/random?with_signals=true`);
  expect(res.ok(), "random process endpoint").toBeTruthy();
  return ((await res.json()) as { ocid: string }).ocid;
}

export async function allPages(page: Page) {
  const ocid = await randomOcid(page);
  return [...STATIC_PAGES, { name: "proceso", path: `/procesos/${encodeURIComponent(ocid)}` }];
}

/**
 * Every test gets a `health` collector. It records console errors, uncaught exceptions, CSP violations
 * and failed or 4xx/5xx requests; the fixture fails the test on teardown if anything was recorded.
 */
export const test = base.extend<{ health: string[] }>({
  health: [
    async ({ page }, use) => {
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
