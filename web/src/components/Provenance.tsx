"use client";

import { createContext, useCallback, useContext, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { fmtDate } from "@/lib/format";
import { citationFor, sourceById, type ProvFact, type Provenance } from "@/lib/provenance";
import { CopyButton } from "./CopyButton";
import { Icon } from "./Icon";

interface Ctx {
  prov: Provenance | null;
  inline: boolean;
  setInline: (v: boolean) => void;
  find: (keys: string[]) => ProvFact | null;
  open: (fact: ProvFact, trigger: HTMLElement) => void;
}

const Context = createContext<Ctx | null>(null);

/**
 * Holds the provenance of one process and the single side panel (a modal dialog: Esc closes it, focus is trapped
 * while open and returns to the marker that opened it). On narrow screens the same dialog is a bottom sheet.
 */
export function ProvenanceProvider({ prov, children }: { prov: Provenance | null; children: ReactNode }) {
  const [inline, setInline] = useState(false);
  const [fact, setFact] = useState<ProvFact | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const titleId = useId();

  const byKey = useMemo(() => new Map((prov?.facts ?? []).map((f) => [f.key, f])), [prov]);
  const find = useCallback((keys: string[]) => {
    for (const k of keys) {
      const f = byKey.get(k);
      if (f) return f;
    }
    return null;
  }, [byKey]);

  const open = useCallback((f: ProvFact, t: HTMLElement) => {
    trigger.current = t;
    setFact(f);
    // Open after the content is rendered.
    requestAnimationFrame(() => {
      const d = dialog.current;
      if (d && !d.open) d.showModal();
    });
  }, []);

  const close = () => dialog.current?.close();
  const onClosed = () => {
    trigger.current?.focus();
  };

  const value = useMemo(() => ({ prov, inline, setInline, find, open }), [prov, inline, find, open]);
  const src = fact && prov ? sourceById(prov, fact.source_id) : undefined;

  return (
    <Context.Provider value={value}>
      {children}
      <dialog
        ref={dialog}
        className="spanel"
        aria-labelledby={titleId}
        onClose={onClosed}
        onClick={(e) => {
          // A click on the backdrop lands on the dialog element itself.
          if (e.target === dialog.current) close();
        }}
      >
        {fact && prov ? (
          <div className="spanel__in">
            <div className="spanel__top">
              <p className="tag">De dónde sale este dato</p>
              <button type="button" className="spanel__x" onClick={close} aria-label="Cerrar">
                <Icon name="close" size={22} />
              </button>
            </div>
            <h2 id={titleId} className="h3">
              {fact.label_es}
            </h2>
            <dl className="spanel__list">
              <div>
                <dt>Valor publicado</dt>
                <dd className="spanel__val">{fact.value || "No disponible"}</dd>
              </div>
              <div>
                <dt>Fuente</dt>
                <dd>
                  {src ? (
                    <>
                      {src.name}
                      {src.publisher ? <span className="muted"> · {src.publisher}</span> : null}
                    </>
                  ) : (
                    "No disponible"
                  )}
                </dd>
              </div>
              <div>
                <dt>Campo en el registro original</dt>
                <dd>{fact.source_field ? <span className="num">{fact.source_field}</span> : "No disponible"}</dd>
              </div>
              <div>
                <dt>¿Lo calculó Veedor?</dt>
                <dd>{fact.derived ? <>Sí. {fact.derivation_es ?? "La fórmula no está disponible."}</> : "No: es el dato tal como lo publica la fuente."}</dd>
              </div>
              <div>
                <dt>Obtenido y licencia</dt>
                <dd>
                  {src?.retrieved_at ? `Obtenido el ${fmtDate(src.retrieved_at)}` : "Fecha de obtención no disponible"}
                  {src?.licence ? ` · ${src.licence}` : ""}
                </dd>
              </div>
              <div>
                <dt>Cómo verificarlo</dt>
                <dd>{fact.verify_es ?? "No hay instrucciones específicas para este dato."}</dd>
              </div>
            </dl>
            <div className="spanel__actions">
              <CopyButton text={citationFor(prov, fact, fmtDate)} label="Copiar cita" className="copy--solid" />
              {src?.url ? (
                <a href={src.url} className="link" target="_blank" rel="noopener noreferrer">
                  Abrir la fuente <Icon name="external" size={16} />
                  <span className="sr-only"> (se abre en una pestaña nueva)</span>
                </a>
              ) : null}
            </div>
          </div>
        ) : null}
      </dialog>
    </Context.Provider>
  );
}

/** The small "where does this come from" button. Renders nothing when the API gave no provenance for the datum. */
export function SourceMarker({ keys }: { keys: string[] }) {
  const ctx = useContext(Context);
  const fact = ctx?.find(keys) ?? null;
  if (!ctx || !fact) return null;
  const src = ctx.prov ? sourceById(ctx.prov, fact.source_id) : undefined;
  return (
    <span className="srcm needs-js">
      <button
        type="button"
        className="srcm__btn"
        aria-haspopup="dialog"
        aria-label={`Ver de dónde sale este dato: ${fact.label_es}`}
        title="Ver de dónde sale este dato"
        onClick={(e) => ctx.open(fact, e.currentTarget)}
      >
        <Icon name="source" size={18} />
      </button>
      {ctx.inline ? <span className="srcm__name">{src?.name ?? "Fuente no disponible"}</span> : null}
    </span>
  );
}

/** Page-level switch: shows the source name next to every marker, for people who want to audit quickly. */
export function SourcesToggle() {
  const ctx = useContext(Context);
  if (!ctx || !ctx.prov || ctx.prov.facts.length === 0) return null;
  return (
    <button type="button" className="toggle needs-js" aria-pressed={ctx.inline} onClick={() => ctx.setInline(!ctx.inline)}>
      <span className="toggle__sw" aria-hidden="true" />
      Mostrar fuentes
    </button>
  );
}

const SOURCE_FALLBACK: Record<string, string> = {
  veedor_indicators: "Indicadores calculados por Veedor",
  sercop_ocds: "SERCOP, datos abiertos (OCDS)",
};

/**
 * Where one sentence of an answer comes from. When its fact exists in the process provenance this is the usual marker
 * (it opens the same panel); otherwise the source name and the original field are printed next to the sentence.
 */
export function AnswerSource({ keys, sourceId, field }: { keys: string[]; sourceId: string; field: string }) {
  const ctx = useContext(Context);
  if (ctx?.find(keys)) return <SourceMarker keys={keys} />;
  const name = (ctx?.prov ? sourceById(ctx.prov, sourceId)?.name : undefined) ?? SOURCE_FALLBACK[sourceId] ?? sourceId;
  return (
    <span className="ask__src">
      Fuente: {name}
      {field ? (
        <>
          {" · campo "}
          <span className="num">{field}</span>
        </>
      ) : null}
    </span>
  );
}
