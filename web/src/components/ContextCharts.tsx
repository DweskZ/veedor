import { fmtInt, fmtNum, fmtPct } from "@/lib/format";
import type { ProcessContext } from "@/lib/types";
import { Term } from "./Term";

const INK = "#1a1f36";

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);
const pctInt = (v: number) => `${Math.round(v * 100)} %`;

function Tenderers({ t, comparable }: { t: NonNullable<ProcessContext["tenderers"]>; comparable: number | null }) {
  const total = t.counts.reduce((a, b) => a + b, 0);
  if (!total) return null;
  const mine = t.position.value != null ? Math.min(6, Math.max(1, Math.round(t.position.value))) : null;
  const max = Math.max(...t.counts);
  const share = (i: number) => t.counts[i] / total;
  // Largest k such that at least half of the comparable processes had k or more tenderers.
  let k = 1;
  for (let i = 1; i <= 6; i++) if (t.counts.slice(i - 1).reduce((a, b) => a + b, 0) / total >= 0.5) k = i;
  const label = (i: number) => (i === 5 ? "6 o más" : String(i + 1));
  const reading =
    mine != null ? (
      <>
        Este proceso tuvo <b>{mine === 6 ? "6 o más" : mine}</b> {plural(mine, "oferente", "oferentes")}. Entre los {fmtInt(comparable ?? total)} procesos de su tipo y año, el{" "}
        <b>{pctInt(share(mine - 1))}</b> tuvo lo mismo. La mitad tuvo <b>{k === 6 ? "6 o más" : k} o más</b>.
      </>
    ) : (
      <>
        Entre los {fmtInt(comparable ?? total)} procesos de su tipo y año, la mitad tuvo <b>{k === 6 ? "6 o más" : k} o más</b> <Term t="oferente">oferentes</Term>.
      </>
    );
  return (
    <figure className="ctx">
      <figcaption className="ctx__q">¿Cuántos <Term t="oferente">oferentes</Term> tuvo?</figcaption>
      <svg viewBox="0 0 360 190" className="ctx__svg" role="img" aria-label={`Número de oferentes en procesos parecidos. ${mine != null ? `Este proceso tuvo ${mine === 6 ? "6 o más" : mine}.` : ""}`}>
        <line x1="14" x2="346" y1="150" y2="150" stroke={INK} strokeWidth="2.5" />
        {t.counts.map((c, i) => {
          const h = max ? (c / max) * 104 : 0;
          const on = mine === i + 1;
          const x = 24 + i * 52;
          return (
            <g key={i}>
              <rect x={x} y={150 - h} width="38" height={Math.max(2, h)} rx="5" fill={on ? "#d9480f" : "#cadbfb"} stroke={INK} strokeWidth="2.5" />
              <text x={x + 19} y={150 - h - 7} textAnchor="middle" fontSize="12" fontWeight="800" fill={INK}>
                {pctInt(share(i))}
              </text>
              <text x={x + 19} y="168" textAnchor="middle" fontSize="12" fontWeight={on ? 800 : 600} fill={INK}>
                {label(i)}
              </text>
              {on ? (
                <text x={x + 19} y="184" textAnchor="middle" fontSize="11" fontWeight="800" fill={INK}>
                  ▲ Este proceso
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <p className="ctx__read">{reading}</p>
    </figure>
  );
}

function Range({
  title,
  d,
  unit,
  fmt,
  what,
  comparable,
}: {
  title: React.ReactNode;
  d: NonNullable<ProcessContext["ratio"]>;
  unit: string;
  fmt: (v: number) => string;
  what: string;
  comparable: number | null;
}) {
  const v = d.position.value;
  const q1 = d.q1 ?? d.median;
  const q3 = d.q3 ?? d.median;
  const lo0 = Math.min(q1, v ?? q1);
  const hi0 = Math.max(q3, v ?? q3);
  const pad = (hi0 - lo0 || Math.abs(d.median) * 0.2 || 1) * 0.35;
  const lo = lo0 - pad;
  const hi = hi0 + pad;
  const X = (a: number) => 20 + ((a - lo) / (hi - lo)) * 320;
  const pc = d.position.percentile != null ? Math.round(d.position.percentile * 100) : null;
  return (
    <figure className="ctx">
      <figcaption className="ctx__q">{title}</figcaption>
      <svg viewBox="0 0 360 130" className="ctx__svg" role="img" aria-label={`${what}. Mitad central de los procesos parecidos: de ${fmt(q1)} a ${fmt(q3)}${v != null ? `. Este proceso: ${fmt(v)}` : ""}.`}>
        <line x1="20" x2="340" y1="78" y2="78" stroke={INK} strokeWidth="2.5" />
        <rect x={X(q1)} y="58" width={Math.max(3, X(q3) - X(q1))} height="40" rx="6" fill="#cadbfb" stroke={INK} strokeWidth="2.5" />
        <line x1={X(d.median)} x2={X(d.median)} y1="54" y2="102" stroke={INK} strokeWidth="4" />
        <text x={X(d.median)} y="118" textAnchor="middle" fontSize="12" fontWeight="800" fill={INK}>
          Mediana {fmt(d.median)}
        </text>
        {v != null ? (
          <g>
            <path d={`M${X(v)} 70 l-9 -16 h18 z`} fill="#d9480f" stroke={INK} strokeWidth="2.5" strokeLinejoin="round" transform="translate(0 -2)" />
            <text x={Math.min(300, Math.max(60, X(v)))} y="30" textAnchor="middle" fontSize="12" fontWeight="800" fill={INK}>
              Este proceso: {fmt(v)}
            </text>
          </g>
        ) : null}
      </svg>
      <p className="ctx__read">
        {v != null ? (
          <>
            Este proceso: <b>{fmt(v)}</b>. La mitad central de los {fmtInt(comparable)} procesos parecidos va de <b>{fmt(q1)}</b> a <b>{fmt(q3)}</b>{unit ? ` ${unit}` : ""}; la mediana es{" "}
            <b>{fmt(d.median)}</b>.
            {pc != null ? (
              <>
                {" "}
                Queda en el <Term t="percentil">percentil</Term> <b>{pc}</b>.
              </>
            ) : null}
          </>
        ) : (
          <>
            La mitad central de los {fmtInt(comparable)} procesos parecidos va de <b>{fmt(q1)}</b> a <b>{fmt(q3)}</b>{unit ? ` ${unit}` : ""}; la mediana es <b>{fmt(d.median)}</b>.
          </>
        )}
      </p>
    </figure>
  );
}

/** Where this process sits among others of the same method and year, one small chart per signal that has comparison data. Position only. */
export function ContextCharts({ ctx }: { ctx: ProcessContext }) {
  const any = ctx.tenderers || ctx.ratio || ctx.window;
  if (!any) return null;
  return (
    <>
      <p className="blk__note" style={{ marginBottom: 20 }}>
        Procesos del mismo método{ctx.method ? ` (${ctx.method})` : ""}
        {ctx.year ? ` y del año ${ctx.year}` : ""}. Describe dónde queda este proceso, no si algo está bien o mal.
      </p>
      <div className="ctx__grid">
        {ctx.tenderers ? <Tenderers t={ctx.tenderers} comparable={ctx.comparable} /> : null}
        {ctx.ratio ? (
          <Range
            title={<>¿Cuánto del <Term t="presupuesto referencial">presupuesto</Term> se adjudicó?</>}
            d={ctx.ratio}
            unit="del presupuesto"
            fmt={(v) => fmtPct(v)}
            what="Parte del presupuesto referencial que se adjudicó"
            comparable={ctx.comparable}
          />
        ) : null}
        {ctx.window ? (
          <Range
            title={<>¿Cuánto duró el <Term t="plazo de ofertas">plazo de ofertas</Term>?</>}
            d={ctx.window}
            unit=""
            fmt={(v) => `${fmtNum(v)} ${v === 1 ? "día" : "días"}`}
            what="Días de plazo para presentar ofertas"
            comparable={ctx.comparable}
          />
        ) : null}
      </div>
    </>
  );
}
