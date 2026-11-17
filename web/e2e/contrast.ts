import type { Page } from "@playwright/test";

export interface ContrastRow {
  page: string;
  text: string;
  fg: string;
  bg: string;
  ratio: number;
  size: number;
  weight: number;
  need: number;
  selector: string;
}

/**
 * Contrast for text axe reports as "needs review" (SVG text over shapes, selects with a background image,
 * text over overlapping elements). For each text element it finds the colour actually painted behind the
 * text's centre point (elementsFromPoint: the first element with an opaque fill or background colour) and
 * applies the WCAG relative-luminance formula, with the 3:1 threshold for large text.
 */
export async function measureContrast(page: Page, name: string): Promise<{ fails: ContrastRow[]; lowest: { ratio: number; text: string } }> {
  const res = await page.evaluate((pageName) => {
    const parse = (c: string): [number, number, number, number] | null => {
      const m = c.match(/rgba?\(([^)]+)\)/);
      if (!m) return null;
      const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const lum = ([r, g, b]: number[]) => {
      const f = (v: number) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const over = (top: number[], bottom: number[]) => {
      const a = top[3] ?? 1;
      return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a));
    };
    const paint = (el: Element): number[] | null => {
      const cs = getComputedStyle(el);
      if (el instanceof SVGElement && !(el instanceof SVGSVGElement)) {
        const f = parse(cs.fill);
        if (!f) return null; // pattern or none
        return [f[0], f[1], f[2], f[3] * parseFloat(cs.fillOpacity) * parseFloat(cs.opacity)];
      }
      const b = parse(cs.backgroundColor);
      return b && b[3] > 0 ? b : null;
    };
    // Hit-testing must see every element, including labels that opt out of pointer events.
    const style = document.createElement("style");
    style.textContent = "* { pointer-events: auto !important; }";
    document.head.append(style);
    const out: Record<string, unknown>[] = [];
    let lowest = { ratio: 21, text: "" };
    const seen = new Set<string>();
    const candidates = document.querySelectorAll<HTMLElement | SVGElement>("svg text, select, .control, input, button");
    for (const el of candidates) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (el instanceof HTMLInputElement && /radio|checkbox|hidden/.test(el.type)) continue;
      if (!(el.textContent || (el as HTMLInputElement).placeholder || (el as HTMLInputElement).value)) continue;
      const cs = getComputedStyle(el);
      const isSvg = el instanceof SVGElement;
      const fgRaw = parse(isSvg ? cs.fill : cs.color);
      if (!fgRaw) continue;
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) {
        // off screen: scroll it in so elementsFromPoint sees it
        el.scrollIntoView({ block: "center", behavior: "instant" as ScrollBehavior });
      }
      const r2 = el.getBoundingClientRect();
      const stack = document.elementsFromPoint(r2.left + r2.width / 2, r2.top + r2.height / 2);
      // layers above the text are ignored; start at the first layer below it
      // An HTML control paints its own background; SVG text's own paint is the text colour itself.
      // (the hit element of multi-line SVG text can be one of its tspans, so use the last element inside the text.)
      let inside = -1;
      stack.forEach((e, i) => {
        if (el.contains(e)) inside = i;
      });
      const start = isSvg ? inside : stack.indexOf(el) - 1;
      let bg: number[] | null = null;
      const layers: number[][] = [];
      for (const e of stack.slice(start + 1)) {
        const p = paint(e);
        if (!p) continue;
        layers.push(p);
        if (p[3] >= 0.999) break;
      }
      let base = [255, 255, 255];
      for (const p of layers.reverse()) base = over(p, base);
      bg = base;
      const fgOpacity = isSvg ? parseFloat(cs.fillOpacity) * parseFloat(cs.opacity) : parseFloat(cs.opacity);
      const fg = over([fgRaw[0], fgRaw[1], fgRaw[2], fgRaw[3] * fgOpacity], bg);
      const l1 = lum(fg), l2 = lum(bg);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      const size = parseFloat(cs.fontSize) * (isSvg ? (el.ownerSVGElement ? r2.height / (el as SVGGraphicsElement).getBBox().height : 1) : 1);
      const weight = Number(cs.fontWeight);
      const large = size >= 24 || (size >= 18.66 && weight >= 700);
      const need = large ? 3 : 4.5;
      if (ratio < lowest.ratio) lowest = { ratio: Math.round(ratio * 100) / 100, text: (el.textContent || "").trim().slice(0, 30) };
      const key = `${fg.map(Math.round)}|${bg.map(Math.round)}|${Math.round(size)}|${weight}`;
      if (ratio < need && !seen.has(key)) {
        seen.add(key);
        out.push({
          page: pageName,
          text: (el.textContent || (el as HTMLInputElement).placeholder || el.tagName).trim().slice(0, 40),
          fg: `rgb(${fg.map(Math.round)})`,
          bg: `rgb(${bg.map(Math.round)})`,
          ratio: Math.round(ratio * 100) / 100,
          size: Math.round(size * 10) / 10,
          weight,
          need,
          selector: el.tagName.toLowerCase() + (el.getAttribute("class") ? "." + el.getAttribute("class")!.split(" ")[0] : ""),
        });
      }
    }
    style.remove();
    return { fails: out, lowest };
  }, name);
  return res as unknown as { fails: ContrastRow[]; lowest: { ratio: number; text: string } };
}
