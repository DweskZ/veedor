import { evidenceLabel, fmtEvidence, fmtNum } from "@/lib/format";
import { SourceMarker } from "./Provenance";
import { FALLBACK_COPY, SIGNAL_COPY } from "@/lib/signal-copy";
import type { FiredSignal, SignalDef } from "@/lib/types";

/** Observed value against its threshold on a shared scale. Decorative: the numbers are the content. */
function Comparison({ value, threshold }: { value: number; threshold: number }) {
  const max = Math.max(Math.abs(value), Math.abs(threshold), 1e-9) * 1.15;
  const pos = (n: number) => `${Math.round(Math.min(100, Math.max(0, (Math.abs(n) / max) * 100)) * 10) / 10}%`;
  return (
    <div className="meter">
      <div className="meter__track" aria-hidden="true">
        <div className="meter__fill" style={{ width: pos(value) }} />
        <div className="meter__mark" style={{ left: pos(threshold) }} />
      </div>
    </div>
  );
}

/**
 * One signal, answering three questions in plain words: what was observed, why it can matter,
 * and how it can be perfectly normal. Context signals are quieter and do not add points.
 */
export function SignalCard({ signal, def, quiet = false }: { signal: FiredSignal; def: SignalDef | undefined; quiet?: boolean }) {
  const evidence = Object.entries(signal.evidence);
  const copy = SIGNAL_COPY[signal.code] ?? FALLBACK_COPY;
  const label = signal.label_es ?? def?.label_es ?? signal.code;
  const hasDetails = evidence.length > 0 || Boolean(def?.threshold_rule_es);
  return (
    <article id={`sig-${signal.code}`} className={`sig ${quiet ? "sig--quiet" : ""}`}>
      <header className="sig__head">
        {quiet ? <p className="tag">Solo contexto · no suma puntos</p> : null}
        <h3 className="h3">{label}</h3>
        <dl className="sig__vals">
          <div>
            <dt>Valor observado</dt>
            <dd>
              {fmtNum(signal.value)}
              <SourceMarker keys={[`signal.${signal.code}`]} />
            </dd>
          </div>
          <div>
            <dt>Umbral de la regla</dt>
            <dd>{fmtNum(signal.threshold)}</dd>
          </div>
        </dl>
        {signal.value != null && signal.threshold != null ? <Comparison value={signal.value} threshold={signal.threshold} /> : null}
      </header>
      <div className="sig__qa">
        {def?.description_es ? (
          <p>
            <b>Qué se observó.</b> {def.description_es}
          </p>
        ) : null}
        <p>
          <b>Por qué puede importar.</b> {copy.why}
        </p>
        <p>
          <b>Cómo puede ser perfectamente normal.</b> {copy.normal}
        </p>
      </div>
      {hasDetails ? (
        <details>
          <summary>
            Regla y datos usados{evidence.length ? ` (${evidence.length})` : ""}
          </summary>
          <div className="ev-wrap">
            {def?.threshold_rule_es ? (
              <p className="sig__rule">
                <b>Regla.</b> {def.threshold_rule_es}
              </p>
            ) : null}
            {evidence.length ? (
              <table className="ev">
                <caption className="sr-only">Evidencia de la señal {label}</caption>
                <tbody>
                  {evidence.map(([k, v]) => (
                    <tr key={k}>
                      <th scope="row">{evidenceLabel(k)}</th>
                      <td>{fmtEvidence(k, v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        </details>
      ) : null}
    </article>
  );
}
