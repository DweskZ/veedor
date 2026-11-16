"use client";

import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { askProcess } from "@/lib/client-api";
import { AskError, COUNTER_FROM, QUESTION_MAX, checkQuestion, examplesFor, provenanceKeysFor, questionLength, waitPhrase, type AskAnswer } from "@/lib/ask";
import { markAskOff, useAskOff } from "@/lib/ask-state";
import { Icon } from "./Icon";
import { AnswerSource } from "./Provenance";
import { Passage } from "./Quotes";
import { Section, Skeleton } from "./ui";

type Outcome =
  | { kind: "answer"; answer: AskAnswer }
  | { kind: "limit"; retry: number | null }
  | { kind: "invalid"; message: string }
  | { kind: "error"; message: string };

interface Entry {
  id: number;
  question: string;
  /** null while the request is pending. */
  outcome: Outcome | null;
}

const MODE_TEXT: Record<AskAnswer["mode"], string> = {
  model: "Respondido con un modelo de lenguaje, que solo eligió qué datos mostrar.",
  retrieval: "Respondido por búsqueda, sin modelo.",
};

const noop = () => () => {};
/** True only after hydration, so the form never exists in the HTML served to a browser without JavaScript. */
const useMounted = () =>
  useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );

/**
 * "Pregunta sobre este proceso". Rendered only when the API reports the route as enabled. Questions and answers live in
 * memory for the visit: nothing goes to storage, and the only place a question is sent is the POST body to the API.
 */
export function AskSection({ ocid, suggestions }: { ocid: string; suggestions: string[] }) {
  const off = useAskOff();
  if (off) return null;
  return (
    <Section
      title="Pregunta sobre este proceso"
      id="preguntar"
      note="Escribe una pregunta en tus palabras. La respuesta sale solo de los datos guardados de este proceso, y cada frase dice de dónde viene."
    >
      <p className="nojs-only ask__nojs">Esta función necesita JavaScript. Todo lo que usa está en la página, más arriba.</p>
      <AskBox ocid={ocid} suggestions={suggestions} />
    </Section>
  );
}

function AskBox({ ocid, suggestions }: { ocid: string; suggestions: string[] }) {
  const mounted = useMounted();
  const uid = useId();
  const [text, setText] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [announce, setAnnounce] = useState("");
  const abort = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const focusId = useRef<number | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => abort.current?.abort(), []);

  // After a result arrives, focus goes to its heading (once).
  useEffect(() => {
    const e = entries[0];
    if (e && e.outcome && focusId.current === e.id) {
      focusId.current = null;
      document.getElementById(`${uid}-h-${e.id}`)?.focus();
    }
  }, [entries, uid]);

  const ask = useCallback(
    async (raw: string) => {
      const q = raw.trim();
      const problem = checkQuestion(q);
      if (problem) {
        setFormError(problem);
        input.current?.focus();
        return;
      }
      setFormError(null);
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      const id = nextId.current++;
      // A request that was still pending is dropped from the list: it never produced an answer.
      setEntries((prev) => [{ id, question: q, outcome: null }, ...prev.filter((p) => p.outcome !== null)]);
      setAnnounce("Buscando la respuesta…");
      let outcome: Outcome;
      try {
        const answer = await askProcess(ocid, q, ctl.signal);
        outcome = { kind: "answer", answer };
        setAnnounce(
          answer.answerable
            ? `Respuesta lista: ${answer.sentences.length} ${answer.sentences.length === 1 ? "frase" : "frases"} y ${answer.quotes.length} ${answer.quotes.length === 1 ? "cita" : "citas"}.`
            : "La evidencia guardada no responde esta pregunta.",
        );
      } catch (e) {
        if (ctl.signal.aborted) return;
        const f = e instanceof AskError ? e.failure : null;
        if (f?.kind === "disabled") {
          markAskOff();
          return;
        }
        if (f?.kind === "limit") {
          outcome = { kind: "limit", retry: f.retryAfterSeconds };
          setAnnounce("Llegaste al límite de preguntas por ahora.");
        } else if (f?.kind === "invalid") {
          outcome = { kind: "invalid", message: f.message };
          setAnnounce("La pregunta no es válida.");
        } else {
          outcome = { kind: "error", message: f?.kind === "error" ? f.message : "El servicio de datos no pudo responder ahora." };
          setAnnounce("No pudimos responder ahora.");
        }
      }
      if (ctl.signal.aborted) return;
      focusId.current = id;
      setEntries((prev) => prev.map((p) => (p.id === id ? { ...p, outcome } : p)));
    },
    [ocid],
  );

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(text);
  };
  const pick = (q: string) => {
    setText(q);
    void ask(q);
  };

  if (!mounted) return null;
  const n = questionLength(text);
  const showCount = n >= COUNTER_FROM;
  const [latest, ...older] = entries;
  const helpId = `${uid}-help`;
  const errId = `${uid}-err`;

  return (
    <div className="ask">
      <div role="status" className="sr-only">
        {announce}
      </div>
      {suggestions.length ? (
        <div role="group" aria-labelledby={`${uid}-sug`} className="ask__chips">
          <span id={`${uid}-sug`} className="ask__chips-t">
            Puedes preguntar:
          </span>
          {suggestions.map((s) => (
            <button key={s} type="button" className="ask__chip" onClick={() => pick(s)}>
              {s}
            </button>
          ))}
        </div>
      ) : null}
      <form onSubmit={onSubmit} noValidate>
        <label htmlFor={`${uid}-q`} className="field__label">
          Tu pregunta
        </label>
        <div className="ask__row">
          <input
            ref={input}
            id={`${uid}-q`}
            type="text"
            className="control"
            value={text}
            maxLength={QUESTION_MAX}
            autoComplete="off"
            spellCheck
            enterKeyHint="send"
            aria-invalid={formError ? true : undefined}
            aria-describedby={`${helpId}${formError ? ` ${errId}` : ""}`}
            placeholder="Por ejemplo: ¿Cuántos oferentes hubo?"
            onChange={(e) => {
              setText(e.target.value);
              if (formError) setFormError(null);
            }}
          />
          <button type="submit" className="btn btn--tc btn--sm">
            Preguntar
          </button>
        </div>
        <div className="ask__meta">
          <span id={helpId}>Una sola pregunta, de 3 a 300 caracteres.</span>
          {showCount ? (
            <span className={n >= QUESTION_MAX - 10 ? "ask__count--hot" : undefined}>
              {n} de {QUESTION_MAX}
            </span>
          ) : null}
        </div>
        {formError ? (
          <p id={errId} className="ask__err">
            {formError}
          </p>
        ) : null}
      </form>

      {latest ? <EntryView entry={latest} uid={uid} suggestions={suggestions} onPick={pick} onRetry={() => void ask(latest.question)} /> : null}

      {older.length ? (
        <section aria-labelledby={`${uid}-prev`} className="ask__prev">
          <h3 id={`${uid}-prev`} className="ask__prevh">
            Preguntas anteriores en esta visita
          </h3>
          {older.map((e) => (
            <details key={e.id} className="card card--quiet card--tight ask__old">
              <summary>{e.question}</summary>
              <EntryView entry={e} uid={uid} suggestions={suggestions} onPick={pick} onRetry={() => void ask(e.question)} />
            </details>
          ))}
        </section>
      ) : null}
    </div>
  );
}

function EntryView({ entry, uid, suggestions, onPick, onRetry }: { entry: Entry; uid: string; suggestions: string[]; onPick: (q: string) => void; onRetry: () => void }) {
  const hid = `${uid}-h-${entry.id}`;
  const o = entry.outcome;
  const asked = (
    <div>
      <p className="ask__q">Tu pregunta</p>
      <p className="ask__qtext">{entry.question}</p>
    </div>
  );
  if (!o) {
    return (
      <div className="ask__ans" aria-busy="true">
        {asked}
        <h3 id={hid} tabIndex={-1} className="ask__h">
          Buscando la respuesta…
        </h3>
        <div className="ask__sk">
          <Skeleton style={{ height: 22, width: "92%" }} />
          <Skeleton style={{ height: 22, width: "78%" }} />
          <Skeleton style={{ height: 96 }} />
        </div>
      </div>
    );
  }
  if (o.kind === "limit") {
    return (
      <article className="ask__ans ask__ans--soft" aria-labelledby={hid}>
        {asked}
        <h3 id={hid} tabIndex={-1} className="ask__h">
          Hiciste muchas preguntas seguidas
        </h3>
        <p>
          Hay un límite de preguntas para que todas las personas puedan usar esta función. Vuelve a intentarlo{" "}
          {o.retry != null ? `en ${waitPhrase(o.retry)}` : "en unos minutos"}. Mientras tanto, los datos de esta página siguen disponibles más arriba.
        </p>
      </article>
    );
  }
  if (o.kind === "invalid" || o.kind === "error") {
    return (
      <article className="ask__ans ask__ans--soft" aria-labelledby={hid}>
        {asked}
        <h3 id={hid} tabIndex={-1} className="ask__h">
          {o.kind === "invalid" ? "No pudimos usar esta pregunta" : "No pudimos responder ahora"}
        </h3>
        <p>{o.message}</p>
        {o.kind === "error" ? (
          <div>
            <button type="button" className="btn btn--line btn--sm" onClick={onRetry}>
              Intentar de nuevo
            </button>
          </div>
        ) : null}
      </article>
    );
  }
  const a = o.answer;
  return (
    <article className={`ask__ans ${a.answerable ? "" : "ask__ans--soft"}`} aria-labelledby={hid}>
      {asked}
      <h3 id={hid} tabIndex={-1} className="ask__h">
        {a.answerable ? "Respuesta" : "Los datos guardados no responden esto"}
      </h3>
      {a.answerable && a.sentences.length ? (
        <ul className="ask__sent">
          {a.sentences.map((s, i) => (
            <li key={`${s.fact_id}-${i}`}>
              {s.text}
              <AnswerSource keys={provenanceKeysFor(s.fact_id)} sourceId={s.source_id} field={s.source_field} />
            </li>
          ))}
        </ul>
      ) : null}
      {!a.answerable ? (
        <>
          <p>{a.note_es ?? "Veedor solo responde con los datos guardados de este proceso, y no los encontró para esta pregunta."}</p>
          <div>
            <p className="ask__prevh" style={{ marginBottom: 8 }}>
              Sí puedes preguntar, por ejemplo:
            </p>
            <div className="ask__ex">
              {examplesFor(suggestions).map((s) => (
                <button key={s} type="button" className="ask__chip" onClick={() => onPick(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        </>
      ) : null}
      {a.quotes.length ? (
        <div className="ask__quotes qt">
          <p className="qt__note">
            <Icon name="quote" size={20} />
            <span>
              <b>Estas palabras no son de Veedor.</b> Las escribieron oferentes o la entidad que compra y se muestran tal como se publicaron.
            </span>
          </p>
          <ol className="qt__list" style={{ margin: 0 }}>
            {a.quotes.map((q) => (
              <li key={q.quote_id} className="qt__item">
                <Passage part={q} date={q.date} author_kind={null} truncated={q.truncated} />
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {a.answerable && a.note_es ? <p className="muted small">{a.note_es}</p> : null}
      <p className="ask__mode">
        <span className="ask__tag">Cómo se respondió: </span>
        {MODE_TEXT[a.mode]}
      </p>
      <p className="ask__fixed">La respuesta usa solo la evidencia guardada de este proceso y no es un juicio.</p>
    </article>
  );
}
