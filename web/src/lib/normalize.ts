import type { MethodMix, Position, ProcessContext, RegionStats, YearRow, YearStats } from "./types";

type Rec = Record<string, unknown>;
const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const first = (o: Rec, ...keys: string[]): unknown => {
  for (const k of keys) if (o[k] !== undefined && o[k] !== null) return o[k];
  return undefined;
};
/** The API reports percentages on a 0-100 scale. */
const frac = (v: number | null) => (v == null ? null : v / 100);

export function normalizeRegions(raw: unknown): RegionStats {
  if (!isRec(raw) || !Array.isArray(raw.items)) throw new Error("bad shape");
  return {
    items: raw.items.filter(isRec).map((r) => ({
      region: String(r.region),
      region_label: str(r.region_label) ?? String(r.region),
      competitive_processes: num(r.competitive_processes) ?? 0,
      with_signal: num(r.with_signal) ?? 0,
      pct_with_signal: num(r.pct_with_signal),
      single_bidder: num(r.single_bidder) ?? 0,
      pct_single_bidder: num(r.pct_single_bidder),
      mean_score: num(r.mean_score),
      processes_total: num(r.processes_total) ?? 0,
      awarded_total: num(r.awarded_total),
      small_sample: typeof r.small_sample === "boolean" ? r.small_sample : undefined,
    })),
    national: isRec(raw.national) ? (raw.national as RegionStats["national"]) : null,
    basis: str(raw.basis),
    notes: Array.isArray(raw.notes) ? raw.notes.filter((n): n is string => typeof n === "string") : [],
    data_built_at: str(raw.data_built_at),
  };
}

function mixOf(r: Rec): MethodMix {
  const src = first(r, "method_mix", "award_share", "share_by_method");
  const pick = (k: string) => {
    const v = isRec(src) ? num(src[k]) : num(first(r, `share_${k}`, `${k}_share`, `pct_${k}`, `awarded_${k}_share`));
    return frac(v);
  };
  return { competitive: pick("competitive"), direct: pick("direct"), catalogue: pick("catalogue"), other: pick("other") };
}

export function normalizeYears(raw: unknown): YearStats {
  const list = Array.isArray(raw) ? raw : isRec(raw) ? (first(raw, "items", "years") as unknown) : null;
  if (!Array.isArray(list)) throw new Error("bad shape");
  const rows: YearRow[] = list.filter(isRec).flatMap((r) => {
    const year = num(r.year);
    if (year == null) return [];
    return [
      {
        year,
        processes_total: num(r.processes_total),
        competitive_processes: num(r.competitive_processes),
        pct_single_bidder: frac(num(r.pct_single_bidder)),
        pct_with_signal: frac(num(r.pct_with_signal)),
        single_bidder_base: num(r.single_bidder_base),
        awarded_total: num(r.awarded_total),
        mix: mixOf(r),
        partial_year: r.partial_year === true,
      },
    ];
  });
  const notesRaw = isRec(raw) ? raw.notes : null;
  const notes: string[] = Array.isArray(notesRaw)
    ? notesRaw.flatMap((n) => (typeof n === "string" ? [n] : isRec(n) ? [str(first(n, "text", "note", "message", "note_es")) ?? ""].filter(Boolean) : []))
    : [];
  rows.sort((a, b) => a.year - b.year);
  return { items: rows, notes, data_built_at: isRec(raw) ? str(raw.data_built_at) : null };
}

function position(v: unknown): Position {
  if (!isRec(v)) return { value: null, percentile: null };
  return { value: num(v.value), percentile: frac(num(v.percentile)) };
}

function spread(v: unknown) {
  if (!isRec(v)) return null;
  const median = num(v.median);
  if (median == null) return null;
  return { median, q1: num(v.q1), q3: num(v.q3), position: position(v) };
}

/** Tolerant reading of `/processes/{ocid}/context`; any missing part becomes null. */
export function normalizeContext(raw: unknown): ProcessContext {
  if (!isRec(raw)) throw new Error("bad shape");
  const t = raw.tenderers;
  let tenderers: ProcessContext["tenderers"] = null;
  const dist: unknown[] = isRec(t) && Array.isArray(t.distribution) ? t.distribution : [];
  if (isRec(t) && dist.length) {
    const counts = ["1", "2", "3", "4", "5", "6+"].map((b) => {
      const row = dist.find((d): d is Rec => isRec(d) && d.bucket === b);
      return row ? (num(row.count) ?? 0) : 0;
    });
    if (counts.some((c) => c > 0)) tenderers = { counts, position: position(t) };
  }
  return {
    method: str(raw.method),
    year: num(raw.year),
    comparable: num(raw.comparable_processes),
    tenderers,
    ratio: spread(raw.award_budget_ratio),
    window: spread(raw.tender_window_days),
  };
}
