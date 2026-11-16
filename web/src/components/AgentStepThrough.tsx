"use client";

import { useEffect, useState } from "react";
import type { Step } from "@/lib/investigation";

const ICON = { ok: "✓", failed: "✕", skipped: "–" } as const;
const TICK_MS = 1500;

/**
 * Step-through of the stored tool log: which specialist asked which source, what came back and how long it took.
 * The full numbered list is always in the page (no JavaScript, reduced motion: that is all there is). With JavaScript and motion
 * welcome, controls play, pause and step through it; played steps stay readable and the rest are dimmed, never hidden.
 */
export function AgentStepThrough({ steps }: { steps: Step[] }) {
  const total = steps.length;
  const [pos, setPos] = useState(total); // number of steps reached; `total` with `started === false` shows everything plainly
  const [started, setStarted] = useState(false);
  const [playing, setPlaying] = useState(false);

  const running = playing && pos < total;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setPos((p) => Math.min(total, p + 1)), TICK_MS);
    return () => clearInterval(t);
  }, [running, total]);

  if (!total) return null;
  const cur = started ? steps[Math.max(0, pos - 1)] : null;

  const play = () => {
    if (!started || pos >= total) {
      setStarted(true);
      setPos(1);
    }
    setStarted(true);
    setPlaying(true);
  };
  const step = (d: 1 | -1) => {
    setPlaying(false);
    if (!started) {
      setStarted(true);
      setPos(d === 1 ? 1 : total);
      return;
    }
    setPos((p) => Math.min(total, Math.max(1, p + d)));
  };

  return (
    <div className="stepper">
      <div className="stepper__controls" role="group" aria-label="Reproducción paso a paso">
        <button type="button" className="btn btn--tc btn--sm" onClick={() => (running ? setPlaying(false) : play())}>
          {running ? "Pausar" : started && pos < total ? "Seguir" : "Reproducir"}
        </button>
        <button type="button" className="btn btn--line btn--sm" onClick={() => step(-1)} disabled={started && pos <= 1}>
          Paso anterior
        </button>
        <button type="button" className="btn btn--line btn--sm" onClick={() => step(1)} disabled={started && pos >= total}>
          Paso siguiente
        </button>
        <button
          type="button"
          className="btn btn--line btn--sm"
          onClick={() => {
            setPlaying(false);
            setStarted(false);
            setPos(total);
          }}
          disabled={!started}
        >
          Ver todo
        </button>
        <p className="stepper__hint small muted">Reproducción acelerada: cada paso dura unos segundos; el tiempo real de cada consulta está en el paso.</p>
      </div>

      <p className="sr-only" role="status" aria-live="polite">
        {cur ? `Paso ${cur.n} de ${total}. ${cur.specialist} consultó ${cur.source}. ${cur.outcome.label}. ${cur.duration}.` : ""}
      </p>

      <ol className="steps2" aria-label="Consultas de los especialistas, en orden">
        {steps.map((s, i) => {
          const state = !started ? "all" : i + 1 < pos ? "done" : i + 1 === pos ? "now" : "next";
          return (
            <li key={s.n} className={`st st--${state}`} aria-current={state === "now" ? "step" : undefined}>
              <span className="st__n" aria-hidden="true">
                {s.n}
              </span>
              <div className="st__body">
                {s.dispatch ? (
                  <p className="st__why">
                    El supervisor envió a <b>{s.specialist}</b> por: {s.dispatch}.
                  </p>
                ) : null}
                <p className="st__q">
                  <span className="sr-only">Paso {s.n}. </span>
                  <b>{s.specialist}</b> consultó <b>{s.source}</b>
                  {s.about ? <> sobre {s.about}</> : null}.
                </p>
                <p className="st__a">
                  <span className={`outcome outcome--${s.outcome.tone}`}>
                    <span aria-hidden="true">{ICON[s.outcome.tone]}</span>
                    {s.outcome.label}
                  </span>
                  <span className="st__t">Tardó {s.duration}</span>
                  {s.attempts && s.attempts > 1 ? <span className="st__t">{s.attempts} intentos</span> : null}
                  {s.reason && s.outcome.tone !== "ok" ? <span className="st__t">Motivo: {s.reason}</span> : null}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
