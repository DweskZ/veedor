import Link from "next/link";
import type { ReactNode } from "react";
import { RISK_LEVELS, riskLevel } from "@/lib/risk";
import { fmtNum } from "@/lib/format";
import { displayName } from "@/lib/names";
import type { PartyKind } from "@/lib/types";
import { Art } from "./Art";

export function PageHeader({
  eyebrow,
  title,
  lead,
  small = false,
  children,
}: {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  /** Smaller title, for long entity or company names. */
  small?: boolean;
  children?: ReactNode;
}) {
  return (
    <header className="phead">
      <div className="wrap">
        <div className="phead__circle" aria-hidden="true" />
        <div className="phead__text">
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h1 className={`h1 ${small ? "h1--sm" : "h1--page"}`}>{title}</h1>
          {lead ? <div className="lead">{lead}</div> : null}
          {children}
        </div>
      </div>
    </header>
  );
}

/** A titled block on an inner page. `note` is a plain-words sentence under the title. */
export function Section({
  title,
  id,
  children,
  aside,
  note,
}: {
  title: string;
  id: string;
  children: ReactNode;
  aside?: ReactNode;
  note?: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="blk" id={`s-${id}`}>
      <div className="blk__head">
        <h2 id={id} className="blk__title">
          {title}
        </h2>
        {aside}
      </div>
      {note ? <p className="blk__note">{note}</p> : null}
      {children}
    </section>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

/** Big figure with a plain-language label. Use inside `<dl className="figs">`. */
export function Fig({ label, value, hint, medium = false }: { label: string; value: ReactNode; hint?: ReactNode; medium?: boolean }) {
  return (
    <div className="fig">
      <dt>{label}</dt>
      <dd className={medium ? "fig__m" : undefined}>{value}</dd>
      {hint ? <dd className="fig__hint">{hint}</dd> : null}
    </div>
  );
}

export function ErrorState({ title = "No pudimos cargar los datos", detail }: { title?: string; detail?: string }) {
  return (
    <div role="alert" className="err">
      <h2 className="h3">{title}</h2>
      <p style={{ marginTop: 10 }}>{detail ?? "El servicio de datos no respondió. Inténtalo de nuevo en unos momentos."}</p>
      <p className="muted small" style={{ marginTop: 10 }}>
        No mostramos datos de reemplazo: la información solo viene del servicio de datos de Veedor.
      </p>
    </div>
  );
}

export function EmptyState({ children, art = false }: { children: ReactNode; art?: boolean }) {
  return (
    <div className={`empty ${art ? "empty--art" : ""}`}>
      <div>{children}</div>
      {art ? <Art name="vacio" sizes="280px" className="empty__art" alt="Dibujo isométrico de un terreno vacío con un letrero en blanco." /> : null}
    </div>
  );
}

export function Skeleton({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={`skeleton ${className}`} style={style} aria-hidden="true" />;
}

export function PageSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="wrap" role="status" aria-live="polite" aria-label="Cargando">
      <span className="sr-only">Cargando datos…</span>
      <Skeleton style={{ height: 24, width: 140, marginTop: 56 }} />
      <Skeleton style={{ height: 96, width: "min(100%, 640px)", marginTop: 20 }} />
      <Skeleton style={{ height: 24, width: "min(100%, 480px)", marginTop: 20 }} />
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", marginTop: 48 }}>
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} style={{ height: 112 }} />
        ))}
      </div>
      <div style={{ display: "grid", gap: 10, marginTop: 40, paddingBottom: 64 }}>
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} style={{ height: 56 }} />
        ))}
      </div>
    </div>
  );
}

/** Four ascending bars: the number of filled bars is the risk level (0 to 4). A shape cue that does not depend on colour. */
function Bars({ level }: { level: number }) {
  return (
    <span className="risk__bars" aria-hidden="true">
      {[1, 2, 3, 4].map((n) => (
        <i key={n} className={n <= level ? "on" : undefined} />
      ))}
    </span>
  );
}

/** Score on the 5-step scale: number in a coloured chip, ascending bars and the level name in words. */
export function RiskScore({ score, big = false }: { score: number; big?: boolean }) {
  const lvl = riskLevel(score);
  return (
    <span className={`risk ${big ? "risk--big" : ""}`} title={`Puntaje ${fmtNum(score)} de 100 · ${lvl.label}`}>
      <span className={`risk__num r${lvl.index}`}>
        <span className="sr-only">Puntaje </span>
        {fmtNum(score)}
      </span>
      <span className="risk__meta">
        <Bars level={lvl.index} />
        <span className="risk__label">{lvl.label}</span>
      </span>
    </span>
  );
}

export function RiskLegend({ large = false }: { large?: boolean }) {
  return (
    <ul className={`legend ${large ? "legend--lg" : ""}`} aria-label="Escala de puntaje">
      {RISK_LEVELS.map((l) => (
        <li key={l.index}>
          <span className={`legend__sw r${l.index}`} aria-hidden="true" />
          <Bars level={l.index} />
          <span>
            {l.label} <span className="legend__rng">({l.min === l.max ? l.min : `${l.min}–${l.max}`})</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function SignalChip({ code, labels, quiet = false }: { code: string; labels: Record<string, string>; quiet?: boolean }) {
  return (
    <Link
      href={`/procesos?signal=${encodeURIComponent(code)}`}
      title={`Ver más procesos con esta señal${quiet ? " (solo contexto, no suma puntos)" : ""}`}
      className={`chip ${quiet ? "chip--quiet" : ""}`}
    >
      {labels[code] ?? code}
    </Link>
  );
}

/** Natural persons arrive masked from the API; this only guards the display. */
export function partyName(name: string | null, kind: PartyKind | null): string {
  if (kind === "natural_person") return "Persona natural";
  if (kind === "unknown" && !name) return "Persona natural o sin identificar";
  return name ? displayName(name) : "No disponible";
}

/**
 * An official name or title shown in sentence-friendly case. The original spelling stays in the title attribute
 * (shown on hover and read by assistive technology only when it differs).
 */
export function Name({ value, fallback = "No disponible" }: { value: string | null | undefined; fallback?: string }) {
  if (!value) return <>{fallback}</>;
  const shown = displayName(value);
  return shown === value ? <>{value}</> : <span title={`Como figura en el registro: ${value}`}>{shown}</span>;
}

/** Codes, RUCs and amounts: same family as the text, tabular figures. */
export function Num({ children }: { children: ReactNode }) {
  return <span className="num">{children}</span>;
}

/** Accessible horizontal bars: a real list, with values as text. */
export function BarList({
  items,
  total,
  format,
  highlightTop = false,
}: {
  items: { key: string; label: string; value: number }[];
  total?: number;
  format: (n: number) => string;
  highlightTop?: boolean;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="bars">
      {items.map((it, i) => (
        <li key={it.key}>
          <div className="bars__row">
            <span>{it.label}</span>
            <span className="bars__val">
              {format(it.value)}
              {total ? ` · ${new Intl.NumberFormat("es-EC", { style: "percent", maximumFractionDigits: 1 }).format(it.value / total)}` : ""}
            </span>
          </div>
          <div className="bars__track" aria-hidden="true">
            <div className={`bars__fill ${highlightTop && i === 0 ? "bars__fill--tc" : ""}`} style={{ width: `${Math.max(1, (it.value / max) * 100)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
