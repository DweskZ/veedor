import { fmtDate } from "@/lib/format";
import { pickQuotes, type QuoteItem, type QuotePart, type Quotes } from "@/lib/provenance";
import { Icon } from "./Icon";

const HEAD: Record<QuotePart["kind"], (it: { author_kind?: QuoteItem["author_kind"] }) => string> = {
  enquiry_question: (it) => (it.author_kind === "entidad" ? "Pregunta de la entidad" : it.author_kind === "oferente" ? "Pregunta de un oferente" : "Pregunta del proceso"),
  enquiry_answer: () => "Respuesta de la entidad",
  award_text: () => "Texto de la adjudicación",
};

/** Passages longer than this show five lines and a native "Ver cita completa" disclosure; the text itself is never cut. */
export const LONG_QUOTE = 320;

/** One passage. The text is a React child (escaped), never HTML, and never turned into links. */
export function Passage({ part, date, author_kind, truncated }: { part: QuotePart; date: string | null; author_kind?: QuoteItem["author_kind"]; truncated?: boolean }) {
  const head = HEAD[part.kind]({ author_kind });
  const long = part.text.length > LONG_QUOTE;
  return (
    <figure className="qt__p">
      <blockquote className={`qt__text ${long ? "qt__text--clamp" : ""}`}>{part.text}{truncated ? " […]" : ""}</blockquote>
      {long ? (
        <details className="qt__full">
          <summary>
            <span className="qt__full-open">Ver cita completa</span>
            <span className="qt__full-close">Ocultar cita completa</span>
          </summary>
        </details>
      ) : null}
      <figcaption className="qt__by">
        <b>{head}</b>
        {date ? ` · ${fmtDate(date)}` : ""}
        {part.source_field ? (
          <>
            {" · campo "}
            <span className="num">{part.source_field}</span>
          </>
        ) : null}
      </figcaption>
    </figure>
  );
}

function omittedLine(q: Quotes): string | null {
  const { personal_data, unsafe, below_relevance } = q.omitted;
  const total = personal_data + unsafe + below_relevance;
  if (total === 0) return null;
  const parts = [
    personal_data ? `${personal_data} por contener datos personales` : null,
    unsafe ? `${unsafe} por contenido no apto para mostrar` : null,
    below_relevance ? `${below_relevance} por no estar relacionados con las señales del proceso` : null,
  ].filter(Boolean);
  return `Se dejaron fuera ${total === 1 ? "1 pasaje" : `${total} pasajes`}: ${parts.join(", ")}.`;
}

/** Anchor id of the quote at position `i`, used by the signal cards that point to it. */
export const quoteAnchor = (i: number) => `cita-${i}`;

export function QuotesBlock({ quotes }: { quotes: Quotes | null }) {
  const items = quotes ? pickQuotes(quotes) : [];
  if (!quotes || items.length === 0) {
    const left = quotes ? omittedLine(quotes) : null;
    return (
      <p className="muted">
        {quotes ? "No hay citas de la fuente para mostrar en este proceso." : "Las citas de la fuente no están disponibles ahora."}
        {left ? ` ${left}` : ""}
      </p>
    );
  }
  const left = omittedLine(quotes);
  return (
    <div className="qt">
      <p className="qt__note">
        <Icon name="quote" size={20} />
        <span>
          <b>Estas palabras no son de Veedor.</b> Las escribieron oferentes o la entidad que compra y se muestran tal como se publicaron, como texto sin
          formato.{left ? ` ${left}` : ""}
        </span>
      </p>
      <ol className="qt__list">
        {items.map((it, i) => (
          <li key={`${it.kind}-${i}`} id={quoteAnchor(i)} className="qt__item">
            <Passage part={it} date={it.date} author_kind={it.author_kind} truncated={it.truncated} />
            {it.pair ? <Passage part={it.pair} date={null} truncated={false} author_kind={null} /> : null}
            {it.related_signal ? (
              <p className="qt__rel">
                Relacionada con la señal{" "}
                <a href={`#sig-${it.related_signal}`} className="inline-link">
                  {it.related_signal_label_es ?? it.related_signal}
                </a>
              </p>
            ) : null}
          </li>
        ))}
      </ol>
      {quotes.note_es ? <p className="muted small qt__api">{quotes.note_es}</p> : null}
      <p className="muted small">
        {quotes.available_total > items.length
          ? `Se muestran ${items.length} de ${quotes.available_total} pasajes disponibles en el expediente original.`
          : `Se ${items.length === 1 ? "muestra 1 pasaje" : `muestran ${items.length} pasajes`}.`}
      </p>
    </div>
  );
}
