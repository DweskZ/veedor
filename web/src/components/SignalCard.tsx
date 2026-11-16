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
      <p className="meter__cap">Barra: lo observado. Marca vertical: el umbral de la regla.</p>
    </div>
  );
}

/**
 * One signal, answering three questions in plain words: what was observed, why it can matter,
 * and how it can be perfectly normal. Context signals are quieter and do not add points.
 */
export function SignalCard({ signal, def, quiet = false, quoteHref }: { signal: FiredSignal; def: SignalDef | undefined; quiet?: boolean; quoteHref?: string }) {
  const evidence = Object.entries(signal.evidence);
  const copy = SIGNAL_COPY[signal.code] ?? FALLBACK_COPY;
  const label = signal.label_es ?? def?.label_es ?? signal.code;
  return (
    <article id={`sig-${signal.code}`} className={`sig ${quiet ? "sig--quiet" : ""}`}>
      <header className="sig__head">
        {quiet ? <p className="tag">Solo contexto · no suma puntos</p> : null}
        <h3 className="h3">{label}</h3>
        <p className="sig__code">{signal.code}</p>
      </header>
      <div className="sig__qa">
        <div className="sig__q">
          <h4>Qué se observó</h4>
          {def?.description_es ? <p>{def.description_es}</p> : null}
          <dl className="sig__vals">
            <div>
              <dt>Valor observado</dt>
              <dd>{fmtNum(signal.value)}<SourceMarker keys={[`signal.${signal.code}`]} /></dd>
            </div>
            <div>
              <dt>Umbral de la regla</dt>
              <dd>{fmtNum(signal.threshold)}</dd>
            </div>
          </dl>
          {def?.threshold_rule_es ? <p className="muted small" style={{ marginTop: 8 }}>Regla: {def.threshold_rule_es}</p> : null}
          {signal.value != null && signal.threshold != null ? <Comparison value={signal.value} threshold={signal.threshold} /> : null}
        </div>
        <div className="sig__q">
          <h4>Por qué puede importar</h4>
          <p>{copy.why}</p>
        </div>
        <div className="sig__q">
          <h4>Cómo puede ser perfectamente normal</h4>
          <p>{copy.normal}</p>
        </div>
      </div>
      {quoteHref ? (
        <p className="sig__quote">
          <a href={quoteHref} className="inline-link">
            Ver la cita de la fuente relacionada
          </a>
        </p>
      ) : null}
      {evidence.length ? (
        <details>
          <summary>Evidencia usada ({evidence.length} campos)</summary>
          <div className="ev-wrap">
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
          </div>
        </details>
      ) : null}
    </article>
  );
}
