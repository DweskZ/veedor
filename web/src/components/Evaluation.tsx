import Link from "next/link";
import snapshot from "@/data/eval-snapshot.json";
import { fmtInt } from "@/lib/format";

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

/** The evaluation in plain words, for the methodology page. Same numbers as docs/EVALUATION.md. */
export function EvaluationText() {
  const f = backtestFigures();
  if (!f) return <p>La evaluación no está disponible en esta compilación.</p>;
  return (
    <>
      <p>
        Probamos si el puntaje pone más arriba a las empresas del listado de «empresas fantasmas» que publicó el SRI: {f.positives}{" "}
        empresas del listado que ganaron procesos públicos, frente a {f.unlabelled} empresas adjudicatarias que no figuran en él, sin
        usar las reglas que dependen del propio listado. El AUC fue {f.auc} (intervalo de confianza del 95 %: {f.low} a {f.high})
        {f.includesHalf ? "; el intervalo incluye 0,5, que es el nivel del azar" : ""}.
      </p>
      <p>
        La evidencia disponible no muestra que el puntaje distinga a los proveedores del listado. Por eso los indicadores son medidas
        descriptivas de transparencia, no predictores validados. Con tan pocos casos la prueba tampoco descarta un efecto modesto, y
        figurar en el listado no equivale a un contrato problemático.
      </p>
    </>
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
