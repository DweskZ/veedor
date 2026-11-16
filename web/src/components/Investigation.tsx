import Link from "next/link";
import { fmtDateTime, fmtInt, NA } from "@/lib/format";
import {
  DECIDERS,
  DISPATCH_REASONS,
  elapsedMs,
  fmtDuration,
  FACT_LABELS,
  isModelAssisted,
  OUTCOME_REASONS,
  outcomeOf,
  SOURCES,
  SPECIALISTS,
  type Outcome,
} from "@/lib/investigation";
import type { Investigation, InvestigationLookup, InvestigationSpecialist } from "@/lib/types";
import { Card, Mono } from "./ui";

const specName = (id: string) => SPECIALISTS[id]?.name ?? id;

const TONE_STYLE: Record<Outcome["tone"], { style?: React.CSSProperties; className: string; icon: string }> = {
  ok: { className: "border-line bg-surface-2 text-ink", icon: "✓" },
  failed: { className: "border-transparent", style: { background: "var(--risk-2-bg)", color: "var(--risk-2-fg)" }, icon: "✕" },
  skipped: { className: "border-dashed border-line text-muted", icon: "–" },
};

function OutcomeChip({ outcome, reason }: { outcome: string; reason: string | null }) {
  const o = outcomeOf(outcome);
  const t = TONE_STYLE[o.tone];
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <span className={`inline-flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 text-xs ${t.className}`} style={t.style}>
        <span aria-hidden="true">{t.icon}</span>
        {o.label}
      </span>
      {reason && o.tone !== "ok" ? <span className="text-xs text-muted">{OUTCOME_REASONS[reason] ?? reason}</span> : null}
    </span>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  );
}

function RunSummary({ inv }: { inv: Investigation }) {
  const assisted = isModelAssisted(inv);
  const u = inv.model_usage;
  const el = elapsedMs(inv);
  const failed = inv.lookups.filter((l) => outcomeOf(l.outcome).tone === "failed").length;
  const skipped = inv.lookups.filter((l) => outcomeOf(l.outcome).tone === "skipped").length;
  return (
    <Card>
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Modo de la ejecución">
          <span className="font-medium">{assisted ? "Asistida por modelo" : "Política determinista"}</span>
          <span className="block text-xs text-muted">
            {assisted
              ? "El modelo ordena especialistas y acciones entre opciones cerradas; no redacta ni pasa argumentos."
              : "Sin modelo: el orden sale de una tabla fija según las señales."}
          </span>
        </Stat>
        <Stat label="Consultas">
          <span className="font-mono">{fmtInt(inv.lookups.length)}</span>
          <span className="block text-xs text-muted">
            {failed ? `${fmtInt(failed)} sin respuesta de la fuente` : "Todas respondieron o se omitieron"}
            {skipped ? ` · ${fmtInt(skipped)} omitida${skipped === 1 ? "" : "s"}` : ""}
          </span>
        </Stat>
        <Stat label="Duración">
          <span className="font-mono">{fmtDuration(el)}</span>
          <span className="block text-xs text-muted">{inv.finished_at ? fmtDateTime(inv.finished_at) : NA}</span>
        </Stat>
        <Stat label="Uso del modelo">
          {u && u.calls > 0 ? (
            <>
              <span className="font-mono">{fmtInt(u.calls)}</span> llamadas
              <span className="block text-xs text-muted">
                {u.model ? <Mono>{u.model}</Mono> : null}
                {u.model ? " · " : ""}
                {fmtInt(u.prompt_tokens)} tokens de entrada, {fmtInt(u.completion_tokens)} de salida
                {u.invalid_choices ? ` · ${fmtInt(u.invalid_choices)} elecciones inválidas` : ""}
              </span>
            </>
          ) : (
            <>
              <span className="font-mono">0</span> llamadas
              <span className="block text-xs text-muted">No se usó ningún modelo</span>
            </>
          )}
        </Stat>
      </dl>
      <p className="mt-4 border-t border-line pt-3 text-sm text-muted">
        Las consultas son de solo lectura. No se consultan registros de personas naturales y no se almacenan ni se muestran datos de personas naturales.
      </p>
    </Card>
  );
}

function DispatchOrder({ specialists }: { specialists: InvestigationSpecialist[] }) {
  return (
    <div className="mt-6">
      <h3 className="text-sm font-semibold text-ink">Orden de despacho del supervisor</h3>
      <ol className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-2 text-sm" aria-label="Orden en que el supervisor despachó a los especialistas">
        <li className="rounded-md border border-accent px-2.5 py-1 font-medium text-ink">Supervisor</li>
        {specialists.map((s, i) => (
          <li key={`${s.specialist}-${i}`} className="inline-flex items-center gap-2">
            <span aria-hidden="true" className="text-muted">
              →
            </span>
            <a href={`#agente-${s.specialist}-${i}`} className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-2.5 py-1 text-ink hover:border-accent">
              <span className="font-mono text-xs text-muted">{i + 1}</span>
              {specName(s.specialist)}
            </a>
          </li>
        ))}
        <li className="inline-flex items-center gap-2">
          <span aria-hidden="true" className="text-muted">
            →
          </span>
          <span className="rounded-md border border-dashed border-line px-2.5 py-1 text-muted">Evidencia, redacción y verificación</span>
        </li>
      </ol>
    </div>
  );
}

function SpecialistCard({ s, index, lookups }: { s: InvestigationSpecialist; index: number; lookups: InvestigationLookup[] }) {
  const meta = SPECIALISTS[s.specialist];
  const reason = s.dispatch_reason ? (DISPATCH_REASONS[s.dispatch_reason] ?? s.dispatch_reason) : null;
  return (
    <li id={`agente-${s.specialist}-${index}`} className="min-w-0 scroll-mt-4 rounded-lg border border-line bg-surface p-5">
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-sm text-muted" aria-label={`Paso ${index + 1}`}>
          {index + 1}
        </span>
        <h4 className="text-base font-semibold text-ink">{specName(s.specialist)}</h4>
      </div>
      {meta ? <p className="mt-1 text-sm text-muted">{meta.objective}</p> : null}
      <p className="mt-2 text-xs text-muted">
        Motivo del despacho: <span className="text-ink">{reason ?? NA}</span>
        {s.decided_by ? <> · decidido por {DECIDERS[s.decided_by] ?? s.decided_by}</> : null}
        {s.action_plan_by && s.action_plan_by !== s.decided_by ? <> · acciones ordenadas por {DECIDERS[s.action_plan_by] ?? s.action_plan_by}</> : null}
      </p>

      <div className="mt-4 overflow-x-auto" tabIndex={0} role="region" aria-label={`Consultas de ${specName(s.specialist)} (tabla desplazable)`}>
        <table className="w-full min-w-[22rem] border-collapse text-left text-sm">
          <caption className="sr-only">Consultas realizadas por {specName(s.specialist)}</caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" className="py-1.5 pr-3 font-medium">Fuente</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Resultado</th>
              <th scope="col" className="py-1.5 text-right font-medium">Tiempo</th>
            </tr>
          </thead>
          <tbody>
            {lookups.length === 0 ? (
              <tr>
                <td colSpan={3} className="py-2 text-muted">Sin consultas registradas.</td>
              </tr>
            ) : (
              lookups.map((l, i) => (
                <tr key={i} className="border-b border-line align-top last:border-b-0">
                  <td className="py-2 pr-3 text-ink">{SOURCES[l.tool] ?? l.tool}</td>
                  <td className="py-2 pr-3">
                    <OutcomeChip outcome={l.outcome} reason={l.reason} />
                  </td>
                  <td className="whitespace-nowrap py-2 text-right font-mono text-xs text-muted">
                    {fmtDuration(l.duration_ms)}
                    {l.attempts && l.attempts > 1 ? <span className="block">{fmtInt(l.attempts)} intentos</span> : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h5 className="mt-4 text-xs font-medium text-muted">Hechos incorporados al expediente</h5>
      {s.facts_added.length ? (
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-ink">
          {s.facts_added.map((f) => (
            <li key={f}>{FACT_LABELS[f] ?? <Mono>{f}</Mono>}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-muted">Ninguno.</p>
      )}
    </li>
  );
}

export function InvestigationPanel({ inv }: { inv: Investigation }) {
  // The first lookups of each specialist belong to its first dispatch; a retry dispatch takes the remainder.
  const used = new Map<string, number>();
  const slices = inv.specialists.map((s) => {
    const mine = inv.lookups.filter((l) => l.specialist === s.specialist);
    const from = used.get(s.specialist) ?? 0;
    const count = s.n_tool_calls ?? mine.length - from;
    used.set(s.specialist, from + count);
    return mine.slice(from, from + count);
  });
  return (
    <>
      <p className="mb-4 max-w-3xl text-sm text-muted">
        Un supervisor decide qué especialistas consultan fuentes públicas adicionales. Cada resultado alimenta el mismo redactor y verificador del expediente; los valores de cada hecho se detallan en el{" "}
        <a href="#texto" className="text-accent underline underline-offset-2">
          texto del expediente
        </a>
        . Más detalle en{" "}
        <Link href="/agentes" className="text-accent underline underline-offset-2">
          Cómo funcionan los agentes
        </Link>
        .
      </p>
      <RunSummary inv={inv} />
      <DispatchOrder specialists={inv.specialists} />
      <ol className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        {inv.specialists.map((s, i) => (
          <SpecialistCard key={`${s.specialist}-${i}`} s={s} index={i} lookups={slices[i]} />
        ))}
      </ol>
      {inv.specialists.length === 0 ? <p className="mt-4 text-sm text-muted">La ejecución no despachó especialistas.</p> : null}
    </>
  );
}
