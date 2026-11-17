import { allPages, expect, test } from "./fixtures";

test.describe("every page loads cleanly", () => {
  test("no console errors, CSP violations or failed requests; one h1; no horizontal scroll at 390px", async ({ page }) => {
    // The `health` fixture fails the test on any console error, CSP violation or failed request.
    await page.setViewportSize({ width: 390, height: 844 });
    for (const p of await allPages(page)) {
      const res = await page.goto(p.path, { waitUntil: "networkidle" });
      expect(res?.status(), `${p.name} status`).toBe(200);
      await expect(page.locator("h1"), `${p.name} h1`).toHaveCount(1);
      const { sw, cw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      expect(sw, `${p.name}: horizontal scroll (scrollWidth ${sw} > clientWidth ${cw})`).toBeLessThanOrEqual(cw);
    }
  });

  test("responses carry a nonce-based CSP", async ({ page }) => {
    const res = await page.goto("/");
    const csp = res?.headers()["content-security-policy"] ?? "";
    expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
    expect(csp).not.toMatch(/script-src[^;]*'unsafe-inline'/);
  });
});

test.describe("layout regressions found in Firefox and WebKit", () => {
  test("header byline stays on one line (Firefox wrapped it onto three)", async ({ page, isMobile }) => {
    test.skip(isMobile, "desktop header");
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const box = await page.locator(".brandline__by").boundingBox();
    expect(box!.height).toBeLessThan(24);
  });

  test("map metric switch: legend sits on the same row as the options (WebKit stacked it)", async ({ page, isMobile }) => {
    test.skip(isMobile, "wraps on a phone by design");
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/mapa");
    const legend = (await page.locator(".seg__legend").boundingBox())!;
    const opt = (await page.locator(".seg__opt").first().boundingBox())!;
    expect(Math.abs(legend.y + legend.height / 2 - (opt.y + opt.height / 2))).toBeLessThan(12);
  });
});
