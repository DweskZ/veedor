import { API, expect, randomOcid, test } from "./fixtures";
import type { Page } from "@playwright/test";

const CORS = { "access-control-allow-origin": "*", "access-control-expose-headers": "Retry-After" };

const answer = (ocid: string, over: Record<string, unknown> = {}) => ({
  ocid,
  answerable: true,
  mode: "retrieval",
  reason: "answered",
  sentences: [{ text: "Hubo 2 oferentes.", fact_id: "process.tenderers", source_id: "sercop_ocds", source_field: "tender.numberOfTenderers" }],
  quotes: [],
  note_es: null,
  ...over,
});

/** Opens the question tab of a process, with the ask endpoint answered by `handler` (questions are never sent to the real API). */
async function openAsk(page: Page, handler: (question: string, ocid: string) => { status: number; headers?: Record<string, string>; body: unknown }) {
  const meta = await (await page.request.get(`${API}/meta`)).json();
  test.skip(meta.ask_enabled !== true, "the API has the question box turned off");
  const ocid = await randomOcid(page);
  const asked: string[] = [];
  await page.route(`${API}/processes/*/ask`, async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: { ...CORS, "access-control-allow-headers": "content-type", "access-control-allow-methods": "POST" } });
    const question = (route.request().postDataJSON() as { question: string }).question;
    asked.push(question);
    const r = handler(question, ocid);
    await route.fulfill({ status: r.status, headers: { ...CORS, ...(r.headers ?? {}) }, contentType: "application/json", body: JSON.stringify(r.body) });
  });
  await page.goto(`/procesos/${encodeURIComponent(ocid)}#preguntar`, { waitUntil: "networkidle" });
  await expect(page.getByRole("tab", { name: "Preguntar" })).toHaveAttribute("aria-selected", "true");
  return { ocid, asked, meta: meta as { ask_mode?: string } };
}

test.describe("question box", () => {
  // The mocked 429 and 500 answers are expected: keep them out of the health fixture's list of failures
  // (afterEach runs before the fixture checks that list).
  test.afterEach(({ health }) => {
    const mocked = (m: string) => /\/ask$/.test(m) || /status of (429|500)/.test(m);
    health.splice(0, health.length, ...health.filter((h) => !mocked(h)));
  });

  test("the notice follows the API's ask_mode (external provider only when it is not retrieval)", async ({ page }) => {
    const { meta } = await openAsk(page, (_q, ocid) => ({ status: 200, body: answer(ocid) }));
    const notice = page.locator(".ask__disc");
    await expect(notice).toBeVisible();
    if (meta.ask_mode === "retrieval") {
      await expect(notice).toContainText("búsqueda dentro de Veedor, sin modelo de lenguaje");
      await expect(notice).not.toContainText("proveedor externo");
    } else {
      // "model" and any missing or unknown value show the cautious text.
      await expect(notice).toContainText("proveedor externo de modelos de lenguaje");
    }
  });

  test("a suggestion chip submits, focus moves to the answer and a live region announces it", async ({ page }) => {
    const { asked } = await openAsk(page, (_q, ocid) => ({ status: 200, body: answer(ocid) }));
    await page.locator(".ask__chips .ask__chip").first().click();
    const heading = page.getByRole("heading", { name: "Respuesta", exact: true });
    await expect(heading).toBeFocused();
    await expect(page.getByText("Hubo 2 oferentes.")).toBeVisible();
    await expect(page.locator(".ask > [role=status]")).toContainText("Respuesta lista");
    expect(asked).toHaveLength(1);
  });

  test("an unanswerable question shows examples that can be clicked", async ({ page }) => {
    const { asked } = await openAsk(page, (q, ocid) => ({ status: 200, body: q === "fuera de alcance" ? answer(ocid, { answerable: false, sentences: [] }) : answer(ocid) }));
    await page.getByLabel("Tu pregunta").fill("fuera de alcance");
    await page.getByRole("button", { name: "Preguntar" }).click();
    await expect(page.getByRole("heading", { name: "Esto no está en los datos de este proceso" })).toBeFocused();
    await page.locator(".ask__can-now .ask__chip").first().click();
    await expect(page.getByText("Hubo 2 oferentes.")).toBeVisible();
    expect(asked).toHaveLength(2);
  });

  test("a 429 with Retry-After shows the wait and re-enables the button afterwards", async ({ page }) => {
    let first = true;
    await openAsk(page, (_q, ocid) => {
      if (first) {
        first = false;
        return { status: 429, headers: { "retry-after": "3" }, body: { error: { message: "limit" } } };
      }
      return { status: 200, body: answer(ocid) };
    });
    await page.getByLabel("Tu pregunta").fill("¿Quién ganó?");
    const send = page.locator(".ask__form button[type=submit]");
    await send.click();
    await expect(page.getByRole("heading", { name: "Hiciste muchas preguntas seguidas" })).toBeFocused();
    await expect(page.locator(".ask__ans")).toContainText(/en \d+ segundos?/);
    await expect(send).toBeDisabled();
    await expect(send).toContainText("Espera");
    await expect(send).toBeEnabled({ timeout: 8000 });
    await expect(send).toHaveText("Preguntar");
    await send.click();
    await expect(page.getByText("Hubo 2 oferentes.")).toBeVisible();
  });

  test("the last pairs of the session stay on the page, in memory only", async ({ page }) => {
    await openAsk(page, (_q, ocid) => ({ status: 200, body: answer(ocid) }));
    for (const q of ["primera pregunta", "segunda pregunta"]) {
      await page.getByLabel("Tu pregunta").fill(q);
      await page.getByRole("button", { name: "Preguntar" }).click();
      await expect(page.getByRole("heading", { name: "Respuesta", exact: true })).toBeFocused();
    }
    await expect(page.locator(".ask__old summary", { hasText: "primera pregunta" })).toBeVisible();
    const stored = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]));
    expect(stored).not.toContain("pregunta");
  });

  test("a failing service explains itself and offers a retry", async ({ page }) => {
    await openAsk(page, () => ({ status: 500, body: {} }));
    await page.getByLabel("Tu pregunta").fill("¿Quién compró?");
    await page.getByRole("button", { name: "Preguntar" }).click();
    await expect(page.getByRole("heading", { name: "No pudimos responder ahora" })).toBeFocused();
    await expect(page.getByRole("button", { name: "Intentar de nuevo" })).toBeVisible();
  });
});
