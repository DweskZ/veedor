import type { RegionRow } from "./types";

export type Metric = "signal" | "single";

export const METRICS: Record<Metric, { label: string; short: string; question: string }> = {
  signal: {
    label: "Con al menos una señal",
    short: "con al menos una señal",
    question: "de los procesos competitivos tuvo al menos una señal",
  },
  single: {
    label: "Con un solo oferente",
    short: "con un solo oferente",
    question: "de los procesos competitivos tuvo un solo oferente",
  },
};

/** A share as a fraction. Uses the API percentage (accepting 0-1 or 0-100) checked against the counts it comes from. */
export function toFraction(pct: number | null | undefined, num: number | null | undefined, den: number | null | undefined): number | null {
  const counted = num != null && den ? num / den : null;
  if (pct == null) return counted;
  if (counted == null) return pct > 1 ? pct / 100 : pct;
  return Math.abs(pct - counted) <= Math.abs(pct / 100 - counted) ? pct : pct / 100;
}

export const fractionOf = (r: Partial<RegionRow>, m: Metric): number | null =>
  m === "signal"
    ? toFraction(r.pct_with_signal, r.with_signal, r.competitive_processes)
    : toFraction(r.pct_single_bidder, r.single_bidder, r.competitive_processes);

export const countOf = (r: Partial<RegionRow>, m: Metric) => (m === "signal" ? r.with_signal : r.single_bidder);

export const SMALL_SAMPLE_MIN = 500;
export const isSmall = (r: RegionRow) => r.small_sample ?? r.competitive_processes < SMALL_SAMPLE_MIN;

export interface ClassScale {
  /** Lower bound of classes 1 to n-1 (class 0 is everything below the first). */
  cuts: number[];
  classOf: (v: number) => number;
  /** Observed min and max per class, null when empty. */
  ranges: ({ min: number; max: number; count: number } | null)[];
}

/** Quintiles: five classes with (as nearly as ties allow) the same number of provinces. */
export function quantileClasses(values: number[], n = 5): ClassScale {
  const v = [...values].sort((a, b) => a - b);
  const cuts: number[] = [];
  for (let i = 1; i < n; i++) cuts.push(v[Math.min(v.length - 1, Math.round((i * v.length) / n))] ?? 0);
  const classOf = (x: number) => cuts.filter((c) => x >= c).length;
  const ranges: ClassScale["ranges"] = Array.from({ length: n }, () => null);
  for (const x of v) {
    const k = classOf(x);
    const r = ranges[k];
    ranges[k] = r ? { min: Math.min(r.min, x), max: Math.max(r.max, x), count: r.count + 1 } : { min: x, max: x, count: 1 };
  }
  return { cuts, classOf, ranges };
}

/** Fills: ice-to-ink sequential, terracotta only for the top class (which also gets a hatch). */
export const CLASS_FILL = ["#ffffff", "#cadbfb", "#8fa6db", "#1a1f36", "#d9480f"];
export const CLASS_NAME = ["Más bajo", "Bajo", "Medio", "Alto", "Más alto"];
