import validation from "@/data/validation.json";
import {
  buildFigures,
  circular,
  compositeWithoutCircular,
  fmtCount,
  fmtDec2,
  fmtPpAbs,
  fmtPpRange,
  fmtPpSigned,
  forestRows,
  primary,
  SIGNAL_LABEL,
  verdictOf,
  type PeriodData,
  type SignalRow,
  type ValidationData,
  type Verdict,
} from "@/lib/validation";
import { Term } from "./Term";

const DATA = validation as unknown as ValidationData;

const READING: Record<Verdict, string> = {
  lower: "Menos ahorro",
  higher: "Más ahorro",
  none: "Sin diferencia clara",
  untestable: "No se pudo probar",
};

/** Plain wording of one cell: effect and interval, or why there is none. */
function Cell({ s }: { s: SignalRow }) {
  if (verdictOf(s) === "untestable" || !s.adjusted)
    return (
      <>
        <span className="muted">Sin cifras</span>
        <span className="cell-sub">{fmtCount(s.n_with)} procesos marcados</span>
      </>
    );
  return (
    <>
      <b>{fmtPpSigned(s.adjusted.effect_pp)}</b>
      <span className="cell-sub">
        {fmtPpRange(s.adjusted)} · {fmtCount(s.n_with)} con la señal
      </span>
    </>
  );
}

function SignalsTable({ rows, caption }: { rows: { explore: SignalRow; confirm: SignalRow }[]; caption: string }) {
  return (
    <div className="tbl-wrap" tabIndex={0} role="region" aria-label={`${caption} (tabla desplazable)`}>
      <table className="tbl vtbl">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Señal</th>
            <th scope="col" className="r">
              Exploración {DATA.explore.years[0]}–{DATA.explore.years[1]}
            </th>
            <th scope="col" className="r">
              Confirmación {DATA.confirm.years[0]}–{DATA.confirm.years[1]}
            </th>
            <th scope="col">Lectura (confirmación)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ explore, confirm }) => (
            <tr key={confirm.signal}>
              <th scope="row">{SIGNAL_LABEL[confirm.signal] ?? confirm.signal}</th>
              <td className="r">
                <Cell s={explore} />
              </td>
              <td className="r">
                <Cell s={confirm} />
              </td>
              <td>{READING[verdictOf(confirm)]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const pair = (rows: SignalRow[], other: PeriodData) =>
  rows.map((c) => ({ confirm: c, explore: other.signals.find((s) => s.signal === c.signal)! })).filter((r) => r.explore);

/**
 * Forest plot of the confirmed effect per signal: dot = estimate, line = 95 % interval, dashed line = zero (no difference).
 * Static SVG (readable without JavaScript); every value is also printed in text above each row and in the table below.
 */
export function ForestPlot() {
  const rows = forestRows(DATA);
  if (rows.length === 0) return null;
  const W = 360;
  const L = 16;
  const R = 344;
  const lo = Math.floor(Math.min(...rows.map((r) => r.ci_low_pp))) - 1;
  const hi = Math.ceil(Math.max(0, ...rows.map((r) => r.ci_high_pp))) + 1;
  const x = (v: number) => L + ((v - lo) / (hi - lo)) * (R - L);
  const ROW = 52;
  const top = 34;
  const H = top + rows.length * ROW + 44;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / 2) * 2; t <= hi; t += 2) ticks.push(t);
  const summary = rows
    .map((r) => `${r.label}: ${fmtPpSigned(r.effect_pp)} puntos, intervalo de ${fmtPpSigned(r.ci_low_pp)} a ${fmtPpSigned(r.ci_high_pp)}`)
    .join(". ");
  return (
    <figure className="forest">
      <figcaption className="forest__cap">
        <b>Diferencia de ahorro con la señal, en puntos porcentuales del presupuesto</b> · {DATA.confirm.years[0]}–{DATA.confirm.years[1]}. El punto es la estimación; la línea, el intervalo del 95 %.
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Gráfico de la diferencia de ahorro por señal. ${summary}.`} className="forest__svg">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top - 6} y2={H - 38} stroke="#cadbfb" strokeWidth="1" />
            <text x={x(t)} y={H - 22} textAnchor="middle" fontSize="11" fontWeight="700" fill="#5b6384">
              {fmtPpSigned(t).replace(/,0$/, "").replace("+", "")}
            </text>
          </g>
        ))}
        <line x1={x(0)} x2={x(0)} y1={top - 10} y2={H - 38} stroke="#1a1f36" strokeWidth="2" strokeDasharray="5 4" />
        <text x={x(0) + 4} y={top - 14} fontSize="11" fontWeight="800" fill="#1a1f36">
          0 = sin diferencia
        </text>
        {rows.map((r, i) => {
          const y = top + i * ROW;
          const low = r.verdict === "lower";
          return (
            <g key={r.code}>
              <text x={L} y={y + 12} fontSize="12" fontWeight="800" fill="#1a1f36">
                {r.label}
              </text>
              <text x={L} y={y + 27} fontSize="12" fontWeight="600" fill="#1a1f36">
                {fmtPpSigned(r.effect_pp)} ({fmtPpSigned(r.ci_low_pp)} a {fmtPpSigned(r.ci_high_pp)})
              </text>
              <line x1={x(r.ci_low_pp)} x2={x(r.ci_high_pp)} y1={y + 38} y2={y + 38} stroke="#1a1f36" strokeWidth="3" strokeLinecap="round" />
              <circle cx={x(r.effect_pp)} cy={y + 38} r="6" fill={low ? "#d9480f" : "#ffffff"} stroke="#1a1f36" strokeWidth="2.5" />
            </g>
          );
        })}
        <text x={L} y={H - 4} fontSize="11" fontWeight="700" fill="#5b6384">
          ← menos ahorro
        </text>
        <text x={R} y={H - 4} fontSize="11" fontWeight="700" fill="#5b6384" textAnchor="end">
          más ahorro →
        </text>
      </svg>
      <p className="forest__key small muted">Punto relleno: el intervalo queda del lado de menos ahorro. Punto vacío: el intervalo incluye el cero.</p>
    </figure>
  );
}

/** The full "Validación" section of /metodologia. Same figures as the home block, with intervals. */
export function ValidationSection() {
  const f = buildFigures(DATA);
  const confirmPrimary = primary(DATA.confirm);
  const circ = pair(circular(DATA.confirm), DATA.explore);
  const comp = compositeWithoutCircular(DATA.confirm);
  const compExplore = compositeWithoutCircular(DATA.explore);
  const lowerOnes = confirmPrimary.filter((s) => verdictOf(s) === "lower");
  const survives = lowerOnes.length > 0 && lowerOnes.every((s) => (s.adjusted?.p_holm ?? 1) < 0.05);
  const notTestable = confirmPrimary.filter((s) => verdictOf(s) === "untestable");
  const recurring = confirmPrimary.find((s) => s.signal === "RECURRING_COBIDDERS");
  const l = f.list;
  return (
    <div className="stack vsec">
      <div className="card">
        <div className="prose">
          <p>
            Para saber si el puntaje dice algo hicimos dos pruebas distintas. Las dos se escribieron con su plan antes de mirar los resultados, y las dos describen el conjunto de los datos: ninguna dice nada de un proceso, una entidad o una
            empresa en particular.
          </p>
          <p>
            <b>Prueba 1.</b> ¿El puntaje pone más arriba a las empresas del listado de «empresas fantasmas» del SRI? Resultado: <b>no concluyente</b>.
            <br />
            <b>Prueba 2.</b> ¿Los procesos con una señal terminan ahorrando menos frente al presupuesto? Resultado: <b>sí, pero poco</b>, y no con todas las señales.
          </p>
        </div>
      </div>

      <div className="card">
        <h3 className="h3">Prueba 2 · Contra el ahorro frente al presupuesto</h3>
        <div className="prose" style={{ marginTop: 14 }}>
          <p>
            El <Term t="ahorro frente al presupuesto">ahorro</Term> es cuánto menos que el <Term t="presupuesto referencial">presupuesto referencial</Term> terminó pagando el Estado: 1 menos el monto adjudicado dividido por el presupuesto.
            Solo cuenta en procesos competitivos que tienen las dos cifras. Comparamos los procesos con una señal contra procesos parecidos sin ella: mismo método y año, mismo tipo de producto, misma provincia y presupuesto
            similar.
          </p>
          <p>
            Exploramos entre {f.explore.years} ({f.explore.n} procesos) y confirmamos entre {f.confirm.years} ({f.confirm.n} procesos de {f.confirm.buyers} entidades; 2026 es un año incompleto). Lo que decide qué decimos es la
            confirmación. Los efectos se miden en puntos porcentuales del presupuesto: un valor negativo significa menos ahorro con la señal. El intervalo es el rango en el que probablemente está la cifra real.
          </p>
        </div>
        <ForestPlot />
        <h4 className="h4" style={{ marginTop: 24 }}>
          Señales que se pudieron comparar, en cifras
        </h4>
        <SignalsTable rows={pair(confirmPrimary, DATA.explore)} caption="Efecto de cada señal sobre el ahorro, en puntos porcentuales, con su intervalo del 95 %, en el período de exploración y en el de confirmación" />
        <ul className="limits" style={{ marginTop: 18 }}>
          {survives ? (
            <li>
              {lowerOnes.length === 1 ? "La diferencia de la señal «con menos ahorro» sigue" : `Las ${lowerOnes.length} diferencias hacia menos ahorro siguen`} siendo distintas de cero aunque se corrija por haber probado varias señales a la vez.
            </li>
          ) : null}
          {recurring && verdictOf(recurring) === "none" ? (
            <li>
              <b>{SIGNAL_LABEL.RECURRING_COBIDDERS}:</b> en la confirmación no hay diferencia clara; en la exploración había incluso algo más de ahorro. No respalda la idea de que esta señal marque menos competencia.
            </li>
          ) : null}
          {notTestable.length ? (
            <li>
              <b>{notTestable.length === 2 ? "Dos señales" : `${notTestable.length} señales`} no se pudieron probar</b> ({notTestable.map((s) => SIGNAL_LABEL[s.signal] ?? s.signal).join("; ")}): marcaron menos de {DATA.min_flagged} procesos o
              de {DATA.min_buyers} entidades, y con tan pocos casos no se puede estimar nada.
            </li>
          ) : null}
        </ul>

        {circ.length ? (
          <>
            <h4 className="h4" style={{ marginTop: 24 }}>
              Tres señales que se reportan aparte
            </h4>
            <p className="small" style={{ marginTop: 8, maxWidth: "46em" }}>
              {f.confirm.circularCount === 3 ? "Tres señales" : `${f.confirm.circularCount} señales`} usan el monto adjudicado en su propia definición. Su relación con el ahorro es en parte automática, así que no cuentan como evidencia y se muestran solo
              por completitud.
            </p>
            <div style={{ marginTop: 12 }}>
              <SignalsTable rows={circ} caption="Señales que usan el monto adjudicado en su definición, reportadas aparte" />
            </div>
          </>
        ) : null}

        {comp?.spearman && comp.effect_per_10_points_pp ? (
          <>
            <h4 className="h4" style={{ marginTop: 24 }}>
              El puntaje en conjunto
            </h4>
            <p className="small" style={{ marginTop: 8, maxWidth: "46em" }}>
              Armamos el puntaje sin esas tres señales y vimos cómo se relaciona con el ahorro en {f.confirm.years}. Los procesos con puntaje más alto tienden a estar entre los que ahorraron menos, pero la relación es débil: la
              correlación de rangos es {fmtDec2(comp.spearman.rho)} (intervalo {fmtDec2(comp.spearman.ci_low)} a {fmtDec2(comp.spearman.ci_high)}; 0 sería ninguna relación y −1, una perfecta). Por cada 10 puntos más de puntaje,
              el ahorro es unos {fmtPpAbs(comp.effect_per_10_points_pp.effect_pp)} puntos menor
              {compExplore?.effect_per_10_points_pp ? ` (en la exploración, ${fmtPpAbs(compExplore.effect_per_10_points_pp.effect_pp)})` : ""}.
            </p>
          </>
        ) : null}
      </div>

      <div className="card">
        <h3 className="h3">Prueba 1 · Contra el listado de «empresas fantasmas» del SRI</h3>
        <div className="prose" style={{ marginTop: 14 }}>
          <p>
            {l.official ? `El listado oficial del SRI tiene  contribuyentes, entre empresas y personas. ` : ""}Solo {l.positives} empresas de ese listado ganaron procesos públicos en los datos; las comparamos con {l.unlabelled} empresas adjudicatarias que no figuran en el listado,
            sin usar las reglas que dependen del propio listado. El <Term t="AUC">AUC</Term> fue {l.auc} y su <Term t="intervalo de confianza">intervalo de confianza</Term> del 95 % va de {l.aucLow} a {l.aucHigh}
            {l.includesHalf ? "; incluye 0,5, que es el nivel del azar" : ""}.
          </p>
          <p>
            <b>Por eso decimos «no concluyente», no «negativo».</b> Con solo {l.positives} casos la prueba tiene poca potencia: {l.detectable ? `solo habría detectado una separación grande, un AUC de alrededor de ${l.detectable} o más` : "solo habría detectado una separación muy grande"}. Si el
            puntaje separa un poco a esas empresas, esta prueba no lo habría notado. Buscamos un listado oficial más amplio{l.checkedOn ? ` (revisado el ${l.checkedOn})` : ""} y no existe: el que hay es el que usamos.
          </p>
        </div>
      </div>

      <div className="card card--quiet">
        <h3 className="h3">Lo que esto no significa</h3>
        <ul className="limits" style={{ marginTop: 14 }}>
          <li>Ahorrar menos no es una irregularidad. Con un solo oferente casi no hay competencia por el precio, así que un ahorro menor es casi lo que se espera: no es una prueba independiente de nada.</li>
          <li>La diferencia mediana es mucho menor que la promedio porque muchos procesos con la señal ahorran exactamente cero. Las cifras de arriba son promedios ajustados.</li>
          <li>Describe el conjunto de los datos, no un proceso: ningún proceso, entidad o empresa es sospechoso por lo que dice este análisis.</li>
          <li>La asociación no prueba una causa, y las pruebas no cambian ninguna regla ni peso del puntaje.</li>
          <li>El análisis completo, con su plan y sus desviaciones, está en el archivo <span className="num">docs/VALIDATION.md</span> del repositorio de Veedor.</li>
        </ul>
        <p className="muted small" style={{ marginTop: 12 }}>
          Muestra total: {fmtCount(DATA.sample)} procesos competitivos con presupuesto y adjudicación. Cifras copiadas de <span className="num">eval/validation.json</span> con <span className="num">pnpm sync:validation</span>.
        </p>
      </div>
    </div>
  );
}
