import Link from "next/link";
import snapshot from "@/data/eval-snapshot.json";
import { fmtInt } from "@/lib/format";
import { Term } from "./Term";

const dec3 = new Intl.NumberFormat("es-EC", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

/** Figures from the generated snapshot (eval/backtest.json via `pnpm sync:eval`), never typed by hand. */
function backtestFigures() {
  const b = snapshot.backtest;
  if (!b || !b.auc || !Number.isFinite(b.auc.estimate)) return null;
  return {
    positives: fmtInt(b.n_positives),
    unlabelled: fmtInt(b.n_unlabelled),
    auc: dec3.format(b.auc.estimate),
    low: dec3.format(b.auc.low),
    high: dec3.format(b.auc.high),
    includesHalf: b.auc.low <= 0.5 && b.auc.high >= 0.5,
  };
}

/** The evaluation with its figures, for the methodology page. Same numbers as docs/EVALUATION.md. */
export function EvaluationText() {
  const f = backtestFigures();
  if (!f) return <p>La evaluación no está disponible en esta compilación.</p>;
  return (
    <>
      <p>
        Probamos si el puntaje pone más arriba a las empresas del <Term t="listado de empresas fantasmas del SRI">listado de «empresas fantasmas»</Term> que publicó el SRI: {f.positives}{" "}
        empresas del listado que ganaron procesos públicos, frente a {f.unlabelled} empresas adjudicatarias que no figuran en él, sin usar las reglas que dependen del propio
        listado. El <Term t="AUC">AUC</Term> fue {f.auc} y su <Term t="intervalo de confianza">intervalo de confianza</Term> del 95 % va de {f.low} a {f.high}
        {f.includesHalf ? "; el intervalo incluye 0,5, que es el nivel del azar" : ""}.
      </p>
      <ul className="limits" style={{ marginTop: 14 }}>
        <li>
          <b>AUC:</b> una medida de 0 a 1. 0,5 equivale a tirar una moneda; 1 sería acertar siempre.
        </li>
        <li>
          <b>Intervalo de confianza:</b> el rango en el que probablemente está la cifra real. Aquí es ancho porque los casos son pocos.
        </li>
      </ul>
      <p style={{ marginTop: 14 }}>
        La evidencia disponible no muestra que el puntaje distinga a los proveedores del listado. Por eso los indicadores son medidas descriptivas de transparencia, no predictores
        validados. Con tan pocos casos la prueba tampoco descarta un efecto modesto, y figurar en el listado no equivale a un contrato problemático.
      </p>
    </>
  );
}

/** The home-page block: headline, one key figure, short sentences on a light card, the link. Figures come from the snapshot. */
export function EvaluationBlock() {
  const f = backtestFigures();
  return (
    <div className="eval">
      <div>
        <h2 className="eval__h" id="ev-h">
          ¿El puntaje predice algo? Lo probamos{f?.includesHalf ? <>, <em>y no.</em></> : <em>.</em>}
        </h2>
        {f && f.includesHalf ? (
          <p className="eval__figure">
            <span className="eval__num">
              {f.positives}
              <small>frente a</small>
              {f.unlabelled}
            </span>
            <span className="eval__cap" style={{ display: "block" }}>
              empresas señaladas por el SRI frente a otras empresas ganadoras: el puntaje las ordenó igual que el azar.
            </span>
          </p>
        ) : null}
      </div>
      <div className="eval__card">
        {f && f.includesHalf ? (
          <>
            <p>
              Miramos si Veedor les ponía puntajes más altos a las {f.positives} empresas señaladas por el SRI que a las otras {f.unlabelled} empresas ganadoras. No lo hizo: acertó igual que el azar.
            </p>
            <p>Por eso un puntaje alto no significa que haya algo malo: solo te dice dónde mirar primero.</p>
          </>
        ) : (
          <p>Un puntaje alto no significa que haya algo malo: solo te dice dónde mirar primero. Los detalles de la prueba están en la metodología.</p>
        )}
        <div className="actions">
          <EvaluationLink className="btn btn--ink btn--sm" />
        </div>
      </div>
    </div>
  );
}

/** One plain sentence for the home page (large text on terracotta). */
export function EvaluationSentence() {
  const f = backtestFigures();
  if (!f) return <>La evaluación no está disponible en esta compilación.</>;
  return (
    <>
      Lo probamos con {f.positives} empresas del listado del SRI frente a {f.unlabelled} que no figuran en él: el puntaje no{" "}
      {f.includesHalf ? "mostró distinguirlas mejor que el azar" : "las distinguió como se esperaba"} (AUC {f.auc}, con un intervalo de {f.low} a{" "}
      {f.high}; 0,5 es el azar). Por eso los indicadores describen, no predicen.
    </>
  );
}

export function EvaluationLink({ className = "link" }: { className?: string }) {
  return (
    <Link href="/metodologia#evaluacion" className={className}>
      Ver la prueba completa
    </Link>
  );
}
