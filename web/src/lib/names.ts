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
    return token.replace(/\p{L}+/gu, (part, offset: number) => caseWord(part, first && offset === 0));
  }
  return token.replace(core, caseWord(core, first));
}

function caseWord(word: string, first: boolean): string {
  const bare = word.replace(/\./g, "");
  if (ACRONYMS.has(bare) || ACRONYMS.has(word)) return word;
  if (word.length === 1) return first ? word : word.toLocaleLowerCase("es") === "y" ? "y" : word;
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
  let first = true;
  return name
    .split(/(\s+)/)
    .map((tok) => {
      if (!tok.trim()) return tok;
      const out = caseToken(tok, first);
      first = false;
      return out;
    })
    .join("");
}
