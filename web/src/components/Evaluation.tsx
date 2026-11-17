import Link from "next/link";
import validation from "@/data/validation.json";
import { buildFigures, type ValidationData } from "@/lib/validation";

/** Figures for the two tests, formatted from src/data/validation.json (generated from eval/validation.json). Never typed by hand. */
export const evaluationFigures = () => buildFigures(validation as unknown as ValidationData);

/**
 * The home-page block: two tests, two different answers, and one line on what neither means.
 * Body text sits on light cards in ink (white on terracotta fails contrast at body size); only the large headline is white.
 */
export function EvaluationBlock() {
  const f = evaluationFigures();
  const c = f.confirm;
  return (
    <div className="eval">
      <h2 className="eval__h" id="ev-h">
        ¿El puntaje dice algo? Dos pruebas, <em>dos respuestas distintas.</em>
      </h2>
      <div className="eval__cards">
        <article className="eval__card" aria-labelledby="ev-list">
          <p className="tag">Prueba 1 · contra la lista del SRI</p>
          <h3 className="eval__verdict" id="ev-list">
            No concluyente
          </h3>
          <p className="eval__big" aria-label={`${f.list.positives} de ${f.list.official ?? f.list.unlabelled}`}>
            {f.list.positives}
            {f.list.official ? <small> de {f.list.official}</small> : null}
          </p>
          <p>
            {f.list.official ? (
              <>
                El SRI publicó una lista de {f.list.official} contribuyentes, entre empresas y personas. Solo {f.list.positives} empresas de esa lista ganaron contratos en estos datos.
              </>
            ) : (
              <>Solo {f.list.positives} empresas de la lista del SRI ganaron contratos en estos datos.</>
            )}{" "}
            Con tan pocos casos la prueba solo habría notado una diferencia enorme. No alcanza para decir que el puntaje sirve ni que no sirve.
          </p>
        </article>
        <article className="eval__card" aria-labelledby="ev-save">
          <p className="tag">Prueba 2 · contra el ahorro</p>
          <h3 className="eval__verdict" id="ev-save">
            Sí, pero poco
          </h3>
          {c.single ? (
            <p className="eval__big" aria-label={`${c.single} puntos`}>
              {c.single}
              <small> puntos menos</small>
            </p>
          ) : null}
          <p>
            Miramos cuánto menos que el presupuesto de referencia terminó pagando el Estado. En el período {c.years}, los procesos con un solo oferente ahorraron unos {c.single} puntos porcentuales menos que procesos
            parecidos sin esa señal. Con plazo de ofertas corto fueron {c.short}; con proveedor nuevo, {c.fresh}. En conjunto, el puntaje se relaciona de forma débil con el ahorro.
          </p>
        </article>
      </div>
      <div className="eval__card eval__note">
        <p>
          <b>Qué no significa.</b> Ahorrar menos no es una falta: con menos oferentes es natural que el precio baje menos. Estas cifras describen el conjunto de los datos, no un proceso en particular. Un puntaje alto solo te
          dice dónde mirar primero.
        </p>
        <div className="actions">
          <EvaluationLink className="btn btn--ink btn--sm" />
        </div>
      </div>
    </div>
  );
}

export function EvaluationLink({ className = "link" }: { className?: string }) {
  return (
    <Link href="/metodologia#evaluacion" className={className}>
      Ver las dos pruebas completas
    </Link>
  );
}
