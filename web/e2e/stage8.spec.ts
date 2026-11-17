import { API, expect, test } from "./fixtures";

/** A process the threshold endpoint says applies (and one it says does not), found through the API itself. */
async function thresholdOcids(page: import("@playwright/test").Page) {
  const list = await page.request.get(`${API}/processes?page_size=60`);
  const items = ((await list.json()) as { items: { ocid: string }[] }).items;
  let yes: string | null = null;
  let no: string | null = null;
  for (const i of items) {
    const r = await page.request.get(`${API}/processes/${encodeURIComponent(i.ocid)}/threshold`);
    if (!r.ok()) continue;
    const b = (await r.json()) as { applicable: boolean };
    if (b.applicable && !yes) yes = i.ocid;
    if (!b.applicable && !no) no = i.ocid;
    if (yes && no) break;
  }
  return { yes, no };
}

test.describe("validation story", () => {
  test("home: two tests, two answers, what it does not mean", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    const h = page.getByRole("heading", { level: 2, name: /¿El puntaje dice algo\? Dos pruebas, dos respuestas distintas\./ });
    await expect(h).toBeVisible();
    const section = page.locator("section[aria-labelledby='ev-h']");
    await expect(section.getByRole("heading", { level: 3, name: "No concluyente" })).toBeVisible();
    await expect(section.getByRole("heading", { level: 3, name: "Sí, pero poco" })).toBeVisible();
    await expect(section).toContainText("Qué no significa");
    await expect(section).toContainText(/Solo 9 empresas de esa lista/);
    await expect(section).toContainText(/1\.112/);
    await expect(section).toContainText(/8,3 puntos porcentuales/);
    for (const banned of [/\bAUC\b/, /p-valor/i, /regresión/i, /acertó igual que el azar/i]) await expect(section).not.toContainText(banned);
    await expect(section.getByRole("link", { name: "Ver las dos pruebas completas" })).toHaveAttribute("href", "/metodologia#evaluacion");
  });

  test("methodology: figures, chart with a zero line, tables and the inconclusive list test", async ({ page }) => {
    await page.goto("/metodologia", { waitUntil: "networkidle" });
    const sec = page.locator("#s-evaluacion");
    await expect(sec.getByRole("heading", { level: 2, name: /Validación/ })).toBeVisible();
    const chart = sec.getByRole("img", { name: /diferencia de ahorro por señal/i });
    await expect(chart).toBeVisible();
    await expect(chart).toContainText("0 = sin diferencia");
    const row = sec.getByRole("row", { name: /Oferente único/ }).first();
    await expect(row).toContainText("−8,3");
    await expect(row).toContainText("Menos ahorro");
    await expect(sec).toContainText("no concluyente");
    await expect(sec).toContainText(/AUC de alrededor de 0,77/);
    await expect(sec).toContainText(/no es una irregularidad/i);
    await expect(sec).not.toContainText(/acertó igual que el azar/i);
    expect(await page.locator("a[href*='VALIDATION']").count()).toBe(0);
  });
});

test.describe("procedure thresholds", () => {
  test("trends: table by year, bar chart, caveats and the plain sentence", async ({ page }) => {
    await page.goto("/tendencias", { waitUntil: "networkidle" });
    const sec = page.locator("#umbrales");
    await expect(sec.getByRole("heading", { level: 2, name: "Montos que cambian el procedimiento" })).toBeVisible();
    await expect(sec.getByRole("row", { name: /^2015/ })).toContainText("$72.634,23");
    await expect(sec.getByRole("row", { name: /^2025/ })).toContainText("Excluido");
    await expect(sec.getByRole("img", { name: /Gráfico de barras/ })).toBeVisible();
    await expect(sec).toContainText("Esto no dice por qué las compras quedan donde quedan.");
    await expect(sec).toContainText(/ínfima cuantía no están en los datos abiertos/);
    await expect(sec).toContainText(/2025 queda fuera/);
  });

  test("process page: neutral threshold card in Resumen with its source, and a row in Datos", async ({ page }) => {
    const { yes } = await thresholdOcids(page);
    test.skip(!yes, "no process with an applicable threshold in the first page of the API");
    await page.goto(`/procesos/${encodeURIComponent(yes!)}`, { waitUntil: "networkidle" });
    const card = page.locator("section.thr");
    await expect(card).toBeVisible();
    await expect(card).toContainText("Contexto · no es una señal de riesgo");
    await expect(card).toContainText(/por debajo del umbral/);
    await expect(card.getByRole("link", { name: /Montos de contratación/ })).toHaveAttribute("href", /^https:\/\//);
    await expect(card).not.toContainText(/fraude|corrup|irregular/i);
    await page.getByRole("tab", { name: /^Datos/ }).click();
    await expect(page.locator("[data-panel='hechos']")).toContainText("Umbral de contratación");
  });

  test("process page: a process with no applicable threshold shows at most one muted line", async ({ page }) => {
    const { no } = await thresholdOcids(page);
    test.skip(!no, "no process without an applicable threshold in the first page");
    await page.goto(`/procesos/${encodeURIComponent(no!)}`, { waitUntil: "networkidle" });
    await expect(page.locator("section.thr")).toHaveCount(0);
    expect(await page.locator("#umbral").count()).toBeLessThanOrEqual(1);
  });
});

test.describe("glossary", () => {
  test("new terms are listed", async ({ page }) => {
    await page.goto("/glosario", { waitUntil: "networkidle" });
    for (const t of ["umbral de contratación", "ínfima cuantía", "presupuesto inicial del Estado (PIE)", "ahorro frente al presupuesto"]) await expect(page.getByText(t, { exact: true }).first()).toBeVisible();
  });
});
