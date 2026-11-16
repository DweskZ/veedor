"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useTransition, type ReactNode } from "react";
import { RandomProcessButton } from "./RandomProcessButton";

export interface Opt {
  value: string;
  label: string;
}
export interface QuickChip {
  id: string;
  label: string;
  href: string;
  on: boolean;
  count: number | null;
}
export interface ActiveFilter {
  id: string;
  text: string;
  removeHref: string;
}

interface Props {
  values: { year: string; method: string; signal: string; region: string; min_score: string; min_amount: string; max_amount: string; q: string; sort: string };
  years: Opt[];
  methods: Opt[];
  signals: Opt[];
  regions: Opt[];
  sorts: Opt[];
  chips: QuickChip[];
  active: ActiveFilter[];
  clearHref: string;
  children: ReactNode;
}

const fmt = new Intl.NumberFormat("es-EC");

function Select({ name, label, value, options, all }: { name: string; label: string; value: string; options: Opt[]; all?: string }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      <select name={name} defaultValue={value} className="control">
        {all ? <option value="">{all}</option> : null}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Filters, quick chips and active-filter chips. Every change navigates with a router transition: the server re-renders only the
 * results, the old ones stay visible (dimmed) until the new ones arrive and the URL stays shareable. Without JavaScript the form is a
 * plain GET and the chips are plain links.
 */
export function ExplorerShell({ values, years, methods, signals, regions, sorts, chips, active, clearHref, children }: Props) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const form = useRef<HTMLFormElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  // Chips, removable filters and back/forward change the URL without touching the form: keep its fields in step.
  const { year, method, signal, region, min_score, min_amount, max_amount, q, sort } = values;
  useEffect(() => {
    const f = form.current;
    if (!f) return;
    const now = { year, method, signal, region, min_score, min_amount, max_amount, q, sort };
    for (const [name, v] of Object.entries(now)) {
      const el = f.elements.namedItem(name);
      if ((el instanceof HTMLSelectElement || el instanceof HTMLInputElement) && el !== document.activeElement && el.value !== v) el.value = v;
    }
  }, [year, method, signal, region, min_score, min_amount, max_amount, q, sort]);

  const go = (href: string) => start(() => router.push(href, { scroll: false }));

  const apply = () => {
    if (!form.current) return;
    const sp = new URLSearchParams();
    for (const [k, v] of new FormData(form.current)) if (typeof v === "string" && v.trim()) sp.set(k, v.trim());
    if (sp.get("sort") === "-risk_score") sp.delete("sort");
    const s = sp.toString();
    go(s ? `/procesos?${s}` : "/procesos");
  };
  const later = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(apply, 450);
  };

  return (
    <div
      onClick={(e) => {
        const a = (e.target as HTMLElement).closest<HTMLAnchorElement>("a[data-nav]");
        if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        go(a.getAttribute("href") ?? "/procesos");
      }}
    >
      <form
        ref={form}
        method="get"
        action="/procesos"
        role="search"
        aria-label="Filtros de procesos"
        className="filters"
        onChange={(e) => {
          const t = e.target as HTMLElement;
          if (t instanceof HTMLSelectElement) apply();
        }}
        onInput={(e) => {
          const t = e.target as HTMLElement;
          if (t instanceof HTMLInputElement) later();
        }}
        onSubmit={(e) => {
          e.preventDefault();
          if (timer.current) clearTimeout(timer.current);
          apply();
        }}
      >
        <div className="qchips" role="group" aria-label="Filtros rápidos">
          <span className="qchips__t">Empieza por:</span>
          {chips.map((c) => (
            <a key={c.id} href={c.href} data-nav className={`qchip ${c.on ? "qchip--on" : ""}`} aria-current={c.on ? "true" : undefined}>
              {c.on ? <span aria-hidden="true">✓ </span> : null}
              {c.label}
              {c.count != null ? <span className="qchip__n"> {fmt.format(c.count)}</span> : null}
              <span className="sr-only">{c.on ? " (activo, pulsa para quitarlo)" : ""}</span>
            </a>
          ))}
          <span className="qchips__r">
            <RandomProcessButton className="btn btn--line btn--sm" label="Proceso al azar" />
          </span>
        </div>

        <div className="filters__grid">
          <label className="field field--search">
            <span className="field__label">Buscar</span>
            <input name="q" type="search" defaultValue={values.q} placeholder="Escribe aquí" className="control" />
            <span className="field__help">Código del proceso o nombre de la entidad</span>
          </label>
          <Select name="year" label="Año" value={values.year} options={years} all="Todos los años" />
          <Select name="method" label="Método de contratación" value={values.method} options={methods} all="Todos los métodos" />
          {regions.length ? <Select name="region" label="Provincia de la entidad" value={values.region} options={regions} all="Todo el país" /> : null}
          <Select name="signal" label="Tipo de señal" value={values.signal} options={signals} all="Cualquier señal" />
          <label className="field">
            <span className="field__label">Puntaje mínimo</span>
            <input name="min_score" type="number" min={0} max={100} inputMode="numeric" defaultValue={values.min_score} placeholder="0" className="control" />
            <span className="field__help">De 0 a 100</span>
          </label>
          <Select name="sort" label="Ordenar por" value={values.sort} options={sorts} />
        </div>
        <input type="hidden" name="min_amount" defaultValue={values.min_amount} />
        <input type="hidden" name="max_amount" defaultValue={values.max_amount} />
        <div className="filters__foot">
          <p className="small muted" style={{ margin: 0 }}>
            Los resultados se actualizan al cambiar un filtro.
          </p>
          <div className="filters__btns">
            <button type="submit" className="btn btn--tc btn--sm nojs-only">
              Aplicar filtros
            </button>
            {active.length ? (
              <a href={clearHref} data-nav className="btn btn--line btn--sm">
                Quitar los {active.length} filtros
              </a>
            ) : null}
          </div>
        </div>
      </form>

      {active.length ? (
        <ul className="achips" aria-label="Filtros activos">
          {active.map((f) => (
            <li key={f.id}>
              <a href={f.removeHref} data-nav className="achip">
                {f.text}
                <span aria-hidden="true" className="achip__x">×</span>
                <span className="sr-only"> Quitar este filtro</span>
              </a>
            </li>
          ))}
          <li>
            <a href={clearHref} data-nav className="achips__clear">
              Quitar todos
            </a>
          </li>
        </ul>
      ) : null}

      <div className={`results ${pending ? "results--pending" : ""}`} aria-busy={pending}>
        {pending ? (
          <p className="sr-only" role="status">
            Actualizando resultados…
          </p>
        ) : null}
        {children}
      </div>
    </div>
  );
}
