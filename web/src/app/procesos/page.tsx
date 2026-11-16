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

export default function ProcesosPage({ searchParams }: PageProps<"/procesos">) {
  return (
    <>
      <PageHeader
        title="Procesos"
        lead="Explore los procesos de contratación con su puntaje de riesgo. Los filtros se reflejan en la dirección de la página para poder compartir una vista."
      />
      <Suspense fallback={<Skeleton className="h-[34rem]" />}>
        <Explorer searchParams={searchParams} />
      </Suspense>
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

  return (
    <>
      <form method="get" action="/procesos" role="search" aria-label="Filtros de procesos" className="rounded-lg border border-line bg-surface p-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Año">
            <select name="year" defaultValue={q.year ?? ""} className={INPUT}>
              <option value="">Todos</option>
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Método">
            <select name="method" defaultValue={q.method ?? ""} className={INPUT}>
              <option value="">Todos</option>
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Señal">
            <select name="signal" defaultValue={q.signal ?? ""} className={INPUT}>
              <option value="">Todas</option>
              {signals.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label_es}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Puntaje mínimo">
            <input name="min_score" type="number" min={0} max={100} inputMode="numeric" defaultValue={q.min_score ?? ""} className={INPUT} />
          </Field>
          <Field label="Buscar">
            <input name="q" type="search" defaultValue={q.q ?? ""} placeholder="Código o nombre" className={INPUT} />
          </Field>
        </div>
        {q.sort ? <input type="hidden" name="sort" value={q.sort} /> : null}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <RiskLegend />
          <div className="flex items-center gap-3">
            <Link href="/procesos" className="text-sm text-muted underline underline-offset-2 hover:text-ink">
              Limpiar filtros
            </Link>
            <button type="submit" className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:opacity-90">
              Aplicar filtros
            </button>
          </div>
        </div>
      </form>

      <div className="mt-6" aria-live="polite">
        {res.status === "rejected" ? (
          <ErrorState detail={res.reason instanceof Error ? res.reason.message : undefined} />
        ) : res.value.items.length === 0 ? (
          <EmptyState>Ningún proceso coincide con estos filtros. Pruebe con un puntaje mínimo menor o quite algún filtro.</EmptyState>
        ) : (
          <>
            <p className="mb-3 text-sm text-muted">
              {fmtInt(res.value.total)} procesos · página {fmtInt(res.value.page)} de {fmtInt(Math.max(1, Math.ceil(res.value.total / res.value.page_size)))}
            </p>
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

const INPUT =
  "w-full rounded-md border border-line bg-bg px-3 py-2 text-sm text-ink placeholder:text-muted";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-ink">{label}</span>
      {children}
    </label>
  );
}

function Pagination({ q, page, pages }: { q: ProcessQuery; page: number; pages: number }) {
  if (pages <= 1) return null;
  const window = Array.from(new Set([1, page - 1, page, page + 1, pages].filter((p) => p >= 1 && p <= pages))).sort((a, b) => a - b);
  const link = "rounded-md border border-line px-3 py-1.5 text-sm hover:bg-surface-2";
  return (
    <nav aria-label="Paginación" className="mt-4 flex flex-wrap items-center justify-center gap-2">
      {page > 1 ? (
        <Link href={href(q, { page: String(page - 1) })} rel="prev" className={link}>
          Anterior
        </Link>
      ) : null}
      {window.map((p, i) => (
        <span key={p} className="inline-flex items-center gap-2">
          {i > 0 && p - window[i - 1] > 1 ? <span aria-hidden="true">…</span> : null}
          <Link
            href={href(q, { page: p === 1 ? undefined : String(p) })}
            aria-current={p === page ? "page" : undefined}
            className={`${link} ${p === page ? "bg-accent text-accent-ink hover:bg-accent" : ""}`}
          >
            <span className="sr-only">Página </span>
            {p}
          </Link>
        </span>
      ))}
      {page < pages ? (
        <Link href={href(q, { page: String(page + 1) })} rel="next" className={link}>
          Siguiente
        </Link>
      ) : null}
    </nav>
  );
}
