import data from "@/data/glossary.json";

export interface GlossaryEntry {
  term: string;
  aliases: string[];
  definition_es: string;
  source: string;
}

export const norm = (s: string) =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();

/** Stable anchor id for a term on /glosario. */
export const termId = (term: string) => norm(term).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const GLOSSARY: GlossaryEntry[] = data.items;

const INDEX = new Map<string, GlossaryEntry>();
for (const e of GLOSSARY) {
  INDEX.set(norm(e.term), e);
  for (const a of e.aliases) INDEX.set(norm(a), e);
}

/** Finds an entry by term or alias, ignoring case and accents. */
export const findTerm = (key: string): GlossaryEntry | undefined => INDEX.get(norm(key));
