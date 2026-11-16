/**
 * Display-only case for official names written in ALL CAPS (entities, companies, process titles).
 * Deterministic and pure. It never touches identifiers (RUC, OCID, process codes): callers keep the
 * original spelling for the `title` attribute and for the sources panel.
 */

/** Kept in capitals wherever they appear: institutions, legal forms and common abbreviations. */
const ACRONYMS = new Set([
  "GAD", "GADM", "GADP", "GADMC", "GADPR", "EP", "EPN", "EMP", "EMAPA", "IESS", "SRI", "SERCOP", "ISSFA", "ISSPOL", "MSP", "MIES", "MAG", "MTOP",
  "MIDUVI", "MINEDUC", "CNEL", "CNT", "CELEC", "ESPOL", "ESPE", "ESPOCH", "UTPL", "PUCE", "UCE", "UTA", "UTC", "UTN", "ONG", "UE", "UNE", "UPS",
  "SA", "SAS", "CA", "CIA", "LTDA", "CLTDA", "MIT", "TV", "USD", "ECU", "GPS", "IVA", "CPC", "PYMES", "TIC", "TICS", "SENAE", "INEC", "BCE", "BIESS",
  "DIGMAT", "IASA", "ASTINAVE", "DINARDAP", "SENESCYT", "SENPLADES", "ARCOTEL", "ARCSA", "INIAP", "INAMHI", "SECOB", "SECAP", "SETEC", "ECU911", "FFAA",
  "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "XIII", "XIV", "XV",
]);

/** Lower-case in the middle of a name. */
const SMALL = new Set(["de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "a", "al", "por", "para", "con", "sin", "su", "sus", "que"]);

const LETTERS = /\p{L}/gu;
const UPPER = /\p{Lu}/gu;

/** True when the text is written (almost) entirely in capitals, so changing its case is safe and useful. */
export function isAllCaps(text: string): boolean {
  const letters = text.match(LETTERS)?.length ?? 0;
  if (letters < 4) return false;
  const upper = text.match(UPPER)?.length ?? 0;
  return upper / letters >= 0.85;
}

const hasVowel = (w: string) => /[AEIOUÁÉÍÓÚÜ]/i.test(w);

function cap(word: string): string {
  const lower = word.toLocaleLowerCase("es");
  return lower.charAt(0).toLocaleUpperCase("es") + lower.slice(1);
}

/** One whitespace-free token: may carry punctuation, hyphens, slashes and dots. */
function caseToken(token: string, first: boolean): string {
  if (/\d/.test(token)) {
    // Codes and numbers ("N° 12", "10D01") are untouched; the words around them in a hyphen compound are cased.
    if (!/-/.test(token)) return token;
    return token
      .split("-")
      .map((part) => (/\d/.test(part) || !part ? part : caseWord(part.replace(/[^\p{L}.]/gu, ""), false) || part))
      .join("-");
  }
  const core = token.replace(/^[^\p{L}]+|[^\p{L}]+$/gu, "");
  if (!core) return token;
  // Dotted initials such as S.A., C.A., E.P., S.A.S.: keep.
  if (/^(\p{Lu}\.)+\p{Lu}?\.?$/u.test(token.replace(/^[^\p{L}]+/u, "").replace(/[,;:)]+$/u, ""))) return token;
  if (/[-/]/.test(core)) {
    // Hyphen or slash compounds: each part on its own, never as the first word of the name.
    // A word after a hyphen starts a new phrase ("Salud-Los Ríos"), so it is never lower-cased; a slash keeps "y/o".
    return token.replace(/\p{L}+/gu, (part, offset: number) => caseWord(part, (first && offset === 0) || token[offset - 1] === "-"));
  }
  return token.replace(core, caseWord(core, first));
}

function caseWord(word: string, first: boolean): string {
  const bare = word.replace(/\./g, "");
  if (ACRONYMS.has(bare) || ACRONYMS.has(word)) return word;
  if (word.length === 1) return first || !"YEOU".includes(word) ? word : word.toLocaleLowerCase("es");
  // A short run of consonants is an acronym (GPSC, MTV); words with vowels are words.
  if (!hasVowel(word) && word.length <= 5) return word;
  if (!first && SMALL.has(word.toLocaleLowerCase("es"))) return word.toLocaleLowerCase("es");
  return cap(word);
}

/**
 * Title-cases an ALL CAPS official name, keeping acronyms and legal forms.
 * Text that is already mixed case is returned unchanged.
 */
export function displayName(name: string | null | undefined): string {
  if (!name) return "";
  if (!isAllCaps(name)) return name;
  // A word that opens a phrase is never lower-cased: the first of the name, the first after a dash and the first in parentheses or quotes.
  const DASH = /[-–—]$/;
  const OPENS = /^[-–—("“«[]/;
  let first = true;
  const parts = name.split(/(\s+)/);
  const tokens = parts.filter((p) => p.trim());
  const nextWord = (i: number) => tokens[i + 1]?.replace(/[^\p{L}]/gu, "").toLocaleUpperCase("es");
  let ti = -1;
  return parts
    .map((tok) => {
      if (!tok.trim()) return tok;
      ti += 1;
      let startsPhrase = first || OPENS.test(tok) || (ti > 0 && DASH.test(tokens[ti - 1]));
      // "Los Ríos" (province) and "Los Ceibos" (district) are names that carry their article: it stays in capitals.
      if (tok.toLocaleUpperCase("es") === "LOS" && ["RIOS", "RÍOS", "CEIBOS"].includes(nextWord(ti) ?? "")) startsPhrase = true;
      const out = caseToken(tok, startsPhrase);
      first = false;
      return out;
    })
    .join("");
}
