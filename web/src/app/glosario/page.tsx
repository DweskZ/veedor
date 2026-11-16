import type { Metadata } from "next";
import Link from "next/link";
import { GLOSSARY, termId } from "@/lib/glossary";
import { PageHeader } from "@/components/ui";

const DESCRIPTION = "Qué significan en palabras sencillas los términos de compras públicas que aparecen en Veedor.";
export const metadata: Metadata = {
  title: "Glosario",
  description: DESCRIPTION,
  openGraph: { title: "Glosario · Veedor", description: DESCRIPTION },
};

const sorted = [...GLOSSARY].sort((a, b) => a.term.localeCompare(b.term, "es", { sensitivity: "base" }));

export default function GlossaryPage() {
  const letters = Array.from(new Set(sorted.map((e) => e.term[0].toLocaleUpperCase("es"))));
  return (
    <>
      <PageHeader
        eyebrow="Glosario"
        title={
          <>
            Las palabras, <em>en claro.</em>
          </>
        }
        lead="Qué significa cada término de compras públicas que aparece en Veedor. En las páginas, las palabras con subrayado punteado abren esta definición."
      />
      <div className="wrap">
        <nav aria-label="Letras del glosario" className="az">
          {letters.map((l) => (
            <a key={l} href={`#letra-${l}`}>
              {l}
            </a>
          ))}
        </nav>
        <dl className="gloss">
          {sorted.map((e, i) => {
            const letter = e.term[0].toLocaleUpperCase("es");
            const startsLetter = i === 0 || sorted[i - 1].term[0].toLocaleUpperCase("es") !== letter;
            return (
              <div key={e.term} id={termId(e.term)} className="gloss__item">
                {startsLetter ? <span id={`letra-${letter}`} className="gloss__letter" aria-hidden="true">{letter}</span> : null}
                <dt>
                  <h2 className="h4">{e.term}</h2>
                  {e.aliases.length ? <span className="muted small">También: {e.aliases.join(", ")}</span> : null}
                </dt>
                <dd>
                  <p>{e.definition_es}</p>
                  <p className="muted small">Fuente: {e.source}</p>
                </dd>
              </div>
            );
          })}
        </dl>
        <p className="muted small" style={{ marginTop: 32, maxWidth: "46em" }}>
          Son descripciones generales para entender el sitio, no asesoría legal. Para el detalle de cada procedimiento, consulta la normativa vigente y el portal
          del SERCOP. Cómo se calcula cada señal está en la{" "}
          <Link href="/metodologia" className="inline-link">
            metodología
          </Link>
          .
        </p>
        <div className="page-end" />
      </div>
    </>
  );
}
