import type { Page } from "@playwright/test";
import { allPages, expect, randomOcid, test } from "./fixtures";

interface Stop {
  name: string;
  tag: string;
  top: number;
  left: number;
  visible: boolean;
  focusStyle: boolean;
  tabindex: number;
  /** Fixed-position or popover content: placed by design away from its place in the reading order. */
  floating: boolean;
}

/** Tabs through the page and records each stop until focus leaves the document or cycles. */
async function tabThrough(page: Page, browserName: string, max = 500): Promise<Stop[]> {
  // Safari (and WebKit) only tab to form controls by default; Option+Tab reaches every focusable element.
  const key = browserName === "webkit" ? "Alt+Tab" : "Tab";
  await page.evaluate(() => {
    (document.activeElement as HTMLElement | null)?.blur();
    window.scrollTo(0, 0);
  });
  const stops: Stop[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < max; i++) {
    await page.keyboard.press(key);
    const s = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      const ring = (c: CSSStyleDeclaration) => c.boxShadow !== "none" || (c.outlineStyle !== "none" && parseFloat(c.outlineWidth) > 0);
      // Wrapped controls (a visually hidden radio inside a styled label) show focus on the wrapper.
      const wrap = el.closest("label, .seg__opt");
      return {
        name: (el.getAttribute("aria-label") || el.textContent || (el as HTMLInputElement).placeholder || el.tagName).trim().replace(/\s+/g, " ").slice(0, 60),
        tag: el.tagName.toLowerCase(),
        top: r.top + window.scrollY,
        left: r.left + window.scrollX,
        visible: r.width > 0 && r.height > 0,
        // The map draws its focus ring as an extra SVG path around the province instead of an outline on the link.
        focusStyle: ring(cs) || (!!wrap && ring(getComputedStyle(wrap))) || (!!el.closest(".map__stage") && !!document.querySelector(".map__ring--o")),
        tabindex: el.tabIndex,
        floating: !!el.closest(".term__pop") || getComputedStyle(el.closest("[class]") ?? el).position === "fixed" || cs.position === "fixed" || !!Array.from(document.querySelectorAll("*")).find((a) => a.contains(el) && getComputedStyle(a).position === "fixed"),
      };
    });
    if (!s) break;
    const sig = `${s.tag}|${s.name}|${Math.round(s.top)}|${Math.round(s.left)}`;
    if (seen.has(sig)) break;
    seen.add(sig);
    stops.push(s);
  }
  return stops;
}

async function assertKeyboardPass(page: Page, browserName: string, label: string) {
  const stops = await tabThrough(page, browserName);
  expect(stops.length, `${label}: tab stops`).toBeGreaterThan(5);

  // Every focusable element on the page is a stop (roving-tabindex widgets expose one stop for the group).
  const missing = await page.evaluate((names) => {
    const all = Array.from(document.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex='0']"));
    return all
      .filter((e) => {
        const r = e.getBoundingClientRect();
        const cs = getComputedStyle(e);
        return e.tabIndex >= 0 && cs.visibility !== "hidden" && cs.display !== "none" && !e.closest("[hidden],[inert]") && !(e.closest("details:not([open])") && e.tagName !== "SUMMARY") && !(e.tagName === "SUMMARY" && e.parentElement?.closest("details:not([open])")) && (r.width > 0 || r.height > 0);
      })
      .map((e) => (e.getAttribute("aria-label") || e.textContent || (e as HTMLInputElement).placeholder || e.tagName).trim().replace(/\s+/g, " ").slice(0, 60))
      .filter((n) => !names.includes(n));
  }, stops.map((s) => s.name));
  expect(missing, `${label}: focusable elements never reached by Tab`).toEqual([]);

  expect(stops.filter((s) => s.tabindex > 0).map((s) => s.name), `${label}: positive tabindex`).toEqual([]);
  expect(stops.filter((s) => !s.visible).map((s) => s.name), `${label}: focus lands on an invisible element`).toEqual([]);
  expect(stops.filter((s) => !s.focusStyle).map((s) => `${s.tag}:${s.name}`), `${label}: stops without a visible focus style`).toEqual([]);

  // Reading order: focus moves down the document; allow a small tolerance for items on one row.
  const flow = stops.filter((s) => !s.floating);
  // Moving up is fine only when it moves to a column on the right (side-by-side cards are read column by column).
  const back = flow.flatMap((s, i) => (i > 0 && s.top < flow[i - 1].top - 40 && s.left < flow[i - 1].left + 150 ? [`${flow[i - 1].name} -> ${s.name}`] : []));
  expect(back, `${label}: focus jumps upwards`).toEqual([]);
}

test("keyboard pass: home", async ({ page, browserName, isMobile }) => {
  test.skip(isMobile, "no hardware keyboard on the mobile viewport");
  await page.goto("/", { waitUntil: "networkidle" });
  await assertKeyboardPass(page, browserName, `home (${browserName})`);
});

test("keyboard pass: process page", async ({ page, browserName, isMobile }) => {
  test.skip(isMobile, "no hardware keyboard on the mobile viewport");
  await page.goto(`/procesos/${encodeURIComponent(await randomOcid(page))}`, { waitUntil: "networkidle" });
  await assertKeyboardPass(page, browserName, `process (${browserName})`);
});

test.describe("prefers-reduced-motion", () => {
  test.use({ reducedMotion: "reduce" });
  test("no animation or transition longer than a blink on any page", async ({ page }) => {
    for (const p of await allPages(page)) {
      await page.goto(p.path, { waitUntil: "networkidle" });
      await page.evaluate(() => window.scrollBy(0, 600));
      const offenders = await page.evaluate(() => {
        const ms = (v: string) => v.split(",").map((x) => (x.trim().endsWith("ms") ? parseFloat(x) : parseFloat(x) * 1000));
        const bad: string[] = [];
        const targets: [HTMLElement, string | null][] = [];
        for (const el of document.querySelectorAll<HTMLElement>("body, body *")) targets.push([el, null], [el, "::before"], [el, "::after"]);
        for (const [el, pseudo] of targets) {
          const cs = getComputedStyle(el, pseudo);
          const anim = cs.animationName !== "none" && ms(cs.animationDuration).some((d) => d > 1) && cs.animationIterationCount !== "1";
          const animOnce = cs.animationName !== "none" && ms(cs.animationDuration).some((d) => d > 50);
          // Colour fades are not vestibular motion; movement and size changes are.
          const tr = cs.transitionProperty.split(",").some((prop, i) => /transform|translate|top|left|right|bottom|margin|width|height|all|scale|rotate/.test(prop) && ms(cs.transitionDuration)[i % ms(cs.transitionDuration).length] > 50);
          if (anim || animOnce || tr) bad.push(`${el.tagName.toLowerCase()}${pseudo ?? ""}.${(el.className?.toString() ?? "").split(" ")[0]} anim=${cs.animationName}/${cs.animationDuration} tr=${cs.transitionDuration}`);
        }
        return Array.from(new Set(bad)).slice(0, 15);
      });
      expect(offenders, `${p.name}: motion under prefers-reduced-motion`).toEqual([]);
      expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior), `${p.name} scroll-behavior`).not.toBe("smooth");
    }
  });
});
