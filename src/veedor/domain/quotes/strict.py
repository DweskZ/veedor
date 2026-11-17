"""Deny-by-default screen: a passage is eligible only when it holds nothing that could be a person (pure).

The earlier screens look for *patterns* of personal data and failed twice: every new review found a new
pattern. This one inverts the question. After the names of the process's own companies and entities are
blanked, a passage is shown only if

1. it contains no cue of a person speaking, signing or being identified: a sign-off, a first-person
   introduction, a legal-representative formula, a spelled-out or abbreviated title followed by any word, a
   credential, licence, certificate, identity-card, passport or plate mention followed by an identifier, a
   vehicle plate, a run of seven or more digits (a company or public RUC and an amount are the only
   exceptions), a partial mobile number, a health reference to a person;
2. it contains no token of the person-name vocabulary, in any case;
3. every capitalised or ALL-CAPS word is vocabulary the data shows to be institutional (`Lexicon`), and a
   sentence may open only with an ordinary word. Unknown capitalised words make the passage ineligible, so a
   run of two or more of them, or a single unknown surname, never reaches a visitor;
4. when the passage is written in capitals (capitalisation carries no signal), every word must be an ordinary
   word or institutional vocabulary and none may be a person-name token.

The rules are in `docs/QUOTES.md`. The result is a short reason; `None` means eligible.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from veedor.domain.dossier.text import canonical, fold_chars
from veedor.domain.quotes.lexicon import Lexicon, fold, is_mixed_case, tokens

# --- 1. cues, matched on `canonical` text (accents, case and look-alikes folded) ---
_SIGN_OFF = re.compile(
    r"\b(?:atte|att|atentamente|atentos|cordialmente|cordial saludo|saludos?|saludo cordial|rubrica|"
    r"firm(?:a|as|ado|ada|ados|adas|ar|an|aron|e|en)|suscrit[oa]s?|suscribe|suscribimos)\b|"
    r"(?<![a-z0-9])f\.(?![a-z0-9])"
)
_FIRST_PERSON = re.compile(
    r"\byo\s*,|\bel suscrit[oa]\b|\bquien suscribe\b|\ben mi (?:calidad|condicion|representacion)\b|"
    r"\brepresentad[oa]s?\s+(?:legalmente\s+)?por\b|\brepresentante\s+legal\b|\brepresentantes\s+legales\b|"
    r"\badministrador(?:a)?\s+del\s+contrato\b|\bdelegad[oa]s?\b|\bapoderad[oa]s?\b|"
    r"\bgerente\s+general\b|\bmi nombre\b|\bme llamo\b|"
    r"\bsoy\s+(?:el|la)\b|\bcon\s+(?:c\.?i\.?|c\.?c\.?|cedula)\b|\bportador[a]?\b|\bidentificad[oa]\s+con\b"
)
_CREDENTIAL = re.compile(
    r"\b(?:licencia|registro|matricula|certificad[oa]|certificacion|cedula|pasaporte|placa|credencial|"
    r"senescyt|acreditacion|colegiatura|carnet|carne|votacion)\b[^.;\n]{0,40}?"
    r"(?<![a-z0-9\-])(?=[a-z\-]*\d)[a-z0-9\-]{5,}\b"
)
# "copia de la cédula de <name>" and a labelled "Nombre: ..." field name a person without a digit to catch.
_ID_OF_PERSON = re.compile(
    r"\bcedulas?\s+de\s+(?!identidad\b|ciudadania\b|ciudadanos?\b|votacion\b|los\b|las\b|la\b|el\b|cada\b|"
    r"todos\b|su\b|sus\b|un\b|una\b)[a-z]+"
)
_LABELLED_NAME = re.compile(r"\b(?:nombres?|apellidos?)\s*(?:y\s+apellidos?\s*)?:")
_HEALTH = re.compile(r"\bpacientes?\b|\bhistorias?\s+clinicas?\b")
_CONTACT = re.compile(
    r"@|\barroba\b|\bgmail|\bhotmail|\byahoo|\boutlook|\bwww\b|https?:|\.(?:com|ec|net|org|gob|edu)\b"
)
_MOBILE_PREFIX = re.compile(r"(?<![\d.,])(?:09\d{2,}|\+?593\s*\d|00593)")

# titles: person-introducing abbreviations and professions, followed by any capitalised (or unknown) word
_TITLE_WORDS = (
    "ing|ingeniero|ingeniera|dr|dra|doctor|doctora|lic|lcdo|lcda|licdo|licda|licenciado|licenciada|abg|"
    "abogado|abogada|econ|eco|economista|arq|arquitecto|arquitecta|bqf|qf|mgs|mg|mag|msc|mba|phd|cpa|sr|sra|srta|"
    "se[ñn]or|se[ñn]ora|se[ñn]orita|tnlgo|tlgo|tnte|crnl|cpnv|prof|profesor|profesora|don|do[ñn]a|biol|bioq|"
    "psic|odont|dip|dipl|magister|tecn[oó]logo|tecn[oó]loga|coronel|capit[aá]n|sargento"
)
_TITLE = re.compile(rf"\b(?i:{_TITLE_WORDS})\b\.?[\s:\-]*([A-Za-zÁÉÍÓÚÑáéíóúñ]+)")
_GLUED_TITLE = re.compile(
    r"\b(?i:sr|sra|srta|ing|dr|dra|lic|lcdo|lcda|abg|econ|arq)\b\.?(?=[A-ZÁÉÍÓÚÑ]{2})|"
    r"\b(?:Sr|Sra|Srta|Ing|Dr|Dra|Lic|Abg|Econ|Arq|sr|sra|srta|ing|dr|dra|lic|abg|econ|arq)(?=[A-ZÁÉÍÓÚÑ]{2})"
)
_STRONG_HONORIFIC = re.compile(
    r"\b(?i:sr|sra|srta|se[ñn]or|se[ñn]ora|se[ñn]orita|don|do[ñn]a)\b\.?\s*[A-Za-zÁÉÍÓÚÑáéíóúñ]{2,}"
)
_PLATE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z]{3}[ \-]?\d{3,4}|[A-Z]{2}[ \-]?\d{3}[ \-]?[A-Z])(?![A-Za-z0-9])|"
    r"(?<![A-Za-z0-9])[a-z]{3}-\d{3,4}(?![A-Za-z0-9])"
)

# --- digits ---
_DATE = re.compile(r"(?<!\d)(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})(?!\d)")
_YEAR_CODE = re.compile(r"(?<!\d)(?:19|20)\d{2}[-.]\d{1,6}(?!\d)")
_NUMBER = re.compile(r"\d(?:[ .\-\u00a0]?\d){6,}")
_AMOUNT_BEFORE = re.compile(
    r"(?:\$|us\$|usd|dolares?|valor|monto|total|precio|presupuesto|costo|cantidad|suma|unidades|"
    r"referencial|importe|anticipo|garantia|saldo)\W{0,3}$"
)
_AMOUNT_FORMAT = re.compile(r"\d{1,3}(?:\.\d{3})+,\d{1,2}|\d{1,3}(?:,\d{3})+\.\d{1,2}")


def blank_protected(text: str, protected: Iterable[str]) -> str:
    """The text with the process's own entity and company names replaced by a break."""
    folded = fold_chars(text)
    chars = list(text)
    for name in protected:
        needle = fold_chars(name).strip()
        if len(needle) < 3:
            continue
        start = folded.find(needle)
        while start != -1:
            end = start + len(needle)
            chars[start:end] = [" "] * len(needle)  # same length: offsets stay aligned
            folded = folded[:start] + " " * len(needle) + folded[end:]
            start = folded.find(needle, end)
    return "".join(chars)


def _long_number(canon: str) -> bool:
    cleaned = _YEAR_CODE.sub(" ", _DATE.sub(" ", canon))
    for match in _NUMBER.finditer(cleaned):
        digits = re.sub(r"\D", "", match.group())
        if len(digits) == 13 and digits[2] in "69" and digits.endswith("001"):
            continue  # a company or public-entity RUC
        before = cleaned[max(0, match.start() - 24) : match.start()]
        window = cleaned[match.start() : match.end() + 4]
        phone_like = digits.startswith(("0", "593"))
        if not phone_like and (_AMOUNT_BEFORE.search(before) or _AMOUNT_FORMAT.match(window)):
            continue
        return True
    return False


def _cue(plain: str, canon: str, lexicon: Lexicon | None) -> str | None:
    if _SIGN_OFF.search(canon):
        return "sign_off"
    if _FIRST_PERSON.search(canon):
        return "self_identification"
    if _HEALTH.search(canon):
        return "health_reference"
    if _PLATE.search(plain):
        return "plate"
    if _CREDENTIAL.search(canon) or _ID_OF_PERSON.search(canon):
        return "credential_id"
    if _LABELLED_NAME.search(canon):
        return "labelled_name"
    if _CONTACT.search(canon):
        return "contact"
    if _long_number(canon) or _MOBILE_PREFIX.search(_DATE.sub(" ", canon)):
        return "long_number"
    if _GLUED_TITLE.search(plain):
        return "title_name"
    mixed = is_mixed_case(plain)
    for match in _TITLE.finditer(plain):
        nxt = match.group(1)
        if nxt[0].isupper() and mixed:
            return "title_name"
        if (
            lexicon is not None
            and fold(nxt) not in lexicon.lowercase
            and fold(nxt) not in lexicon.capitalised
        ):
            return "title_name"
    if not mixed and _STRONG_HONORIFIC.search(plain):
        return "title_name"
    return None


def _unknown_lowercase_pair(words: list, lexicon: Lexicon) -> bool:
    """Two consecutive lower-case words of 4 or more letters that are in neither list: a rare given name and
    surname typed in lower case ("patricio garcia") looks like this, and so does a rare technical bigram
    (the price of refusing those is about 0.4 % of the passages)."""
    previous_unknown = False
    for word in words:
        unknown = len(word.raw) >= 4 and word.raw[0].islower() and not lexicon.known(word.folded)
        if unknown and previous_unknown:
            return True
        previous_unknown = unknown
    return False


def strict_reason(
    text: str,
    *,
    lexicon: Lexicon | None = None,
    protected_names: Iterable[str] = (),
    name_vocabulary: frozenset[str] = frozenset(),
) -> str | None:
    """Why the passage is not eligible under the deny-by-default rules, or ``None``.

    Without a `lexicon` only the cue rules and the person-name vocabulary apply: that is never enough to
    show a passage, so the build and the API always pass one."""
    plain = blank_protected(text, protected_names)
    canon = canonical(plain)
    if (reason := _cue(plain, canon, lexicon)) is not None:
        return reason
    words = list(tokens(plain))
    if name_vocabulary and any(w.folded in name_vocabulary for w in words if len(w.raw) >= 3):
        return "name_token"
    if lexicon is None:
        return None
    if _unknown_lowercase_pair(words, lexicon):
        return "unknown_lowercase_pair"
    if not is_mixed_case(plain):
        unknown = any(len(w.raw) >= 2 and not lexicon.known(w.folded) for w in words)
        return "caps_unknown_word" if unknown else None
    for word in words:
        if len(word.raw) < 2 or not (word.capital or word.all_caps):
            continue
        if word.folded in lexicon.capitalised:
            continue
        if word.initial and word.folded in lexicon.lowercase and not word.all_caps:
            continue
        return "unknown_capitalised"
    return None
