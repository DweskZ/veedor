import Link from "next/link";
import { Card } from "./ui";

/** Static copy. Numbers are taken verbatim from docs/EVALUATION.md (run 2026-11-16, seed 20260101). */
export function EvaluationText() {
  return (
    <>
      <p>
        Se probó si el puntaje coloca más arriba a las empresas del listado de &quot;empresas fantasmas&quot; publicado por el SRI:
        9 empresas listadas que ganaron procesos públicos frente a 19.837 empresas adjudicatarias no listadas, sin usar las reglas que
        dependen del propio listado. El AUC fue 0,474 (intervalo de confianza del 95 %: 0,315 a 0,661); el intervalo incluye 0,5, el
        nivel del azar.
      </p>
      <p>
        La evidencia disponible no muestra que el puntaje distinga a los proveedores del listado. Por eso los indicadores son medidas
        descriptivas de transparencia, no predictores validados. Con tan pocos casos la prueba tampoco descarta un efecto modesto, y
        figurar en el listado no equivale a un contrato problemático.
      </p>
    </>
  );
}

export function EvaluationCard() {
  return (
    <Card>
      <h3 className="font-semibold text-ink">Evaluación</h3>
      <div className="mt-2 space-y-2 text-sm leading-relaxed text-muted">
        <EvaluationText />
      </div>
      <p className="mt-3 text-sm">
        <Link href="/metodologia#evaluacion" className="text-accent underline underline-offset-2">
          Ver la metodología y la evaluación
        </Link>
      </p>
    </Card>
  );
}
