import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { getProcesses, getSignals, getStats } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import type { ProcessQuery, SignalDef } from "@/lib/types";
import { ProcessTable } from "@/components/ProcessTable";
import { EmptyState, ErrorState, PageHeader, RiskLegend, Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Procesos" };

// Method names as they appear in the contract's data description.
const METHODS = ["Subasta Inversa Electrónica", "Menor Cuantía", "Cotización", "Licitación"];
const PAGE_SIZE = 25;
const KEYS = ["year", "method", "signal", "min_score", "q", "sort", "page"] as const;

function pick(sp: Record<string, string | string[] | undefined>): ProcessQuery {
  const out: Record<string, string> = {};
  for (const k of KEYS) {
    const v = sp[k];
    const s = Array.isArray(v) ? v[0] : v;
    if (s) out[k] = s;
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
    <>
      <PageHeader
        eyebrow="Explorador"
        title={
          <>
            Todos los <em>procesos.</em>
          </>
        }
        lead="Cada fila es una compra del Estado con su puntaje de riesgo. Filtra lo que te interese: la dirección de la página guarda tus filtros, así puedes compartir lo que ves."
      />
      <div className="wrap">
        <Suspense fallback={<Skeleton style={{ height: 544 }} />}>
          <Explorer searchParams={searchParams} />
        </Suspense>
        <div className="page-end" />
      </div>
    </>
  );
}

async function Explorer({ searchParams }: { searchParams: PageProps<"/procesos">["searchParams"] }) {
  const q = pick(await searchParams);
  const [res, sigRes, statRes] = await Promise.allSettled([
    getProcesses({ ...q, page_size: String(PAGE_SIZE) }),
    getSignals(),
    getStats(),
  ]);
  const signals: SignalDef[] = sigRes.status === "fulfilled" ? sigRes.value : [];
  const labels = Object.fromEntries(signals.map((s) => [s.code, s.label_es]));
  const context = signals.filter((s) => s.kind === "context").map((s) => s.code);
  const last = statRes.status === "fulfilled" ? statRes.value.last_year ?? 2026 : 2026;
  const firstY = statRes.status === "fulfilled" ? statRes.value.first_year ?? 2015 : 2015;
  const years = Array.from({ length: Math.max(1, last - firstY + 1) }, (_, i) => String(last - i));
  const sort = q.sort || "-risk_score";
  const hasFilters = Boolean(q.year || q.method || q.signal || q.min_score || q.q);

  return (
    <>
      <form method="get" action="/procesos" role="search" aria-label="Filtros de procesos" className="filters">
        <div className="filters__grid">
          <Field label="Año">
            <select name="year" defaultValue={q.year ?? ""} className="control">
              <option value="">Todos los años</option>
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Método de contratación">
            <select name="method" defaultValue={q.method ?? ""} className="control">
              <option value="">Todos los métodos</option>
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Tipo de señal">
            <select name="signal" defaultValue={q.signal ?? ""} className="control">
              <option value="">Cualquier señal</option>
              {signals.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label_es}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Puntaje mínimo" help="De 0 a 100">
            <input name="min_score" type="number" min={0} max={100} inputMode="numeric" defaultValue={q.min_score ?? ""} placeholder="0" className="control" />
          </Field>
          <Field label="Buscar" help="Código del proceso o nombre de la entidad">
            <input name="q" type="search" defaultValue={q.q ?? ""} placeholder="Escribe aquí" className="control" />
          </Field>
          <Field label="Ordenar por">
            <select name="sort" defaultValue={SORTS.some(([v]) => v === sort) ? sort : "-risk_score"} className="control">
              {SORTS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="filters__foot">
          <RiskLegend />
          <div className="filters__btns">
            <button type="submit" className="btn btn--tc btn--sm">
              Aplicar filtros
            </button>
            {hasFilters ? (
              <Link href="/procesos" className="btn btn--line btn--sm">
                Quitar filtros
              </Link>
            ) : null}
          </div>
        </div>
      </form>

      <div style={{ marginTop: 40 }} aria-live="polite">
        {res.status === "rejected" ? (
          <ErrorState detail={res.reason instanceof Error ? res.reason.message : undefined} />
        ) : res.value.items.length === 0 ? (
          <EmptyState art>
            <p className="empty__t">Ningún proceso coincide con estos filtros.</p>
            <p style={{ marginTop: 8 }}>Prueba con un puntaje mínimo menor o quita algún filtro.</p>
            <div className="actions">
              <Link href="/procesos" className="btn btn--ink btn--sm">
                Quitar filtros
              </Link>
            </div>
          </EmptyState>
        ) : (
          <>
            <div style={{ marginBottom: 18 }}>
              <p className="results__count">
                {res.value.total === 1 ? "Hay 1 proceso" : `Hay ${fmtInt(res.value.total)} procesos`}
                {hasFilters ? " con estos filtros" : ""}.
              </p>
              <p className="results__sub">
                Página {fmtInt(res.value.page)} de {fmtInt(Math.max(1, Math.ceil(res.value.total / res.value.page_size)))} · {SORTS.find(([v]) => v === sort)?.[1] ?? "Orden personalizado"}.
              </p>
            </div>
            <ProcessTable
              rows={res.value.items}
              labels={labels}
              context={context}
              caption="Procesos de contratación con puntaje de riesgo"
              sort={{
                current: sort,
                href: (f) => href(q, { sort: sort === `-${f}` ? f : `-${f}`, page: undefined }),
              }}
            />
            <Pagination q={q} page={res.value.page} pages={Math.max(1, Math.ceil(res.value.total / res.value.page_size))} />
          </>
        )}
      </div>
    </>
  );
}

function Field({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {help ? <span className="field__help">{help}</span> : null}
    </label>
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
