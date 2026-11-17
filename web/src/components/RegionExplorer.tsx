"use client";

import Link from "next/link";
import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import geoData from "@/data/ecuador-provinces.json";
import { fmtInt, fmtPct, NA } from "@/lib/format";
import {
  CLASS_FILL,
  CLASS_NAME,
  countOf,
  fractionOf,
  isSmall,
  METRICS,
  METRIC_DEFINITION,
  quantileClasses,
  classRangeLabel,
  type Metric,
} from "@/lib/map";
import type { RegionRow } from "@/lib/types";

interface Prov {
  name: string;
  short: string;
  d: string;
  lx: number;
  ly: number;
  inset?: boolean;
}
const GEO = geoData as unknown as {
  source: { name: string; url: string; licence: string; boundaryYear: string; retrieved: string };
  viewBox: [number, number];
  inset: { x: number; y: number; w: number; h: number; label: string };
  provinces: Record<string, Prov>;
};
const [W, H] = GEO.viewBox;
const KEYS = Object.keys(GEO.provinces).sort((a, b) => GEO.provinces[a].name.localeCompare(GEO.provinces[b].name, "es"));
const TOP = CLASS_FILL.length - 1;
const HATCH = "veedor-hatch";

const fmtP = (v: number | null) => (v == null ? NA : fmtPct(v));

/** Pattern shared by every swatch and province of the top class: diagonal ink lines, so it reads without colour. */
function Defs() {
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" style={{ position: "absolute" }}>
      <defs>
        <pattern id={HATCH} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill={CLASS_FILL[TOP]} />
          <rect width="1.7" height="7" fill="#1a1f36" />
        </pattern>
      </defs>
    </svg>
  );
}

interface Props {
  rows: RegionRow[];
  national: Partial<RegionRow> | null;
  notes?: string[];
  compact?: boolean;
}

export function RegionExplorer({ rows, national, notes = [], compact = false }: Props) {
  const [metric, setMetric] = useState<Metric>("signal");
  const [hover, setHover] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [rove, setRove] = useState<string>(KEYS[0]);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const pointer = useRef<string>("mouse");
  const stage = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const links = useRef<Record<string, SVGAElement | null>>({});
  const groupId = useId();

  const byKey = useMemo(() => new Map(rows.map((r) => [r.region, r])), [rows]);
  const scale = useMemo(() => {
    const vals = KEYS.flatMap((k) => {
      const r = byKey.get(k);
      const v = r ? fractionOf(r, metric) : null;
      return v == null ? [] : [v];
    });
    return quantileClasses(vals);
  }, [byKey, metric]);
  const nat = national ? fractionOf(national, metric) : null;
  const active = hover ?? focus ?? sel;

  const info = (key: string) => {
    const r = byKey.get(key);
    const v = r ? fractionOf(r, metric) : null;
    return { r, v, cls: v == null ? -1 : scale.classOf(v) };
  };

  // Place the tooltip next to the active province without letting it leave the stage.
  useLayoutEffect(() => {
    const t = tip.current;
    const s = stage.current;
    if (!active || !t || !s) return;
    const sr = s.getBoundingClientRect();
    const tr = t.getBoundingClientRect();
    const p = GEO.provinces[active];
    const ax = (p.lx / W) * sr.width;
    const ay = (p.ly / H) * sr.height;
    const half = tr.width / 2;
    const left = Math.min(Math.max(ax, half + 4), sr.width - half - 4);
    const below = ay - tr.height - 16 < 0;
    t.style.left = `${left}px`;
    t.style.top = `${below ? ay + 16 : ay - 16}px`;
    t.style.transform = below ? "translate(-50%, 0)" : "translate(-50%, -100%)";
  }, [active, metric]);

  const label = (key: string) => byKey.get(key)?.region_label ?? GEO.provinces[key].name;
  const describe = (key: string) => {
    const { r, v } = info(key);
    if (!r || v == null) return `${label(key)}: sin datos.`;
    return `${label(key)}: ${fmtP(v)} ${METRICS[metric].question}, sobre ${fmtInt(r.competitive_processes)} procesos competitivos. Nacional: ${fmtP(nat)}.${
      isSmall(r) ? " Muestra pequeña." : ""
    } Abrir los procesos.`;
  };

  const move = (from: string, e: React.KeyboardEvent) => {
    const i = KEYS.indexOf(from);
    let n = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") n = (i + 1) % KEYS.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") n = (i - 1 + KEYS.length) % KEYS.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = KEYS.length - 1;
    else return;
    e.preventDefault();
    setRove(KEYS[n]);
    links.current[KEYS[n]]?.focus();
  };

  const ranges = scale.ranges;
  const best = useMemo(() => {
    const list = KEYS.flatMap((k) => {
      const { r, v } = info(k);
      return r && v != null ? [{ k, v, label: r.region_label }] : [];
    }).sort((a, b) => b.v - a.v);
    return list.length ? { top: list[0], low: list[list.length - 1] } : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [byKey, metric]);

  const sorted = useMemo(() => {
    // Default order is alphabetical by province: the table is not a ranking. The visitor can still sort by any column.
    const key = sort?.key ?? "name";
    const dir = sort?.dir ?? 1;
    const val = (r: RegionRow) =>
      key === "name" ? r.region_label : key === "competitive" ? r.competitive_processes : (fractionOf(r, key as Metric) ?? -1);
    return [...rows].sort((a, b) => {
      const x = val(a), y = val(b);
      const c = typeof x === "string" ? x.localeCompare(String(y), "es") : (x as number) - (y as number);
      return c * dir;
    });
  }, [rows, sort]);

  const sortBy = (key: string, first: 1 | -1) => setSort((s) => {
      const cur = s ?? { key: "name", dir: 1 as const };
      return cur.key === key ? { key, dir: (cur.dir * -1) as 1 | -1 } : { key, dir: first };
    });
  const ariaSort = (key: string): "ascending" | "descending" | "none" => {
    const cur = sort ?? { key: "name", dir: 1 as const };
    return cur.key === key ? (cur.dir === 1 ? "ascending" : "descending") : "none";
  };

  const a = active ? info(active) : null;
  const small = rows.some(isSmall);
  const nonMap = rows.filter((r) => !GEO.provinces[r.region]);

  return (
    <div className={`map ${compact ? "map--compact" : ""}`}>
      <Defs />
      <p className="callout">
        <b>Más señales no significa más problemas:</b> muchas veces refleja que en la zona hay menos proveedores. La provincia es la de la entidad que
        compra.
      </p>

      {compact ? null : (
        <fieldset className="seg">
          <legend className="seg__legend">Qué mostrar</legend>
          <div className="seg__opts">
            {(Object.keys(METRICS) as Metric[]).map((m) => (
              <label key={m} className={`seg__opt ${metric === m ? "seg__opt--on" : ""}`}>
                <input
                  type="radio"
                  name={`${groupId}-metric`}
                  value={m}
                  checked={metric === m}
                  onChange={() => {
                    setMetric(m);
                    setSort(null);
                  }}
                />
                <span>{METRICS[m].label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <p className="small muted map__def">{METRIC_DEFINITION[metric]}</p>
      <p className="sr-only" role="status" aria-live="polite">
        Mostrando el porcentaje de procesos competitivos {METRICS[metric].short}.
      </p>

      <div className="map__grid">
        <div className="map__fig">
          <div className="map__stage" ref={stage}>
            <svg
              viewBox={`0 0 ${W} ${H}`}
              className="map__svg"
              role="group"
              aria-label={`Mapa de las provincias del Ecuador. Porcentaje de procesos competitivos ${METRICS[metric].short}. Usa las flechas para pasar de una provincia a otra y Enter para ver sus procesos.`}
            >
              <rect
                x={GEO.inset.x}
                y={GEO.inset.y}
                width={GEO.inset.w}
                height={GEO.inset.h}
                rx="10"
                className="map__inset"
              />
              <text x={GEO.inset.x + 10} y={GEO.inset.y + 17} className="map__insetlab">
                {GEO.inset.label} (otra escala)
              </text>
              {KEYS.map((k) => {
                const p = GEO.provinces[k];
                const { r, cls } = info(k);
                const fill = cls < 0 ? "#f1f6ff" : cls === TOP ? `url(#${HATCH})` : CLASS_FILL[cls];
                return (
                  <Link
                    key={k}
                    href={`/procesos?region=${encodeURIComponent(k)}`}
                    ref={(el) => {
                      links.current[k] = el as unknown as SVGAElement | null;
                    }}
                    className="map__a"
                    aria-label={describe(k)}
                    tabIndex={rove === k ? 0 : -1}
                    onPointerDown={(e) => {
                      pointer.current = e.pointerType;
                    }}
                    onPointerEnter={(e) => {
                      if (e.pointerType === "mouse") setHover(k);
                    }}
                    onPointerLeave={() => setHover(null)}
                    onFocus={() => {
                      setFocus(k);
                      setRove(k);
                    }}
                    onBlur={() => setFocus(null)}
                    onKeyDown={(e) => move(k, e)}
                    onClick={(e) => {
                      // Touch: the first tap reads the province, the second one opens it.
                      if (pointer.current === "touch" && sel !== k) {
                        e.preventDefault();
                        setSel(k);
                        setRove(k);
                      }
                    }}
                  >
                    <path
                      d={p.d}
                      fill={fill}
                      className={`map__p ${r && isSmall(r) ? "map__p--small" : ""} ${active === k ? "map__p--on" : ""}`}
                    />
                  </Link>
                );
              })}
              {active ? (
                <>
                  <path d={GEO.provinces[active].d} className="map__ring map__ring--o" aria-hidden="true" />
                  <path d={GEO.provinces[active].d} className="map__ring map__ring--i" aria-hidden="true" />
                </>
              ) : null}
              {compact ? null : (
                <g className="map__labels" aria-hidden="true">
                  {KEYS.map((k) => {
                    const p = GEO.provinces[k];
                    const w = p.short.length * 5.7 + 10;
                    const small = byKey.get(k) && isSmall(byKey.get(k)!);
                    return (
                      <g key={k} transform={`translate(${p.lx} ${p.ly})`}>
                        <rect x={-w / 2} y="-7.5" width={w} height="15" rx="7.5" />
                        <text y="3.6" textAnchor="middle">
                          {p.short}
                          {small ? "*" : ""}
                        </text>
                      </g>
                    );
                  })}
                </g>
              )}
            </svg>
            {a && active ? (
              <div className="map__tip" ref={tip} aria-hidden="true">
                <p className="map__tipname">{label(active)}</p>
                {a.r && a.v != null ? (
                  <>
                    <p className="map__tipval">
                      {fmtP(a.v)} <span>{METRICS[metric].short}</span>
                    </p>
                    <p>Sobre {fmtInt(a.r.competitive_processes)} procesos competitivos</p>
                    <p>Nacional: {fmtP(nat)}</p>
                    {isSmall(a.r) ? <p className="map__tipsmall">Muestra pequeña: léelo con cautela.</p> : null}
                    {sel === active ? (
                      <Link href={`/procesos?region=${encodeURIComponent(active)}`} className="map__tiplink" onPointerDown={(e) => e.stopPropagation()}>
                        Ver los procesos
                      </Link>
                    ) : null}
                  </>
                ) : (
                  <p>Sin datos para esta provincia.</p>
                )}
              </div>
            ) : null}
          </div>
        </div>

        <div className="map__side">
          <h3 className="h4">Cómo leer los colores</h3>
          <ul className="mlegend" aria-label="Escala de colores">
            {CLASS_FILL.map((fill, i) => (
              <li key={i}>
                <svg width="34" height="24" viewBox="0 0 34 24" aria-hidden="true" focusable="false">
                  <rect x="1.5" y="1.5" width="31" height="21" rx="6" fill={i === TOP ? `url(#${HATCH})` : fill} stroke="#1a1f36" strokeWidth="2.5" />
                </svg>
                <span>
                  <b>{CLASS_NAME[i]}</b>{" "}
                  <span className="muted">
                    {ranges[i] ? (
                      <>
                        {classRangeLabel(scale.cuts, i)} · {ranges[i]!.count} {ranges[i]!.count === 1 ? "provincia" : "provincias"}
                      </>
                    ) : (
                      "sin provincias"
                    )}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          <p className="small muted">
            Cinco grupos con el mismo número de provincias (quintiles). Son una forma de agruparlas, no umbrales: siempre hay un grupo con el
            porcentaje más alto, aunque las diferencias sean pequeñas. Ese grupo lleva rayas para que se distinga sin color.
          </p>
          {small ? (
            <p className="small muted">
              <b>*</b> y borde discontinuo: <b>muestra pequeña</b>, con menos de 500 procesos competitivos.
            </p>
          ) : null}
          {best ? (
            <p className="map__read">
              En el país, {fmtP(nat)} de los procesos competitivos tuvo{" "}
              {metric === "signal" ? "al menos una señal" : "la señal «oferente único»"}. Por provincia va de {fmtP(best.low.v)} a{" "}
              {fmtP(best.top.v)}.
            </p>
          ) : null}
          <p className="small muted">
            Se cuentan solo los <b>procesos competitivos</b> (subasta inversa, menor cuantía, cotización y licitación). Las compras por catálogo y las directas
            no entran.
          </p>
        </div>
      </div>

      {compact ? (
        <div className="actions">
          <Link href="/mapa" className="btn btn--ink btn--sm">
            Ver el mapa completo
          </Link>
        </div>
      ) : (
        <>
          <h3 className="h3 map__tbltitle" id="tabla-provincias">
            Datos por provincia
          </h3>
          <p className="small muted" style={{ marginTop: 6 }}>
            En orden alfabético; puedes ordenar por la columna que quieras. Cada provincia lleva a sus procesos.
          </p>
          <p className="callout" style={{ marginTop: 10 }}>
            <b>Más señales no significa más problemas:</b> el orden de una columna no es un ranking ni un juicio sobre la provincia. La provincia es la de la
            entidad que compra.
          </p>
          <div className="tbl-wrap" tabIndex={0} role="region" aria-labelledby="tabla-provincias" style={{ marginTop: 14 }}>
            <table className="tbl tbl--regions">
              <caption className="sr-only">Procesos competitivos por provincia de la entidad contratante</caption>
              <thead>
                <tr>
                  <th scope="col" aria-sort={ariaSort("name")}>
                    <button type="button" className="sortbtn" onClick={() => sortBy("name", 1)}>Provincia</button>
                  </th>
                  <th scope="col" className="r" aria-sort={ariaSort("competitive")}>
                    <button type="button" className="sortbtn" onClick={() => sortBy("competitive", -1)}>Procesos competitivos</button>
                  </th>
                  <th scope="col" className="r" aria-sort={ariaSort("signal")}>
                    <button type="button" className="sortbtn" onClick={() => sortBy("signal", -1)}>Con al menos una señal</button>
                  </th>
                  <th scope="col" className="r" aria-sort={ariaSort("single")}>
                    <button type="button" className="sortbtn" onClick={() => sortBy("single", -1)}>Con la señal «oferente único»</button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.region}>
                    <th scope="row">
                      {GEO.provinces[r.region] ? (
                        <Link href={`/procesos?region=${encodeURIComponent(r.region)}`} className="cell-link">
                          {r.region_label}
                        </Link>
                      ) : (
                        r.region_label
                      )}
                      {isSmall(r) ? <span className="cell-sub">Muestra pequeña</span> : null}
                    </th>
                    <td className="r">{fmtInt(r.competitive_processes)}</td>
                    <td className="r">
                      <b>{fmtP(fractionOf(r, "signal"))}</b>
                      <span className="cell-sub">{fmtInt(countOf(r, "signal"))} procesos</span>
                    </td>
                    <td className="r">
                      <b>{fmtP(fractionOf(r, "single"))}</b>
                      <span className="cell-sub">{fmtInt(countOf(r, "single"))} procesos</span>
                    </td>
                  </tr>
                ))}
              </tbody>
              {national ? (
                <tfoot>
                  <tr>
                    <th scope="row">Nacional</th>
                    <td className="r">{fmtInt(national.competitive_processes)}</td>
                    <td className="r">
                      <b>{fmtP(fractionOf(national, "signal"))}</b>
                    </td>
                    <td className="r">
                      <b>{fmtP(fractionOf(national, "single"))}</b>
                    </td>
                  </tr>
                </tfoot>
              ) : null}
            </table>
          </div>
          {nonMap.length ? (
            <p className="small muted" style={{ marginTop: 10 }}>
              Las filas sin provincia identificable no se dibujan en el mapa.
            </p>
          ) : null}
          {notes.length ? (
            <ul className="small muted" style={{ marginTop: 14, display: "grid", gap: 4, maxWidth: "52rem" }}>
              {notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
          <p className="small muted map__attr">
            Límites provinciales: {GEO.source.name} (
            <a href={GEO.source.url} rel="noopener noreferrer" target="_blank" className="inline-link">
              fuente<span className="sr-only"> (se abre en una pestaña nueva)</span>
            </a>
            ), licencia {GEO.source.licence}, límites de {GEO.source.boundaryYear}, simplificados para esta página. Obtenido el {GEO.source.retrieved}.
          </p>
        </>
      )}
    </div>
  );
}
