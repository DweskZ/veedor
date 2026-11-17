import type { ReactNode } from "react";
import { fmtOne, fmtThresholdCategory, fmtUsd, NA } from "@/lib/format";
import { findTerm } from "@/lib/glossary";
import type { ProcessThreshold } from "@/lib/types";
import { Icon } from "./Icon";
import { Term } from "./Term";

/** A procedure name with its glossary definition when there is one. */
const Proc = ({ name }: { name: string | null }): ReactNode => (name ? findTerm(name) ? <Term t={name}>{name.toLowerCase()}</Term> : name.toLowerCase() : "otro procedimiento");

/** Where the threshold comes from: the official publication the API cites. Printed as text and a link, so it reads without JavaScript. */
function Source({ t }: { t: ProcessThreshold }) {
  const url = t.threshold?.source_url;
  return (
    <p className="thr__src">
      <span className="tag">De dónde sale</span>{" "}
      {url ? (
        <a href={url} className="link" target="_blank" rel="noopener noreferrer">
          Montos de contratación {t.year ?? ""}, SERCOP <Icon name="external" size={16} />
          <span className="sr-only"> (se abre en una pestaña nueva)</span>
        </a>
      ) : (
        "Publicación oficial del SERCOP"
      )}
    </p>
  );
}

/** Keeps a label inside the scale when its marker is near an end. */
const edge = (pct: number) => (pct > 84 ? "thr__lb--end" : pct < 16 ? "thr__lb--start" : "");

/** Tiny horizontal scale: budget marker against the threshold marker. Decorative; the numbers are in the text. */
function Scale({ budget, threshold }: { budget: number; threshold: number }) {
  const max = Math.max(budget, threshold) * 1.08;
  const b = Math.max(1, Math.min(99, (budget / max) * 100));
  const t = Math.max(1, Math.min(99, (threshold / max) * 100));
  return (
    <div className="thr__scale" aria-hidden="true">
      <div className="thr__track" />
      <div className="thr__fill" style={{ width: `${b}%` }} />
      <span className="thr__mk thr__mk--b" style={{ left: `${b}%` }} />
      <span className="thr__mk thr__mk--t" style={{ left: `${t}%` }} />
      <span className={`thr__lb thr__lb--b ${edge(b)}`} style={{ left: `${b}%` }}>
        Presupuesto
      </span>
      <span className={`thr__lb thr__lb--t ${edge(t)}`} style={{ left: `${t}%` }}>
        Umbral
      </span>
    </div>
  );
}

/**
 * Context card for the Resumen tab: which procedure-amount threshold applies to this process and how far below it the budget sits.
 * Neutral on purpose: it is context, it is not a risk signal and it changes no score. Not applicable: one muted line (or nothing).
 */
export function ThresholdCard({ t }: { t: ProcessThreshold | null }) {
  if (!t) return null;
  if (!t.applicable || !t.threshold || t.budget == null)
    return t.reason ? (
      <p className="thr__none muted small" id="umbral">
        <span className="tag">Montos que cambian el procedimiento</span> {t.reason}
      </p>
    ) : null;
  const th = t.threshold;
  const below = t.distance_pct != null && t.distance_pct >= 0;
  const band = t.band_pct != null ? fmtOne(t.band_pct).replace(/,0$/, "") : null;
  return (
    <section className="thr" aria-labelledby="thr-h" id="umbral">
      <p className="tag">Contexto · no es una señal de riesgo</p>
      <h3 className="h4" id="thr-h">
        Monto que cambia el procedimiento
      </h3>
      <p className="thr__txt">
        Para {fmtThresholdCategory(th.category) ?? "esta categoría"} en {t.year ?? "este año"}, el <Term t="umbral de contratación">umbral</Term> es <b className="num">{fmtUsd(th.usd)}</b>. Por debajo se usa <Proc name={th.procedure_below} />; por encima,{" "}
        <Proc name={th.procedure_above} />. El <Term t="presupuesto referencial">presupuesto referencial</Term> de este proceso es <b className="num">{fmtUsd(t.budget)}</b>
        {t.distance_pct != null ? (
          <>
            , un <b className="num">{fmtOne(Math.abs(t.distance_pct))} %</b> {below ? "por debajo" : "por encima"} del umbral
          </>
        ) : null}
        .
      </p>
      <Scale budget={t.budget} threshold={th.usd} />
      {t.just_below ? (
        <p className="thr__jb">
          El presupuesto quedó a menos de {band ?? NA} % del monto que obliga a usar un procedimiento más exigente.
        </p>
      ) : null}
      {t.notes.length ? (
        <ul className="thr__notes small muted">
          {(t.just_below ? t.notes : t.notes.slice(0, 1)).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      <Source t={t} />
    </section>
  );
}

/** One line for the Datos tab, to sit in the facts list. */
export function ThresholdFact({ t }: { t: ProcessThreshold | null }) {
  if (!t || !t.applicable || !t.threshold) return null;
  const th = t.threshold;
  return (
    <div className="fact">
      <dt>
        <Term t="umbral de contratación">Umbral de contratación</Term>
      </dt>
      <dd>
        <span className="num">{fmtUsd(th.usd)}</span> ({fmtThresholdCategory(th.category)}, {t.year})
        {t.distance_pct != null ? <> · el presupuesto está un {fmtOne(Math.abs(t.distance_pct))} % {t.distance_pct >= 0 ? "por debajo" : "por encima"}</> : null}
        {t.just_below ? " · justo por debajo del umbral" : ""} · <a href="#umbral" className="inline-link">ver el contexto</a>
        <span className="cell-sub">Contexto, no una señal de riesgo ni parte del puntaje.</span>
      </dd>
    </div>
  );
}
