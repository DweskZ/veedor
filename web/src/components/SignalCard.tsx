import { evidenceLabel, fmtEvidence, fmtNum } from "@/lib/format";
import type { FiredSignal, SignalDef } from "@/lib/types";
import { Mono } from "./ui";

/** Observed value against its threshold on a shared scale. Decorative; the numbers are the content. */
function Comparison({ value, threshold }: { value: number; threshold: number }) {
  const max = Math.max(Math.abs(value), Math.abs(threshold), 1e-9) * 1.15;
  const pos = (n: number) => `${Math.min(100, Math.max(0, (Math.abs(n) / max) * 100))}%`;
  return (
    <div className="mt-3">
      <div className="relative h-2 rounded-sm bg-surface-2" aria-hidden="true">
        <div className="absolute inset-y-0 left-0 rounded-sm bg-accent" style={{ width: pos(value) }} />
        <div className="absolute -inset-y-1 w-0.5 bg-ink" style={{ left: pos(threshold) }} />
      </div>
      <p className="mt-1.5 text-xs text-muted">
        Barra: valor observado. Línea: umbral de la regla.
      </p>
    </div>
  );
}

export function SignalCard({ signal, def, quiet = false }: { signal: FiredSignal; def: SignalDef | undefined; quiet?: boolean }) {
  const evidence = Object.entries(signal.evidence);
  return (
    <article className={`rounded-lg p-5 ${quiet ? "border border-dashed border-line" : "border border-line bg-surface"}`}>
      <header>
        <h3 className={`text-lg font-semibold ${quiet ? "text-muted" : "text-ink"}`}>{signal.label_es ?? def?.label_es ?? signal.code}</h3>
        <p className="mt-0.5 text-xs text-muted">
          <Mono>{signal.code}</Mono>
        </p>
      </header>
      {def?.description_es ? <p className="mt-3 text-sm leading-relaxed text-ink">{def.description_es}</p> : null}
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted">Valor observado</dt>
          <dd className="font-mono text-base text-ink">{fmtNum(signal.value)}</dd>
        </div>
        <div>
          <dt className="text-muted">Umbral</dt>
          <dd className="font-mono text-base text-ink">{fmtNum(signal.threshold)}</dd>
        </div>
        <div>
          <dt className="text-muted">Regla</dt>
          <dd className="text-ink">{def?.threshold_rule_es ?? "No disponible"}</dd>
        </div>
      </dl>
      {signal.value != null && signal.threshold != null ? <Comparison value={signal.value} threshold={signal.threshold} /> : null}
      {evidence.length ? (
        <details className="mt-4" open>
          <summary className="cursor-pointer text-sm font-medium text-ink">Evidencia ({evidence.length} campos)</summary>
          <table className="mt-2 w-full text-sm">
            <caption className="sr-only">Evidencia de la señal {signal.label_es ?? def?.label_es ?? signal.code}</caption>
            <tbody>
              {evidence.map(([k, v]) => (
                <tr key={k} className="border-t border-line">
                  <th scope="row" className="w-1/2 py-1.5 pr-3 text-left font-normal text-muted">
                    {evidenceLabel(k)}
                  </th>
                  <td className="py-1.5 font-mono text-ink">{fmtEvidence(k, v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
    </article>
  );
}
