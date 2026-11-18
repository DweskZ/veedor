import type { Metadata } from "next";
import { PageShell } from "@/components/PageFrame";
import Link from "next/link";
import { getProcesses, getRegions, getSignals, getStats } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import type { ProcessQuery, SignalDef } from "@/lib/types";
import { ProcessTable } from "@/components/ProcessTable";
import { ExplorerShell, type ActiveFilter, type QuickChip } from "@/components/ExplorerShell";
import { Term } from "@/components/Term";
import { EmptyState, ErrorState, PageHeader, RiskLegend } from "@/components/ui";

export const metadata: Metadata = { title: "Procesos" };

// Method names as they appear in the contract's data description.
const METHODS = ["Subasta Inversa Electrónica", "Menor Cuantía", "Cotización", "Licitación"];
const PAGE_SIZE = 25;
const KEYS = ["year", "method", "signal", "region", "min_score", "min_amount", "max_amount", "q", "sort", "page"] as const;

const QUICK: { id: string; label: string; signal: string; hint?: string }[] = [
  {
    id: "single",
    label: "Con la señal «oferente único»",
    signal: "SINGLE_BIDDER",
    hint: "Procesos competitivos con una sola oferta en que se activó la señal; excluye los procedimientos donde un solo oferente es normal por diseño.",
  },
  { id: "new", label: "Proveedor nuevo", signal: "NEW_SUPPLIER" },
  { id: "repeat", label: "Compras repetidas", signal: "REPEATED_DIRECT_AWARDS" },
];

function pick(sp: Record<string, string | string[] | undefined>): ProcessQuery {
  const out: Record<string, string> = {};
  for (const k of KEYS) {
    const v = sp[k];
    const s = Array.isArray(v) ? v[0] : v;
    // Surrounding whitespace is never part of a search; a blank value is no filter (the API rejects a blank `q`).
    const value = k === "q" ? s?.trim() : s;
    if (value) out[k] = value;
  }
  return out;
}

function href(q: ProcessQuery, patch: Partial<ProcessQuery>): string {
  const merged = { ...q, ...patch };
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(merged)) if (v) sp.set(k, v);
  const s = sp.toString();
  return s ? `/procesos?${s}` : "/procesos";
}

const SORTS: [string, string][] = [
  ["-risk_score", "Mayor puntaje primero"],
  ["risk_score", "Menor puntaje primero"],
  ["-award_total", "Mayor monto primero"],
  ["award_total", "Menor monto primero"],
];

export default function ProcesosPage({ searchParams }: PageProps<"/procesos">) {
  return (
    <Explorer searchParams={searchParams} />
  );
}

function ExplorerPage({ children }: { children: React.ReactNode }) {
  return (
    <PageShell>
      <PageHeader
        compact
        eyebrow="Explorador"
        title={
          <>
            Todos los <em>procesos.</em>
          </>
        }
        lead={
          <>
            Cada fila es una compra del Estado con su <Term t="puntaje">puntaje</Term> de riesgo. La dirección de la página guarda tus filtros.
          </>
        }
      />
      <div className="wrap">
        {children}
        <div className="page-end" />
      </div>
    </PageShell>
  );
}

async function Explorer({ searchParams }: { searchParams: PageProps<"/procesos">["searchParams"] }) {
  const raw = pick(await searchParams);
  const [sigRes, statRes, regRes] = await Promise.allSettled([getSignals(), getStats(), getRegions()]);
  const signals: SignalDef[] = sigRes.status === "fulfilled" ? sigRes.value : [];
  const regionList = regRes.status === "fulfilled" ? regRes.value.items.filter((r) => r.region !== "SIN_REGION") : [];
  // An unknown province key would be a 422 from the API: ignore it when the list of provinces is known.
  const q: ProcessQuery = { ...raw };
  if (q.region && regionList.length && !regionList.some((r) => r.region === q.region)) delete q.region;
  const last = statRes.status === "fulfilled" ? statRes.value.last_year ?? 2026 : 2026;
  const firstY = statRes.status === "fulfilled" ? statRes.value.first_year ?? 2015 : 2015;
  const years = Array.from({ length: Math.max(1, last - firstY + 1) }, (_, i) => String(last - i));
  const sort = q.sort || "-risk_score";

  // Each text search (`q`) scans the lake and counts against the visitor's search limit. One page render must cost one
  // search, not a handful: while a search is active the count badges (three signal chips, "more than USD 1 million") are
  // not computed and the chips show no count. Without `q` the counts are ordinary filtered reads and stay.
  const searching = Boolean(q.q);
  const counts = await Promise.all(
    QUICK.map((c) =>
      searching
        ? Promise.resolve(null)
        : getProcesses({ ...q, signal: c.signal, page: undefined, page_size: "1" }).then(
            (r) => r.total,
            () => null,
          ),
    ),
  );
  const chips: QuickChip[] = QUICK.map((c, i) => {
    const on = q.signal === c.signal;
    return { id: c.id, label: c.label, hint: c.hint, on, count: counts[i], href: href(q, { signal: on ? undefined : c.signal, page: undefined }) };
  });

  const regionLabel = (k: string) => regionList.find((r) => r.region === k)?.region_label ?? k;
  const active: ActiveFilter[] = [];
  const add = (key: keyof ProcessQuery, text: string | undefined) => {
    if (q[key] && text) active.push({ id: key, text, removeHref: href(q, { [key]: undefined, page: undefined }) });
  };
  add("year", `Año: ${q.year}`);
  add("method", `Método: ${q.method}`);
  add("region", `Provincia: ${q.region ? regionLabel(q.region) : ""}`);
  add("signal", `Señal: ${signals.find((s) => s.code === q.signal)?.label_es ?? q.signal}`);
  add("min_score", `Puntaje desde ${q.min_score}`);
  if (q.min_amount) add("min_amount", `Monto desde USD ${fmtInt(Number(q.min_amount))}`);
  if (q.max_amount) add("max_amount", `Monto hasta USD ${fmtInt(Number(q.max_amount))}`);
  add("q", `Búsqueda: «${q.q}»`);

  const millionOn = q.min_amount === "1000000";
  chips.push({
    id: "million",
    label: "Más de USD 1 millón",
    on: millionOn,
    count: searching ? null : await millionCount(q),
    href: href(q, { min_amount: millionOn ? undefined : "1000000", page: undefined }),
  });
  const bigOn = sort === "-award_total";
  chips.push({ id: "big", label: "Montos más altos primero", on: bigOn, count: null, href: href(q, { sort: bigOn ? undefined : "-award_total", page: undefined }) });

  // Loaded before rendering (see PageFrame): a list still pending while the page is sent would arrive after the footer.
  const results = await Results({ q, signals, regionLabel });

  return (
    <ExplorerPage>
    <ExplorerShell
      values={{ year: q.year ?? "", method: q.method ?? "", signal: q.signal ?? "", region: q.region ?? "", min_score: q.min_score ?? "", min_amount: q.min_amount ?? "", max_amount: q.max_amount ?? "", q: q.q ?? "", sort: SORTS.some(([v]) => v === sort) ? sort : "-risk_score" }}
      years={years.map((y) => ({ value: y, label: y }))}
      methods={METHODS.map((m) => ({ value: m, label: m }))}
      signals={signals.map((s) => ({ value: s.code, label: s.label_es }))}
      regions={regionList.map((r) => ({ value: r.region, label: r.region_label }))}
      sorts={SORTS.map(([value, label]) => ({ value, label }))}
      chips={chips}
      active={active}
      clearHref="/procesos"
    >
      {results}
    </ExplorerShell>
    </ExplorerPage>
  );
}

/**
 * Processes above USD 1 million within the current filters. If the API ignores `min_amount` (an older build), the filtered total
 * equals the unfiltered one: then no count is shown rather than a wrong one.
 */
async function millionCount(q: ProcessQuery): Promise<number | null> {
  const [withMin, without] = await Promise.all([
    getProcesses({ ...q, min_amount: "1000000", page: undefined, page_size: "1" }).then((r) => r.total, () => null),
    getProcesses({ ...q, min_amount: undefined, page: undefined, page_size: "1" }).then((r) => r.total, () => null),
  ]);
  return withMin != null && without != null && withMin < without ? withMin : null;
}

const FILTER_NAMES: Record<string, string> = { year: "el año", method: "el método", region: "la provincia", signal: "el tipo de señal", min_score: "el puntaje mínimo", min_amount: "el monto mínimo", max_amount: "el monto máximo", q: "la búsqueda" };

async function Results({ q, signals, regionLabel }: { q: ProcessQuery; signals: SignalDef[]; regionLabel: (k: string) => string }) {
  const res = await getProcesses({ ...q, page_size: String(PAGE_SIZE) }).then(
    (v) => ({ ok: true as const, v }),
    (e: unknown) => ({ ok: false as const, e }),
  );
  const labels = Object.fromEntries(signals.map((s) => [s.code, s.label_es]));
  const context = signals.filter((s) => s.kind === "context").map((s) => s.code);
  const sort = q.sort || "-risk_score";
  const hasFilters = Boolean(q.year || q.method || q.signal || q.min_score || q.min_amount || q.max_amount || q.q || q.region);
  if (!res.ok) return <ErrorState detail={res.e instanceof Error ? res.e.message : undefined} />;
  const page = res.v;

  if (page.items.length === 0) {
    // Which single filter, once removed, brings results back? Ask the API for each.
    // While a text search is active only the search itself is probed (a probe without `q`, which is not a search): probing
    // the other filters would repeat the search once per filter and each repetition counts against the search limit.
    const candidates = q.q ? (["q"] as const) : (["year", "method", "region", "signal", "min_score", "min_amount", "max_amount"] as const);
    const keys = candidates.filter((k) => q[k]);
    const probes = await Promise.all(
      keys.map((k) =>
        getProcesses({ ...q, [k]: undefined, page: undefined, page_size: "1" }).then(
          (r) => ({ k, total: r.total }),
          () => ({ k, total: null as number | null }),
        ),
      ),
    );
    const useful = probes.filter((p) => p.total && p.total > 0).sort((a, b) => (b.total ?? 0) - (a.total ?? 0));
    const valueOf = (k: string) => (k === "region" ? regionLabel(q.region ?? "") : k === "signal" ? (labels[q.signal ?? ""] ?? q.signal) : (q[k as keyof ProcessQuery] ?? ""));
    return (
      <EmptyState art>
        <p className="empty__t">Ningún proceso coincide con estos filtros.</p>
        {useful.length ? (
          <>
            <p style={{ marginTop: 8 }}>Prueba quitando uno:</p>
            <ul className="relax">
              {useful.map((p) => (
                <li key={p.k}>
                  <Link href={href(q, { [p.k]: undefined, page: undefined })} data-nav className="btn btn--line btn--sm">
                    Quitar {FILTER_NAMES[p.k]}: {valueOf(p.k)}
                  </Link>
                  <span className="muted small"> daría {fmtInt(p.total)} procesos</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p style={{ marginTop: 8 }}>Ni quitando un solo filtro aparecen procesos. Prueba con menos filtros a la vez.</p>
        )}
        <div className="actions">
          <Link href="/procesos" data-nav className="btn btn--ink btn--sm">
            Quitar todos los filtros
          </Link>
        </div>
      </EmptyState>
    );
  }

  const pages = Math.max(1, Math.ceil(page.total / page.page_size));
  return (
    <>
      <div className="results__head">
        <p className="results__count" role="status" aria-live="polite">
          {page.total === 1 ? "Hay 1 proceso" : `Hay ${fmtInt(page.total)} procesos`}
          {hasFilters ? " con estos filtros" : ""}.
        </p>
        <p className="results__sub">
          Página {fmtInt(page.page)} de {fmtInt(pages)} · {SORTS.find(([v]) => v === sort)?.[1] ?? "Orden personalizado"}.
        </p>
        <RiskLegend />
      </div>
      <ProcessTable
        rows={page.items}
        labels={labels}
        context={context}
        caption="Procesos de contratación con puntaje de riesgo"
        sort={{
          current: sort,
          href: (f) => href(q, { sort: sort === `-${f}` ? f : `-${f}`, page: undefined }),
        }}
      />
      <Pagination q={q} page={page.page} pages={pages} />
    </>
  );
}

function Pagination({ q, page, pages }: { q: ProcessQuery; page: number; pages: number }) {
  if (pages <= 1) return null;
  const window = Array.from(new Set([1, page - 1, page, page + 1, pages].filter((p) => p >= 1 && p <= pages))).sort((a, b) => a - b);
  return (
    <nav aria-label="Paginación" className="pager">
      {page > 1 ? (
        <Link href={href(q, { page: String(page - 1) })} rel="prev">
          Anterior
        </Link>
      ) : null}
      {window.map((p, i) => (
        <span key={p} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          {i > 0 && p - window[i - 1] > 1 ? <span aria-hidden="true">…</span> : null}
          <Link href={href(q, { page: p === 1 ? undefined : String(p) })} aria-current={p === page ? "page" : undefined}>
            <span className="sr-only">Página </span>
            {p}
          </Link>
        </span>
      ))}
      {page < pages ? (
        <Link href={href(q, { page: String(page + 1) })} rel="next">
          Siguiente
        </Link>
      ) : null}
    </nav>
  );
}
