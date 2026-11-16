import type { DossierSection } from "@/lib/types";

/** Lists longer than this show the first VISIBLE items and fold the rest. */
const FOLD_OVER = 6;
const VISIBLE = 4;

export const slug = (title: string) =>
  title
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

type Block = { kind: "p"; text: string } | { kind: "ul"; items: string[] };

/** Splits a section body into paragraphs and bullet lists without altering any text. */
function parse(body: string): Block[] {
  const blocks: Block[] = [];
  for (const line of body.split("\n")) {
    if (!line.trim()) continue;
    const m = /^\s*[-•]\s+(.*)$/.exec(line);
    const last = blocks[blocks.length - 1];
    if (m) {
      if (last?.kind === "ul") last.items.push(m[1]);
      else blocks.push({ kind: "ul", items: [m[1]] });
    } else {
      blocks.push({ kind: "p", text: line });
    }
  }
  return blocks;
}

function Items({ items }: { items: string[] }) {
  return (
    <ul>
      {items.map((t, i) => (
        <li key={i}>{t}</li>
      ))}
    </ul>
  );
}

function List({ items }: { items: string[] }) {
  if (items.length <= FOLD_OVER) return <Items items={items} />;
  return (
    <>
      <Items items={items.slice(0, VISIBLE)} />
      <details className="fold">
        <summary>Mostrar {items.length - VISIBLE} elementos más</summary>
        <div>
          <Items items={items.slice(VISIBLE)} />
        </div>
      </details>
    </>
  );
}

/** Dossier index: one anchor per section. */
export function DossierIndex({ sections }: { sections: DossierSection[] }) {
  if (sections.length < 3) return null;
  return (
    <nav aria-label="Secciones del texto del expediente" className="dossier-index">
      <ul>
        {sections.map((s) => (
          <li key={s.title}>
            <a href={`#${slug(s.title)}`}>{s.title}</a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function DossierSectionView({ section }: { section: DossierSection }) {
  const id = slug(section.title);
  return (
    <div className="dossier__sec">
      <h3 id={id}>
        <a href={`#${id}`}>{section.title}</a>
      </h3>
      <div className="dossier__body">
        {parse(section.body).map((b, i) =>
          b.kind === "p" ? <p key={i}>{b.text}</p> : <List key={i} items={b.items} />,
        )}
      </div>
    </div>
  );
}
