import { expect, randomOcid, test } from "./fixtures";

test("home renders the hero and the main navigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  if (test.info().project.use.isMobile) await page.getByRole("button", { name: "Menú" }).click();
  await expect(page.getByRole("banner").getByRole("search")).toBeVisible();
});

test.describe("explorer /procesos", () => {
  test("quick chip, province filter, remove a filter", async ({ page }) => {
    await page.goto("/procesos");
    const chips = page.getByRole("group", { name: "Filtros rápidos" }).getByRole("link");
    await expect(chips.first()).toBeVisible();
    await chips.first().click();
    await expect(page).toHaveURL(/\/procesos\?.+/);
    await expect(page.getByRole("list", { name: "Filtros activos" })).toBeVisible();

    const region = page.getByLabel("Provincia de la entidad");
    const firstProvince = await region.locator("option:not([value=''])").first().getAttribute("value");
    await region.selectOption(firstProvince!);
    await expect(page).toHaveURL(new RegExp(`region=${firstProvince}`));
    const active = page.getByRole("list", { name: "Filtros activos" });
    await expect(active.getByRole("link", { name: /Provincia/ })).toBeVisible();

    await active.getByRole("link", { name: /Provincia/ }).click();
    await expect(page).not.toHaveURL(/region=/);
    await expect(page.getByLabel("Provincia de la entidad")).toHaveValue("");
  });

  test("empty state when nothing matches", async ({ page }) => {
    await page.goto("/procesos?q=zzzzqqqqxx");
    await expect(page.getByText("Ningún proceso coincide con estos filtros.")).toBeVisible();
  });
});

test("process page renders a dossier", async ({ page }) => {
  const ocid = await randomOcid(page);
  const res = await page.goto(`/procesos/${encodeURIComponent(ocid)}`);
  expect(res?.status()).toBe(200);
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.getByText(ocid).first()).toBeVisible();
});

test.describe("map /mapa", () => {
  test("keyboard focus on a province, metric switch, click-through", async ({ page, isMobile }) => {
    await page.goto("/mapa");
    const group = page.getByRole("group", { name: /Mapa de las provincias/ });
    const provinces = group.getByRole("link");
    expect(await provinces.count()).toBeGreaterThan(10);

    // The map is one tab stop (roving tabindex); arrows move between provinces.
    const first = provinces.locator("visible=true").first();
    await first.focus();
    const name1 = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
    await page.keyboard.press("ArrowRight");
    const name2 = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
    expect(name2).not.toBe(name1);
    await expect(page.locator(".map__tip")).toBeVisible();

    const metrics = page.getByRole("group", { name: "Qué mostrar" }).getByRole("radio");
    expect(await metrics.count()).toBeGreaterThan(1);
    const before = await page.locator(".map__def").textContent();
    await page.getByRole("group", { name: "Qué mostrar" }).locator("label").nth(1).click();
    await expect(page.locator(".map__def")).not.toHaveText(before ?? "");

    if (!isMobile) {
      await page.keyboard.press("Tab"); // leaves the map; return to a province and open it
      await first.focus();
      await page.keyboard.press("Enter");
    } else {
      await first.click(); // first tap selects, the second opens
      await first.click();
    }
    await expect(page).toHaveURL(/\/procesos\?region=/);
  });
});

test("trends: pointer and keyboard update the readout", async ({ page, isMobile }) => {
  await page.goto("/tendencias");
  const chart = page.getByRole("group", { name: /Usa las flechas izquierda y derecha/ }).first();
  await expect(chart).toBeVisible();
  const out = page.locator(".trend__out").first();
  await chart.focus();
  await page.keyboard.press("Home");
  const a = await out.textContent();
  await page.keyboard.press("End");
  const b = await out.textContent();
  expect(a).not.toBe(b);
  if (!isMobile) {
    const box = (await chart.boundingBox())!;
    await chart.hover({ position: { x: box.width * 0.25, y: 100 } });
    await expect(out).not.toHaveText(b ?? "");
  }
});

test("glossary page lists terms with anchors", async ({ page }) => {
  await page.goto("/glosario");
  expect(await page.locator("dt, h2, h3").count()).toBeGreaterThan(5);
});

test.describe("header search combobox", () => {
  test("type, arrow keys, Enter", async ({ page, isMobile }) => {
    await page.goto("/");
    if (isMobile) {
      await page.getByRole("button", { name: "Menú" }).click();
    }
    const input = page.getByRole("combobox").first();
    await input.click();
    await input.fill("ministerio");
    const list = page.getByRole("listbox", { name: "Sugerencias de búsqueda" }).first();
    await expect(list.getByRole("option").first()).toBeVisible();
    await expect(input).toHaveAttribute("aria-expanded", "true");
    await expect.poll(() => list.getByRole("option").count()).toBeGreaterThan(1);
    await input.press("ArrowDown");
    const id = await input.getAttribute("aria-activedescendant");
    expect(id).toBeTruthy();
    await expect(page.locator(`[id="${id}"]`)).toHaveAttribute("aria-selected", "true");
    await input.press("ArrowDown");
    expect(await input.getAttribute("aria-activedescendant")).not.toBe(id);
    await input.press("Enter");
    await expect(page).toHaveURL(/\/entidades\/\d{13}|\/procesos\?q=/);
  });
});

test.describe("glossary term popover", () => {
  test("hover, focus and Escape", async ({ page, isMobile }) => {
    await page.goto("/metodologia");
    const term = page.locator(".term__btn").first();
    const pop = page.locator(".term__pop").first();
    await term.scrollIntoViewIfNeeded();
    if (!isMobile) {
      await term.hover();
      await expect(pop).toHaveClass(/term__pop--open/);
      await expect(pop).toBeVisible();
      await page.mouse.move(0, 0);
      await expect(pop).not.toHaveClass(/term__pop--open/);
    }
    await term.focus();
    await expect(pop).toHaveClass(/term__pop--open/);
    await page.keyboard.press("Escape");
    await expect(pop).not.toHaveClass(/term__pop--open/);
    await expect(term).toBeFocused();
  });
});
