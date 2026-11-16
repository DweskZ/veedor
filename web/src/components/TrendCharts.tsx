"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { fmtInt, fmtPct, NA } from "@/lib/format";
import type { YearRow } from "@/lib/types";

const H = 290;
const M = { l: 48, r: 18, t: 18, b: 38 };
const INK = "#1a1f36";
const GRID = "#cadbfb";
const MUTED = "#5b6384";

const p = (v: number | null) => (v == null ? NA : fmtPct(v));

/** Width of an element, tracked so that chart text keeps its real pixel size on any screen. */
function useWidth(initial = 680) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => setW(Math.max(280, Math.round(el.getBoundingClientRect().width)));
    read();
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function niceMax(v: number) {
  const step = v > 0.5 ? 0.2 : v > 0.2 ? 0.1 : 0.05;
  return Math.max(step, Math.ceil((v * 1.1) / step) * step);
}

interface FrameProps {
  years: YearRow[];
  label: string;
  reading: ReactNode;
  readout: (i: number) => ReactNode;
  children: (g: { w: number; x: (i: number) => number; band: number; active: number; plotH: number }) => ReactNode;
  yMax: number;
  table: ReactNode;
  notes: string[];
  lastFull: number;
  title: string;
  id: string;
}

/** Shared chart frame: card, reading sentence, live readout, keyboard and pointer year selection, notes and data table. */
function Frame({ years, label, reading, readout, children, yMax, table, notes, lastFull, title, id }: FrameProps) {
  const [ref, w] = useWidth();
  const [active, setActive] = useState(lastFull);
  const plotW = w - M.l - M.r;
  const plotH = H - M.t - M.b;
  const band = plotW / years.length;
  const x = (i: number) => M.l + band * (i + 0.5);
  const ticks = Array.from({ length: Math.round(yMax / (yMax > 0.5 ? 0.2 : yMax > 0.2 ? 0.1 : 0.05)) + 1 }, (_, k) => k * (yMax > 0.5 ? 0.2 : yMax > 0.2 ? 0.1 : 0.05));
  const sparse = band < 34;

  const onKey = (e: KeyboardEvent) => {
    let n = active;
    if (e.key === "ArrowRight") n = Math.min(years.length - 1, active + 1);
    else if (e.key === "ArrowLeft") n = Math.max(0, active - 1);
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = years.length - 1;
    else return;
    e.preventDefault();
    setActive(n);
  };

  return (
    <section className="card trend" aria-labelledby={`${id}-t`}>
      <h2 className="h3" id={`${id}-t`}>
        {title}
      </h2>
      <p className="trend__read">{reading}</p>
      <div className="trend__body">
        <div className="trend__chart" ref={ref}>
          <p className="trend__out" aria-live="polite">
            {readout(active)}
          </p>
          <svg
            width="100%"
            height={H}
            viewBox={`0 0 ${w} ${H}`}
            role="group"
            tabIndex={0}
            aria-label={`${label}. Usa las flechas izquierda y derecha para recorrer los años.`}
            className="trend__svg"
            onKeyDown={onKey}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              const px = ((e.clientX - r.left) / r.width) * w;
              setActive(Math.max(0, Math.min(years.length - 1, Math.floor((px - M.l) / band))));
            }}
          >
            {ticks.map((t) => {
              const y = M.t + plotH - (t / yMax) * plotH;
              return (
                <g key={t}>
                  <line x1={M.l} x2={w - M.r} y1={y} y2={y} stroke={GRID} strokeWidth={t === 0 ? 2 : 1} />
                  <text x={M.l - 8} y={y + 4} textAnchor="end" fontSize="12" fontWeight="700" fill={MUTED}>
                    {fmtPct(t)}
                  </text>
                </g>
              );
            })}
            {years.map((yr, i) =>
              !sparse || i % 2 === (years.length - 1) % 2 ? (
                <text key={yr.year} x={x(i)} y={H - 12} textAnchor="middle" fontSize="12" fontWeight={i === active ? 800 : 600} fill={i === active ? INK : MUTED}>
                  {sparse ? String(yr.year).slice(2) : yr.year}
                  {yr.partial_year ? "*" : ""}
                </text>
              ) : null,
            )}
            <rect x={x(active) - band / 2} y={M.t} width={band} height={plotH} fill={INK} opacity="0.07" />
            {children({ w, x, band, active, plotH })}
          </svg>
        </div>
        <aside className="trend__notes" aria-label="Ten en cuenta">
          <p className="tag">Ten en cuenta</p>
          <ul>
            {years.some((y) => y.partial_year) ? <li>* Año en curso: los datos llegan hasta la última actualización y se dibujan con trazo discontinuo.</li> : null}
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </aside>
      </div>
      <details className="trend__table">
        <summary>Ver los datos en una tabla</summary>
        <div className="tbl-wrap" tabIndex={0} role="region" aria-label={`${title} (tabla desplazable)`}>
          {table}
        </div>
      </details>
    </section>
  );
}

const yearLabel = (y: YearRow) => `${y.year}${y.partial_year ? " (año parcial)" : ""}`;

function LineChart({
  years,
  series,
  title,
  id,
  what,
  unit,
  base,
  notes,
  lastFull,
}: {
  years: YearRow[];
  series: (y: YearRow) => number | null;
  title: string;
  id: string;
  what: string;
  unit: string;
  base: (y: YearRow) => number | null;
  notes: string[];
  lastFull: number;
}) {
  const vals = years.map(series);
  const max = niceMax(Math.max(0.05, ...vals.map((v) => v ?? 0)));
  const full = years.map((y, i) => ({ y, v: vals[i], i })).filter((d) => d.v != null && !d.y.partial_year);
  const first = full[0];
  const last = full[full.length - 1];
  const top = full.reduce((a, b) => ((b.v as number) > ((a?.v as number) ?? -1) ? b : a), full[0]);
  const reading = first && last && top ? (
    <>
      Entre {first.y.year} y {last.y.year}, {what} pasó de <b>{p(first.v)}</b> a <b>{p(last.v)}</b>. El valor más alto fue <b>{p(top.v)}</b> en {top.y.year}.
    </>
  ) : (
    "No hay datos suficientes para describir este gráfico."
  );
  return (
    <Frame
      id={id}
      title={title}
      years={years}
      lastFull={lastFull}
      notes={notes}
      yMax={max}
      label={title}
      reading={reading}
      readout={(i) => (
        <>
          <b>{yearLabel(years[i])}:</b> {p(vals[i])} {unit}
          <span className="muted">{base(years[i]) != null ? ` · sobre ${fmtInt(base(years[i]))} procesos` : ""}</span>
        </>
      )}
      table={
        <table className="tbl">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th scope="col">Año</th>
              <th scope="col" className="r">Porcentaje</th>
            </tr>
          </thead>
          <tbody>
            {years.map((y, i) => (
              <tr key={y.year}>
                <th scope="row">{yearLabel(y)}</th>
                <td className="r">{p(vals[i])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {({ x, plotH, active }) => {
        const yy = (v: number) => M.t + plotH - (v / max) * plotH;
        const pts = years.flatMap((yr, i) => (vals[i] == null ? [] : [{ i, yr, X: x(i), Y: yy(vals[i] as number) }]));
        const solid = pts.filter((d) => !d.yr.partial_year);
        const tail = pts.length && pts[pts.length - 1].yr.partial_year && solid.length ? [solid[solid.length - 1], pts[pts.length - 1]] : [];
        const path = (a: { X: number; Y: number }[]) => a.map((d, k) => `${k ? "L" : "M"}${d.X.toFixed(1)} ${d.Y.toFixed(1)}`).join("");
        return (
          <g>
            {solid.length > 1 ? <path d={path(solid)} fill="none" stroke={INK} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" /> : null}
            {tail.length ? <path d={path(tail)} fill="none" stroke={INK} strokeWidth="3" strokeDasharray="6 6" strokeLinecap="round" /> : null}
            {pts.map((d) => (
              <circle
                key={d.yr.year}
                cx={d.X}
                cy={d.Y}
                r={d.i === active ? 7 : 4.5}
                fill={d.yr.partial_year ? "#ffffff" : d.i === active ? "#d9480f" : INK}
                stroke={INK}
                strokeWidth="2.5"
              />
            ))}
          </g>
        );
      }}
    </Frame>
  );
}

const MIX: { key: "competitive" | "direct" | "catalogue" | "other"; label: string; fill: string }[] = [
  { key: "competitive", label: "Competitivos", fill: INK },
  { key: "direct", label: "Contratación directa", fill: "#8fa6db" },
  { key: "catalogue", label: "Catálogo electrónico", fill: "#ffffff" },
  { key: "other", label: "Otros", fill: "#e3eeff" },
];

function MixChart({ years, notes, lastFull }: { years: YearRow[]; notes: string[]; lastFull: number }) {
  const rows = years.filter((y) => MIX.some((m) => y.mix[m.key] != null));
  const ref = rows[Math.max(0, Math.min(rows.length - 1, rows.findIndex((r) => r.year === years[lastFull].year)))] ?? rows[rows.length - 1];
  const reading = ref ? (
    <>
      En {ref.year}, de cada 100 dólares adjudicados, unos <b>{Math.round((ref.mix.competitive ?? 0) * 100)}</b> se compraron por métodos competitivos,{" "}
      <b>{Math.round((ref.mix.direct ?? 0) * 100)}</b> por contratación directa y <b>{Math.round((ref.mix.catalogue ?? 0) * 100)}</b> por catálogo electrónico.
    </>
  ) : (
    "No hay datos suficientes para describir este gráfico."
  );
  const idx = rows.map((r) => years.indexOf(r));
  return (
    <Frame
      id="mezcla"
      title="Cómo compra el Estado, según el monto"
      years={rows}
      lastFull={Math.max(0, idx.findIndex((i) => i === lastFull))}
      notes={notes}
      yMax={1}
      label="Cómo compra el Estado, según el monto, por año"
      reading={reading}
      readout={(i) => (
        <>
          <b>{yearLabel(rows[i])}:</b> competitivos {p(rows[i].mix.competitive)} · directa {p(rows[i].mix.direct)} · catálogo {p(rows[i].mix.catalogue)} · otros {p(rows[i].mix.other)}
        </>
      )}
      table={
        <table className="tbl">
          <caption className="sr-only">Parte del monto adjudicado por método de compra y año</caption>
          <thead>
            <tr>
              <th scope="col">Año</th>
              {MIX.map((m) => (
                <th key={m.key} scope="col" className="r">{m.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((y) => (
              <tr key={y.year}>
                <th scope="row">{yearLabel(y)}</th>
                {MIX.map((m) => (
                  <td key={m.key} className="r">{p(y.mix[m.key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {({ x, band, plotH, active }) => (
        <g>
          {rows.map((y, i) => {
            let acc = 0;
            const bw = Math.min(46, band * 0.68);
            return (
              <g key={y.year}>
                {MIX.map((m) => {
                  const v = y.mix[m.key] ?? 0;
                  const h = v * plotH;
                  const top = M.t + plotH - (acc + v) * plotH;
                  acc += v;
                  return (
                    <rect
                      key={m.key}
                      x={x(i) - bw / 2}
                      y={top}
                      width={bw}
                      height={Math.max(0, h)}
                      fill={m.fill}
                      stroke={INK}
                      strokeWidth={i === active ? 2.5 : 1.5}
                      strokeDasharray={y.partial_year ? "5 4" : undefined}
                    />
                  );
                })}
              </g>
            );
          })}
        </g>
      )}
    </Frame>
  );
}

export function TrendCharts({ years, notes }: { years: YearRow[]; notes: string[] }) {
  const general = notes.filter((n) => !/oferente único/i.test(n));
  if (years.length === 0) return <p className="muted">No hay datos por año disponibles.</p>;
  const lastFullIdx = (() => {
    for (let i = years.length - 1; i >= 0; i--) if (!years[i].partial_year) return i;
    return years.length - 1;
  })();
  return (
    <div className="trends">
      <LineChart
        id="solo-oferente"
        title="¿Cuántas subastas tienen un solo oferente?"
        what="la parte de subastas inversas electrónicas con un solo oferente"
        unit="de las subastas inversas electrónicas tuvo un solo oferente"
        base={(y) => y.single_bidder_base}
        years={years}
        lastFull={lastFullIdx}
        notes={notes}
        series={(y) => y.pct_single_bidder}
      />
      <div>
        <MixChart years={years} notes={general} lastFull={lastFullIdx} />
        <ul className="mlegend mlegend--row" aria-label="Leyenda del gráfico de barras" style={{ marginTop: 14 }}>
          {MIX.map((m) => (
            <li key={m.key}>
              <svg width="30" height="20" viewBox="0 0 30 20" aria-hidden="true">
                <rect x="1.5" y="1.5" width="27" height="17" rx="5" fill={m.fill} stroke={INK} strokeWidth="2.5" />
              </svg>
              <span>
                <b>{m.label}</b>
              </span>
            </li>
          ))}
          <li className="muted small">De abajo hacia arriba: competitivos, directa, catálogo y otros.</li>
        </ul>
      </div>
      <LineChart
        id="con-senal"
        title="¿Qué parte de los procesos competitivos tiene señales?"
        what="la parte de procesos competitivos con al menos una señal"
        unit="de los procesos competitivos tuvo al menos una señal"
        base={(y) => y.competitive_processes}
        years={years}
        lastFull={lastFullIdx}
        notes={general}
        series={(y) => y.pct_with_signal}
      />
    </div>
  );
}
