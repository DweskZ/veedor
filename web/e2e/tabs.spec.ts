import { expect, randomOcid, test } from "./fixtures";

const path = async (page: import("@playwright/test").Page) => `/procesos/${encodeURIComponent(await randomOcid(page))}`;
const visiblePanels = (page: import("@playwright/test").Page) =>
  page.evaluate(() => [...document.querySelectorAll<HTMLElement>("[data-panel]")].filter((p) => !p.hidden && p.offsetHeight > 0).map((p) => p.dataset.panel));

test.describe("process page tabs (with JavaScript)", () => {
  test("shows the summary first, one panel at a time, and the tab is in the URL", async ({ page }) => {
    await page.goto(await path(page), { waitUntil: "networkidle" });
    const tabs = page.getByRole("tablist");
    await expect(tabs).toBeVisible();
    await expect(page.getByRole("tab", { name: "Resumen" })).toHaveAttribute("aria-selected", "true");
    expect(await visiblePanels(page)).toEqual(["resumen"]);

    await page.getByRole("tab", { name: /^Datos/ }).click();
    await expect(page).toHaveURL(/#hechos$/);
    expect(await visiblePanels(page)).toEqual(["hechos"]);
    await expect(page.getByRole("tab", { name: /^Datos/ })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toHaveCount(1);
  });

  test("arrow keys, Home and End move between tabs (roving tabindex)", async ({ page }) => {
    await page.goto(await path(page), { waitUntil: "networkidle" });
    const first = page.getByRole("tab").first();
    await first.focus();
    await expect(first).toHaveAttribute("tabindex", "0");
    await page.keyboard.press("ArrowRight");
    const second = page.getByRole("tab").nth(1);
    await expect(second).toBeFocused();
    await expect(second).toHaveAttribute("aria-selected", "true");
    await expect(first).toHaveAttribute("tabindex", "-1");
    expect((await visiblePanels(page)).length).toBe(1);
    await page.keyboard.press("End");
    const n = await page.getByRole("tab").count();
    await expect(page.getByRole("tab").nth(n - 1)).toBeFocused();
    await page.keyboard.press("ArrowRight"); // wraps to the first
    await expect(first).toBeFocused();
    await expect(first).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowLeft"); // wraps to the last
    await expect(page.getByRole("tab").nth(n - 1)).toBeFocused();
  });

  test("a link to a tab or to a signal opens its panel", async ({ page }) => {
    const p = await path(page);
    await page.goto(p, { waitUntil: "networkidle" });
    await page.getByRole("tab", { name: /^Señales/ }).click();
    const id = await page.locator("article[id^='sig-']").first().getAttribute("id");
    expect(id).toBeTruthy();

    await page.goto(`${p}#verificar`, { waitUntil: "networkidle" });
    expect(await visiblePanels(page)).toEqual(["verificar"]);

    await page.goto(`${p}#${id}`, { waitUntil: "networkidle" });
    await expect(page.getByRole("tab", { name: /^Señales/ })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(`[id="${id}"]`)).toBeInViewport();

    // Following a link inside the page changes the panel too (hashchange).
    await page.evaluate(() => (location.hash = "#fuentes"));
    await expect.poll(() => visiblePanels(page)).toEqual(["fuentes"]);
  });
});

test.describe("process page without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("every section is in the HTML and readable, in document order, with anchor links", async ({ page }) => {
    await page.goto(await path(page));
    const panels = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>("[data-panel]")].map((p) => ({ id: p.dataset.panel, h: p.offsetHeight, hidden: p.hidden })));
    expect(panels.length).toBeGreaterThanOrEqual(7);
    expect(panels.filter((p) => p.hidden || p.h === 0)).toEqual([]);
    expect(panels[0].id).toBe("resumen");
    const nav = page.getByRole("navigation", { name: "Secciones de este proceso" });
    await expect(nav.getByRole("link", { name: /^Señales/ })).toHaveAttribute("href", "#senales");
    await expect(page.getByRole("tablist")).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 2, name: "Señales de riesgo" })).toBeVisible();
  });
});
