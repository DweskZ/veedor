import validation from "@/data/validation.json";
import { getThresholds } from "@/lib/api";
import { fmtInt, fmtOne, fmtThresholdCategory, fmtUsd } from "@/lib/format";
import type { PooledThreshold, ValidationData } from "@/lib/validation";
import type { ThresholdRow, ThresholdStats } from "@/lib/types";
import { Term } from "./Term";
import { ErrorState } from "./ui";

const POOLED = (validation as unknown as ValidationData).thresholds;

/** Column order for the by-year table; a code not listed here is appended. */
const ORDER = [
  "GS_INFIMA_SIE",
  "GS_MENOR_COTIZACION",
  "GS_COTIZACION_LICITACION",
  "W_INFIMA_LICITACION",
  "W_MENOR_COTIZACION",
  "W_COTIZACION_LICITACION",
  "C_INFIMA_CONCURSO",
  "C_LISTA_CORTA_CONCURSO",
];

const EXCLUDED_COPY: Record<string, string> = {
  "2025": "Las reglas cambiaron a mitad de año (hasta junio regía la tabla por coeficientes; después, montos fijos de 10.000 dólares). Se deja fuera en vez de mezclar dos regímenes.",
};

interface Column {
  code: string;
  category: string | null;
  below: string | null;
  above: string | null;
}

function columnsOf(items: ThresholdRow[]): Column[] {
  const seen = new Map<string, Column>();
  for (const r of items) if (!seen.has(r.code)) seen.set(r.code, { code: r.code, category: fmtThresholdCategory(r.category), below: r.procedure_below, above: r.procedure_above });
  const rank = (c: string) => (ORDER.includes(c) ? ORDER.indexOf(c) : ORDER.length);
  return [...seen.values()].sort((a, b) => rank(a.code) - rank(b.code));
}

const label = (c: Column | undefined, code: string) => (c ? `${c.below ?? "?"} → ${c.above ?? "?"}` : code);

/** Bar chart, static SVG: budgets in the 5 % just below and just above each analysable threshold, with the count a smooth curve would give. */
function BunchingChart({ rows, cols }: { rows: PooledThreshold[]; cols: Map<string, Column> }) {
  const W = 360;
  const L = 16;
  const BAR_MAX = 190;
  const G = 74;
  const top = 8;
  const H = top + rows.length * G + 6;
  const max = Math.max(...rows.flatMap((r) => [r.budget.observed_below ?? 0, r.budget.observed_above ?? 0, r.budget.expected_below ?? 0]));
  const w = (v: number) => (v / max) * BAR_MAX;
  const summary = rows
    .map((r) => `${label(cols.get(r.threshold_code), r.threshold_code)}: ${fmtInt(r.budget.observed_below ?? 0)} justo por debajo y ${fmtInt(r.budget.observed_above ?? 0)} justo por encima`)
    .join(". ");
  return (
    <figure className="forest bunch">
      <figcaption className="forest__cap">
        <b>Presupuestos justo por debajo y justo por encima de cada umbral</b>, años {POOLED.pooled[0]?.years[0]}–{POOLED.pooled[0]?.years.at(-1)} juntos. «Justo» es el 5 % del monto a cada lado. La marca vertical es lo que daría una curva suave.
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Gráfico de barras. ${summary}.`} className="forest__svg">
        {rows.map((r, i) => {
          const y = top + i * G;
          const col = cols.get(r.threshold_code);
          const below = r.budget.observed_below ?? 0;
          const above = r.budget.observed_above ?? 0;
          const exp = r.budget.expected_below ?? 0;
          return (
            <g key={r.threshold_code}>
              <text x={L} y={y + 12} fontSize="12" fontWeight="800" fill="#1a1f36">
                {col?.category ? `${col.category[0].toUpperCase()}${col.category.slice(1)}: ` : ""}
                {label(col, r.threshold_code)}
              </text>
              <rect x={L} y={y + 20} width={w(below)} height="15" fill="#d9480f" stroke="#1a1f36" strokeWidth="2" rx="2" />
              <line x1={L + w(exp)} x2={L + w(exp)} y1={y + 16} y2={y + 39} stroke="#1a1f36" strokeWidth="2.5" />
              <text x={L + Math.max(w(below), w(exp)) + 8} y={y + 32} fontSize="11" fontWeight="700" fill="#1a1f36">
                {fmtInt(below)} debajo (esperados {fmtInt(Math.round(exp))})
              </text>
              <rect x={L} y={y + 44} width={w(above)} height="15" fill="#cadbfb" stroke="#1a1f36" strokeWidth="2" rx="2" />
              <text x={L + w(above) + 8} y={y + 56} fontSize="11" fontWeight="700" fill="#1a1f36">
                {fmtInt(above)} encima
              </text>
            </g>
          );
        })}
      </svg>
      <p className="forest__key small muted">Barra de terracota: justo por debajo. Barra celeste: justo por encima. Los números están también en la tabla de abajo.</p>
    </figure>
  );
}

/** "Montos que cambian el procedimiento" for /tendencias. Context only: it never changes a score. */
export async function ThresholdTrends() {
  const r = await getThresholds().then(
    (v) => ({ ok: true as const, v }),
    () => ({ ok: false as const }),
  );
  if (!r.ok || r.v.items.length === 0)
    return (
      <section className="card trend thrs" aria-labelledby="thrs-t" id="umbrales">
        <h2 className="h3" id="thrs-t">
          Montos que cambian el procedimiento
        </h2>
        <ErrorState title="Los montos por año no están disponibles" detail="Todavía no podemos mostrar los umbrales. Los demás datos del sitio siguen disponibles." />
      </section>
    );
  return <ThresholdBody stats={r.v} />;
}

function ThresholdBody({ stats }: { stats: ThresholdStats }) {
  const cols = columnsOf(stats.items);
  const colMap = new Map(cols.map((c) => [c.code, c]));
  const years = [...new Set([...stats.items.map((i) => i.year), ...Object.keys(stats.excluded_years).map(Number)])].sort((a, b) => a - b);
  const cell = new Map(stats.items.map((i) => [`${i.year}|${i.code}`, i]));
  const pooled = POOLED.pooled.filter((p) => p.budget.status === "estimated" && p.budget.excess_pct != null);
  const allAbove = pooled.length > 0 && pooled.every((p) => (p.budget.excess_pct_ci?.[0] ?? -1) > 0);
  const caveats = [...new Set(stats.items.flatMap((i) => i.caveats))];
  const band = stats.band_pct != null ? fmtOne(stats.band_pct).replace(/,0$/, "") : "5";
  const y0 = pooled[0]?.years[0];
  const y1 = pooled[0]?.years.at(-1);

  return (
    <section className="card trend thrs" aria-labelledby="thrs-t" id="umbrales">
      <h2 className="h3" id="thrs-t">
        Montos que cambian el procedimiento
      </h2>
      <p className="trend__def">
        Cada año la ley fija <Term t="umbral de contratación">montos</Term> a partir de los cuales una compra debe seguir un procedimiento más exigente. Es contexto: no es una señal de riesgo y no cambia ningún puntaje.
      </p>
      <p className="trend__read">
        Hasta mediados de 2025 cada monto era una fracción fija del <Term t="presupuesto inicial del Estado (PIE)">presupuesto inicial del Estado</Term>; por eso cambiaba de un año a otro.
      </p>

      <h3 className="h4" style={{ marginTop: 20 }}>
        Los montos, año por año
      </h3>
      <div className="tbl-wrap" tabIndex={0} role="region" aria-label="Montos que cambian el procedimiento, por año (tabla desplazable)" style={{ marginTop: 10 }}>
        <table className="tbl thrs__tbl">
          <caption className="sr-only">Monto en dólares que separa dos procedimientos, por año y categoría. Cada columna indica el procedimiento de abajo y el de arriba del monto.</caption>
          <thead>
            <tr>
              <th scope="col">Año</th>
              {cols.map((c) => (
                <th scope="col" className="r" key={c.code}>
                  {c.category}
                  <span className="cell-sub">{label(c, c.code)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((y) => {
              const why = stats.excluded_years[String(y)];
              if (why)
                return (
                  <tr key={y}>
                    <th scope="row">{y}</th>
                    <td colSpan={cols.length} className="muted">
                      Excluido. {EXCLUDED_COPY[String(y)] ?? "El régimen cambió o no se pudo verificar."}
                    </td>
                  </tr>
                );
              return (
                <tr key={y}>
                  <th scope="row">{y}</th>
                  {cols.map((c) => {
                    const it = cell.get(`${y}|${c.code}`);
                    return (
                      <td className="r" key={c.code}>
                        {it ? (
                          <>
                            {fmtUsd(it.usd)}
                            {it.procedure_above !== c.above ? <span className="cell-sub">{it.procedure_above}</span> : null}
                          </>
                        ) : (
                          <span className="muted" aria-label="sin dato">
                            –
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        Fuente: publicaciones oficiales del SERCOP; cada año enlaza a la suya en el expediente de un proceso. Los años que no se pudieron verificar no se muestran.
      </p>

      {pooled.length ? (
        <>
          <h3 className="h4" style={{ marginTop: 28 }}>
            ¿Cuántos presupuestos quedan justo debajo de cada monto?
          </h3>
          <p className="small" style={{ marginTop: 8, maxWidth: "46em" }}>
            Contamos los presupuestos que caen en el {band} % justo por debajo y justo por encima de cada monto, y los comparamos con los que daría una curva suave ajustada al resto. Con los años {y0}–{y1} juntos, en{" "}
            {allAbove ? "los cinco umbrales analizables" : "algunos umbrales"} hay más presupuestos justo por debajo de lo que esa curva esperaría
            {allAbove ? ": el intervalo de cada uno queda por encima de cero" : ""}. El exceso va de {fmtOne(Math.min(...pooled.map((p) => p.budget.excess_pct!)))} % a {fmtOne(Math.max(...pooled.map((p) => p.budget.excess_pct!)))} %, según el monto.
          </p>
          <BunchingChart rows={pooled} cols={colMap} />
          <div className="tbl-wrap" tabIndex={0} role="region" aria-label="Presupuestos cerca de cada monto, observados y esperados (tabla desplazable)" style={{ marginTop: 16 }}>
            <table className="tbl thrs__tbl">
              <caption className="sr-only">Para cada monto: presupuestos observados y esperados justo por debajo, exceso con su intervalo del 95 % y presupuestos justo por encima</caption>
              <thead>
                <tr>
                  <th scope="col">Monto</th>
                  <th scope="col" className="r">Presupuestos cerca del monto</th>
                  <th scope="col" className="r">Justo por debajo: observados / esperados</th>
                  <th scope="col" className="r">Exceso (intervalo del 95 %)</th>
                  <th scope="col" className="r">Justo por encima: observados / esperados</th>
                </tr>
              </thead>
              <tbody>
                {pooled.map((p) => {
                  const c = colMap.get(p.threshold_code);
                  const b = p.budget;
                  return (
                    <tr key={p.threshold_code}>
                      <th scope="row">
                        {c?.category}
                        <span className="cell-sub">{label(c, p.threshold_code)}</span>
                      </th>
                      <td className="r">{fmtInt(b.n_window)}</td>
                      <td className="r">
                        {fmtInt(b.observed_below)} / {fmtInt(Math.round(b.expected_below ?? 0))}
                      </td>
                      <td className="r">
                        <b>{b.excess_pct != null ? `+${fmtOne(b.excess_pct)} %` : "–"}</b>
                        {b.excess_pct_ci ? <span className="cell-sub">{`+${fmtOne(b.excess_pct_ci[0])} % a +${fmtOne(b.excess_pct_ci[1])} %`}</span> : null}
                      </td>
                      <td className="r">
                        {fmtInt(b.observed_above)} / {fmtInt(Math.round(b.expected_above ?? 0))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <p className="thrs__plain">Esto no dice por qué las compras quedan donde quedan.</p>

      <aside className="trend__notes thrs__notes" aria-label="Ten en cuenta en esta sección">
        <p className="tag">Ten en cuenta</p>
        <ul>
          {stats.notes.filter((n) => !/^Es contexto/.test(n)).map((n) => (
            <li key={n}>{n}</li>
          ))}
          {stats.excluded_years["2025"] ? <li>El año 2025 queda fuera. {EXCLUDED_COPY["2025"]}</li> : null}
          {caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
          <li>
            Una curva suave no sabe que, justo en el monto, cambia el procedimiento. Ese cambio puede por sí solo doblar la distribución de presupuestos en ese punto, así que el tamaño del exceso no debe leerse al pie de la letra.
          </li>
          <li>Los años 2026 en adelante no se pueden analizar: todos los montos son de 10.000 dólares y las compras por debajo no están en los datos abiertos.</li>
        </ul>
      </aside>
    </section>
  );
}
