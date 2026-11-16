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
import { Card, Num } from "./ui";

const specName = (id: string) => SPECIALISTS[id]?.name ?? id;

const TONE_ICON: Record<Outcome["tone"], string> = { ok: "✓", failed: "✕", skipped: "–" };

function OutcomeChip({ outcome, reason }: { outcome: string; reason: string | null }) {
  const o = outcomeOf(outcome);
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
      <span className={`outcome outcome--${o.tone}`}>
        <span aria-hidden="true">{TONE_ICON[o.tone]}</span>
        {o.label}
      </span>
      {reason && o.tone !== "ok" ? <span className="cell-sub">{OUTCOME_REASONS[reason] ?? reason}</span> : null}
    </span>
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
      <dl className="run run--4">
        <div>
          <dt>Cómo se hizo</dt>
          <dd>
            {assisted ? "Con ayuda de un modelo" : "Sin modelo: reglas fijas"}
            <span className="cell-sub" style={{ display: "block" }}>
              {assisted
                ? "El modelo ordena a los especialistas y sus acciones entre opciones cerradas; no redacta ni pasa argumentos."
                : "El orden sale de una tabla fija según las señales."}
            </span>
          </dd>
        </div>
        <div>
          <dt>Consultas a fuentes</dt>
          <dd>
            <span className="run__big">{fmtInt(inv.lookups.length)}</span>
            <span className="cell-sub" style={{ display: "block" }}>
              {failed ? `${fmtInt(failed)} sin respuesta de la fuente` : "Todas respondieron o se omitieron"}
              {skipped ? ` · ${fmtInt(skipped)} omitida${skipped === 1 ? "" : "s"}` : ""}
            </span>
          </dd>
        </div>
        <div>
          <dt>Duración</dt>
          <dd>
            <span className="run__big">{fmtDuration(el)}</span>
            <span className="cell-sub" style={{ display: "block" }}>{inv.finished_at ? fmtDateTime(inv.finished_at) : NA}</span>
          </dd>
        </div>
        <div>
          <dt>Uso del modelo</dt>
          <dd>
            {u && u.calls > 0 ? (
              <>
                <span className="run__big">{fmtInt(u.calls)}</span> llamadas
                <span className="cell-sub" style={{ display: "block" }}>
                  {u.model ? <Num>{u.model}</Num> : null}
                  {u.model ? " · " : ""}
                  {fmtInt(u.prompt_tokens)} tokens de entrada, {fmtInt(u.completion_tokens)} de salida
                  {u.invalid_choices ? ` · ${fmtInt(u.invalid_choices)} elecciones inválidas` : ""}
                </span>
              </>
            ) : (
              <>
                <span className="run__big">0</span> llamadas
                <span className="cell-sub" style={{ display: "block" }}>No se usó ningún modelo</span>
              </>
            )}
          </dd>
        </div>
      </dl>
      <p className="muted small" style={{ marginTop: 18, paddingTop: 14, borderTop: "2px solid var(--ice-deep)" }}>
        Las consultas son de solo lectura. No se consultan registros de personas naturales y no se almacenan ni se muestran datos de personas naturales.
      </p>
    </Card>
  );
}

function DispatchOrder({ specialists }: { specialists: InvestigationSpecialist[] }) {
  return (
    <div style={{ marginTop: 28 }}>
      <h3 className="h4">En qué orden trabajaron</h3>
      <ol className="order" style={{ marginTop: 12 }} aria-label="Orden en que el supervisor despachó a los especialistas">
        <li>
          <span className="order__box order__box--sup">Supervisor</span>
        </li>
        {specialists.map((s, i) => (
          <li key={`${s.specialist}-${i}`}>
            <span aria-hidden="true" className="order__arrow">
              →
            </span>
            <a href={`#agente-${s.specialist}-${i}`}>
              <Num>{i + 1}</Num>
              {specName(s.specialist)}
            </a>
          </li>
        ))}
        <li>
          <span aria-hidden="true" className="order__arrow">
            →
          </span>
          <span className="order__box order__box--dash">Evidencia, redacción y verificación</span>
        </li>
      </ol>
    </div>
  );
}

function SpecialistCard({ s, index, lookups }: { s: InvestigationSpecialist; index: number; lookups: InvestigationLookup[] }) {
  const meta = SPECIALISTS[s.specialist];
  const reason = s.dispatch_reason ? (DISPATCH_REASONS[s.dispatch_reason] ?? s.dispatch_reason) : null;
  return (
    <li id={`agente-${s.specialist}-${index}`} className="spec">
      <div className="spec__head">
        <span className="pin pin--inline">
          <span className="sr-only">Paso </span>
          {index + 1}
        </span>
        <h4 className="h3">{specName(s.specialist)}</h4>
      </div>
      {meta ? <p style={{ marginTop: 10 }}>{meta.objective}</p> : null}
      <p className="muted small" style={{ marginTop: 8 }}>
        Motivo del despacho: <b style={{ color: "var(--ink)" }}>{reason ?? NA}</b>
        {s.decided_by ? <> · decidido por {DECIDERS[s.decided_by] ?? s.decided_by}</> : null}
        {s.action_plan_by && s.action_plan_by !== s.decided_by ? <> · acciones ordenadas por {DECIDERS[s.action_plan_by] ?? s.action_plan_by}</> : null}
      </p>

      <div className="scroll-x" style={{ marginTop: 16 }} tabIndex={0} role="region" aria-label={`Consultas de ${specName(s.specialist)} (tabla desplazable)`}>
        <table className="mini-tbl">
          <caption className="sr-only">Consultas realizadas por {specName(s.specialist)}</caption>
          <thead>
            <tr>
              <th scope="col">Fuente</th>
              <th scope="col">Resultado</th>
              <th scope="col" style={{ textAlign: "right" }}>Tiempo</th>
            </tr>
          </thead>
          <tbody>
            {lookups.length === 0 ? (
              <tr>
                <td colSpan={3} className="muted">Sin consultas registradas.</td>
              </tr>
            ) : (
              lookups.map((l, i) => (
                <tr key={i}>
                  <td>{SOURCES[l.tool] ?? l.tool}</td>
                  <td>
                    <OutcomeChip outcome={l.outcome} reason={l.reason} />
                  </td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Num>{fmtDuration(l.duration_ms)}</Num>
                    {l.attempts && l.attempts > 1 ? <span className="cell-sub" style={{ display: "block" }}>{fmtInt(l.attempts)} intentos</span> : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h5 className="tag" style={{ marginTop: 18 }}>Hechos que sumó al expediente</h5>
      {s.facts_added.length ? (
        <ul className="ticks" style={{ marginTop: 8 }}>
          {s.facts_added.map((f) => (
            <li key={f}>{FACT_LABELS[f] ?? <Num>{f}</Num>}</li>
          ))}
        </ul>
      ) : (
        <p className="muted" style={{ marginTop: 6 }}>Ninguno.</p>
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
      <p className="blk__note">
        Un supervisor eligió qué especialistas consultaron fuentes públicas adicionales. Lo que encontraron pasa por el mismo redactor y verificador del expediente; el detalle de cada hecho está en el{" "}
        <a href="#texto" className="inline-link">
          texto del expediente
        </a>
        . Cómo funciona, en{" "}
        <Link href="/agentes" className="inline-link">
          Agentes de investigación
        </Link>
        .
      </p>
      <RunSummary inv={inv} />
      <DispatchOrder specialists={inv.specialists} />
      <ol className="specs" style={{ marginTop: 24 }}>
        {inv.specialists.map((s, i) => (
          <SpecialistCard key={`${s.specialist}-${i}`} s={s} index={i} lookups={slices[i]} />
        ))}
      </ol>
      {inv.specialists.length === 0 ? <p className="muted" style={{ marginTop: 16 }}>La ejecución no despachó especialistas.</p> : null}
    </>
  );
}
