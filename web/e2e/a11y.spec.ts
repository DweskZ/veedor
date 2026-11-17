import AxeBuilder from "@axe-core/playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { measureContrast } from "./contrast";
import { allPages, expect, test } from "./fixtures";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("axe, WCAG 2.1 A and AA", () => {
  test.skip(({ browserName, isMobile }) => !(browserName === "chromium" || (browserName === "webkit" && !isMobile)), "axe runs on chromium and desktop webkit");

  test("no violations on any page", async ({ page, browserName }) => {
    const rows: { page: string; rule: string; impact: string | null | undefined; nodes: number; targets: string[] }[] = [];
    const incompleteRows: string[] = [];
    for (const p of await allPages(page)) {
      await page.goto(p.path, { waitUntil: "networkidle" });
      const { violations, incomplete } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      incompleteRows.push(...incomplete.map((i) => `${p.name}: ${i.id} (${i.nodes.length})`));
      for (const v of violations) rows.push({ page: p.name, rule: v.id, impact: v.impact, nodes: v.nodes.length, targets: v.nodes.slice(0, 6).map((n) => n.target.join(" ") + " :: " + (n.any[0]?.message ?? n.all[0]?.message ?? n.none[0]?.message ?? "")) });
    }
    mkdirSync("test-results/axe", { recursive: true });
    writeFileSync(`test-results/axe/${browserName}.json`, JSON.stringify({ violations: rows, needsReview: incompleteRows }, null, 2));
    expect(rows.map((r) => `${r.page}: ${r.rule} (${r.nodes})`), "axe violations").toEqual([]);
  });
});

test.describe("contrast axe cannot resolve (SVG text, selects with a background image, overlapping labels)", () => {
  test.skip(({ browserName, isMobile }) => !(browserName === "chromium" || (browserName === "webkit" && !isMobile)), "runs on chromium and desktop webkit");

  test("the measurer flags a low-contrast sample (self-check)", async ({ page }) => {
    await page.goto("/glosario");
    await page.evaluate(() => {
      const b = document.createElement("button");
      b.style.cssText = "color:#9aa3b8;background:#fff;font-size:16px";
      b.textContent = "low contrast sample";
      document.body.prepend(b);
    });
    const { fails } = await measureContrast(page, "self-check");
    expect(fails.map((f) => f.text)).toContain("low contrast sample");
  });

  test("WCAG AA ratios hold for every text element on every page, at 1280 and 390 px", async ({ page }) => {
    const all = [];
    const lows: string[] = [];
    for (const p of await allPages(page)) {
      for (const width of [1280, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(p.path, { waitUntil: "networkidle" });
        const { fails, lowest } = await measureContrast(page, `${p.name}@${width}`);
        all.push(...fails);
        lows.push(`${p.name}@${width}: lowest ${lowest.ratio}:1 ("${lowest.text}")`);
      }
    }
    test.info().annotations.push({ type: "lowest ratios", description: lows.join("\n") });
    expect(all, "text below WCAG AA contrast").toEqual([]);
  });
});
