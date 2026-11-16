import Link from "next/link";
import type { ReactNode } from "react";
import { RISK_LEVELS, riskLevel } from "@/lib/risk";
import { fmtNum } from "@/lib/format";
import type { PartyKind } from "@/lib/types";

export function PageHeader({ title, lead, children }: { title: string; lead?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-8 mt-10">
      <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{title}</h1>
      {lead ? <p className="mt-3 max-w-3xl text-base leading-relaxed text-muted">{lead}</p> : null}
      {children}
    </div>
  );
}

export function Section({ title, id, children, aside }: { title: string; id?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section aria-labelledby={id} className="mt-12">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={id} className="text-xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-line bg-surface p-5 ${className}`}>{children}</div>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <Card>
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-2xl font-medium tracking-tight text-ink">{value}</dd>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </Card>
  );
}

export function ErrorState({ title = "No se pudieron cargar los datos", detail }: { title?: string; detail?: string }) {
  return (
    <div role="alert" className="rounded-lg border border-line bg-surface p-6">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <p className="mt-2 text-sm text-muted">{detail ?? "El servicio de datos no respondió. Intente nuevamente en unos momentos."}</p>
      <p className="mt-2 text-sm text-muted">No se muestran datos de reemplazo: la información solo proviene del servicio de datos de Veedor.</p>
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-line px-6 py-10 text-center text-sm text-muted">{children}</div>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function PageSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-label="Cargando">
      <span className="sr-only">Cargando datos…</span>
      <Skeleton className="mb-3 mt-10 h-10 w-2/3" />
      <Skeleton className="mb-10 h-5 w-1/2" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="mt-10 space-y-2">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    </div>
  );
}

/** Score with a calm sequential scale: number, bar and label (never colour alone). */
export function RiskScore({ score, compact = false }: { score: number; compact?: boolean }) {
  const lvl = riskLevel(score);
  return (
    <span className="inline-flex items-center gap-2" title={`Puntaje ${score} de 100 · ${lvl.label}`}>
      <span
        className="inline-flex min-w-9 justify-center rounded-sm px-1.5 py-0.5 font-mono text-sm font-medium"
        style={{ background: `var(--risk-${lvl.index}-bg)`, color: `var(--risk-${lvl.index}-fg)` }}
      >
        {fmtNum(score)}
      </span>
      {compact ? <span className="sr-only">{lvl.label}</span> : <span className="text-xs text-muted">{lvl.label}</span>}
    </span>
  );
}

export function RiskLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label="Escala de puntaje">
      {RISK_LEVELS.map((l) => (
        <li key={l.index} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="h-3 w-3 rounded-sm border border-line" style={{ background: `var(--risk-${l.index}-bg)` }} />
          {l.label} ({l.min === l.max ? l.min : `${l.min}–${l.max}`})
        </li>
      ))}
    </ul>
  );
}

export function SignalChip({ code, labels, quiet = false }: { code: string; labels: Record<string, string>; quiet?: boolean }) {
  return (
    <Link
      href={`/procesos?signal=${encodeURIComponent(code)}`}
      title={code}
      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs hover:border-accent ${
        quiet ? "border-dashed border-line text-muted" : "border-line bg-surface-2 text-ink"
      }`}
    >
      {labels[code] ?? code}
    </Link>
  );
}

/** Natural persons arrive masked from the API; this only guards the display. */
export function partyName(name: string | null, kind: PartyKind | null): string {
  if (kind === "natural_person") return "Persona natural";
  if (kind === "unknown" && !name) return "Persona natural o sin identificar";
  return name ?? "No disponible";
}

export function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[0.92em]">{children}</span>;
}

/** Accessible horizontal bars: a real list, with values as text. */
export function BarList({
  items,
  total,
  barVar = "--accent",
  format,
}: {
  items: { key: string; label: string; value: number; swatch?: string }[];
  total?: number;
  barVar?: string;
  format: (n: number) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-3">
      {items.map((it) => (
        <li key={it.key}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-ink">{it.label}</span>
            <span className="font-mono text-muted">
              {format(it.value)}
              {total ? ` · ${new Intl.NumberFormat("es-EC", { style: "percent", maximumFractionDigits: 1 }).format(it.value / total)}` : ""}
            </span>
          </div>
          <div className="mt-1 h-2.5 w-full rounded-sm bg-surface-2" aria-hidden="true">
            <div
              className="h-full rounded-sm border border-line"
              style={{ width: `${Math.max(1, (it.value / max) * 100)}%`, background: it.swatch ?? `var(${barVar})` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
