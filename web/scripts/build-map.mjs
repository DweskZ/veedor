#!/usr/bin/env node
/**
 * Authoring-time build of the province map used by /mapa and the home page.
 *
 *   node scripts/build-map.mjs [geo-src/geoBoundaries-ECU-ADM1.geojson]
 *
 * Input : geoBoundaries ECU ADM1 (CC0 1.0), downloaded once into web/geo-src/ (git-ignored).
 * Output: src/data/ecuador-provinces.json (committed): one SVG path string per province key plus a
 *         label anchor, the Galapagos inset frame and the attribution. No map library at runtime.
 *
 * The script fails (non-zero exit) unless exactly the 24 expected province keys are matched once each.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const input = resolve(process.argv[2] ?? resolve(here, "../geo-src/geoBoundaries-ECU-ADM1.geojson"));
const output = resolve(here, "../src/data/ecuador-provinces.json");

/** Geometry name -> canonical API key (the upper-case `buyer_region` of the data lake) and display name. */
const MAPPING = {
  "Azuay": ["AZUAY", "Azuay"],
  "Bolívar": ["BOLIVAR", "Bolívar"],
  "Carchi": ["CARCHI", "Carchi"],
  "Cañar": ["CAÑAR", "Cañar"],
  "Chimborazo": ["CHIMBORAZO", "Chimborazo"],
  "Cotopaxi": ["COTOPAXI", "Cotopaxi"],
  "El Oro": ["EL ORO", "El Oro"],
  "Esmeraldas": ["ESMERALDAS", "Esmeraldas"],
  "Galápagos": ["GALAPAGOS", "Galápagos"],
  "Guayas": ["GUAYAS", "Guayas"],
  "Imbabura": ["IMBABURA", "Imbabura"],
  "Loja": ["LOJA", "Loja"],
  "Los Ríos": ["LOS RIOS", "Los Ríos"],
  "Manabi": ["MANABI", "Manabí"],
  "Morona Santiago": ["MORONA SANTIAGO", "Morona Santiago"],
  "Napo": ["NAPO", "Napo"],
  "Orellana": ["ORELLANA", "Orellana"],
  "Pastaza": ["PASTAZA", "Pastaza"],
  "Pichincha": ["PICHINCHA", "Pichincha"],
  "Santa Elena": ["SANTA ELENA", "Santa Elena"],
  "Santo Domingo de los Tsáchilas": ["SANTO DOMINGO DE LOS TSACHILAS", "Santo Domingo de los Tsáchilas"],
  "Sucumbios": ["SUCUMBIOS", "Sucumbíos"],
  "Tungurahua": ["TUNGURAHUA", "Tungurahua"],
  "Zamora Chinchipe": ["ZAMORA CHINCHIPE", "Zamora Chinchipe"],
};
/** Short labels for the pills drawn on the map. */
const SHORT = { "SANTO DOMINGO DE LOS TSACHILAS": "Santo Domingo", "ZAMORA CHINCHIPE": "Zamora Ch.", "MORONA SANTIAGO": "Morona S." };
/** Manual label nudges in degrees (east, north) where two pills would collide. */
const NUDGE = {};

const SCALE = 100; // 1 degree = 100 SVG units
const TOLERANCE = 0.9; // Douglas-Peucker tolerance in SVG units (about 1 km)
const GALAPAGOS_SCALE = 0.55;

const geo = JSON.parse(readFileSync(input, "utf8"));
const byKey = new Map();
for (const f of geo.features) {
  const m = MAPPING[f.properties.shapeName];
  if (!m) throw new Error(`Unmapped geometry name: ${f.properties.shapeName}`);
  if (byKey.has(m[0])) throw new Error(`Duplicate key ${m[0]}`);
  byKey.set(m[0], { name: m[1], geometry: f.geometry });
}
const expected = Object.values(MAPPING).map((m) => m[0]);
const missing = expected.filter((k) => !byKey.has(k));
if (byKey.size !== 24 || missing.length) throw new Error(`Expected 24 provinces, matched ${byKey.size}; missing: ${missing.join(", ")}`);

const polygons = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates);

// Mainland bounding box (degrees) decides the origin; Galapagos is drawn apart in an inset.
let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
for (const [key, p] of byKey) {
  if (key === "GALAPAGOS") continue;
  for (const poly of polygons(p.geometry)) for (const [x, y] of poly[0]) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
}
const g = byKey.get("GALAPAGOS");
let gx0 = Infinity, gx1 = -Infinity, gy0 = Infinity, gy1 = -Infinity;
for (const poly of polygons(g.geometry)) for (const [x, y] of poly[0]) {
  gx0 = Math.min(gx0, x); gx1 = Math.max(gx1, x); gy0 = Math.min(gy0, y); gy1 = Math.max(gy1, y);
}

const PAD = 6;
const insetW = (gx1 - gx0) * SCALE * GALAPAGOS_SCALE + 24;
const insetH = (gy1 - gy0) * SCALE * GALAPAGOS_SCALE + 40;
const mainW = (maxX - minX) * SCALE;
const mainH = (maxY - minY) * SCALE;
const OFFSET_X = Math.round(insetW * 0.62) + PAD; // widen the canvas on the left for the inset
const W = Math.round(mainW + OFFSET_X + PAD);
const H = Math.round(mainH + 2 * PAD);

const project = (lon, lat) => [(lon - minX) * SCALE + OFFSET_X, (maxY - lat) * SCALE + PAD];
const projectGal = (lon, lat) => {
  const ix = PAD + 12;
  const iy = H - PAD - insetH + 26;
  return [ix + (lon - gx0) * SCALE * GALAPAGOS_SCALE, iy + (gy1 - lat) * SCALE * GALAPAGOS_SCALE];
};

function dp(points, tol) {
  if (points.length < 3) return points;
  const keep = new Uint8Array(points.length);
  keep[0] = keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop();
    let max = 0, idx = -1;
    const [ax, ay] = points[a], [bx, by] = points[b];
    const dx = bx - ax, dy = by - ay, len = Math.hypot(dx, dy) || 1e-9;
    for (let i = a + 1; i < b; i++) {
      const d = Math.abs(dy * points[i][0] - dx * points[i][1] + bx * ay - by * ax) / len;
      if (d > max) { max = d; idx = i; }
    }
    if (max > tol && idx > 0) { keep[idx] = 1; stack.push([a, idx], [idx, b]); }
  }
  return points.filter((_, i) => keep[i]);
}

const area = (ring) => {
  let s = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) s += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
  return Math.abs(s / 2);
};

function toPath(poly, proj, minArea) {
  const out = [];
  for (const ring of poly) {
    const pts = ring.map(([x, y]) => proj(x, y));
    if (area(pts) < minArea) continue;
    const s = dp(pts.slice(0, -1), TOLERANCE);
    if (s.length < 3) continue;
    out.push("M" + s.map(([x, y]) => `${+x.toFixed(1)} ${+y.toFixed(1)}`).join("L") + "Z");
  }
  return out.join("");
}

function inside(pt, rings) {
  let c = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) c = !c;
    }
  }
  return c;
}
function edgeDist(pt, rings) {
  let best = Infinity;
  for (const ring of rings) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [ax, ay] = ring[j], [bx, by] = ring[i];
    const dx = bx - ax, dy = by - ay;
    const t = Math.max(0, Math.min(1, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / (dx * dx + dy * dy || 1)));
    best = Math.min(best, Math.hypot(pt[0] - (ax + t * dx), pt[1] - (ay + t * dy)));
  }
  return best;
}
/** Visual centre: the grid point inside the largest polygon that is farthest from its edge. */
function anchor(rings) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const [x, y] of rings[0]) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
  let best = [(x0 + x1) / 2, (y0 + y1) / 2], bd = -1;
  const n = 40;
  for (let i = 1; i < n; i++) for (let j = 1; j < n; j++) {
    const p = [x0 + ((x1 - x0) * i) / n, y0 + ((y1 - y0) * j) / n];
    if (!inside(p, rings)) continue;
    const d = edgeDist(p, rings);
    if (d > bd) { bd = d; best = p; }
  }
  return best;
}

const provinces = {};
for (const [key, p] of [...byKey].sort((a, b) => a[0].localeCompare(b[0], "es"))) {
  const isGal = key === "GALAPAGOS";
  const proj = isGal ? projectGal : project;
  const polys = polygons(p.geometry);
  const minArea = isGal ? 2.5 : 0;
  const d = polys.map((poly) => toPath(poly, proj, minArea)).join("");
  if (!d) throw new Error(`Empty path for ${key}`);
  const largest = polys
    .map((poly) => poly.map((r) => r.map(([x, y]) => proj(x, y))))
    .sort((a, b) => area(b[0]) - area(a[0]))[0];
  let [lx, ly] = anchor(largest);
  const nudge = NUDGE[key];
  if (nudge) { lx += nudge[0] * SCALE; ly -= nudge[1] * SCALE; }
  provinces[key] = { name: p.name, short: SHORT[key] ?? p.name, d, lx: +lx.toFixed(1), ly: +ly.toFixed(1), inset: isGal || undefined };
}

const result = {
  note: "Generated by scripts/build-map.mjs. Do not edit by hand.",
  source: {
    name: "geoBoundaries gbOpen, Ecuador ADM1 (provincias)",
    url: "https://github.com/wmgeolab/geoBoundaries/tree/main/releaseData/gbOpen/ECU/ADM1",
    licence: "CC0 1.0 (dominio público)",
    boundaryYear: "2011",
    retrieved: new Date().toISOString().slice(0, 10),
  },
  viewBox: [W, H],
  inset: { x: PAD, y: +(H - PAD - insetH).toFixed(1), w: +(insetW).toFixed(1), h: +insetH.toFixed(1), label: "Galápagos" },
  provinces,
};
const text = JSON.stringify(result);
writeFileSync(output, text + "\n");
console.log(`ok: ${Object.keys(provinces).length} provinces, viewBox ${W}x${H}, ${(text.length / 1024).toFixed(1)} KB -> ${output}`);
