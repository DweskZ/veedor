"""Eligibility pipeline for a passage that may be shown as a quote (pure).

A passage of free text written by a bidder or by the buying entity is eligible only when it passes,
in this order:

1. the asker check: an enquiry whose asker is a natural person (or an unidentified party) is dropped
   whole, because the exchange can sign or address that person;
2. `safe_free_text` with the process's known person names: the text is withheld when masking finds
   anything (a party's name, a natural-person RUC, a cédula, an honorific followed by a name);
3. the identifier scan of `domain.investigation.identifiers` (natural-person RUC, valid cédula, written
   plain, dotted, dashed or spaced, with Unicode digits);
4. stricter personal-data cues that the masking heuristic does not cover: an honorific followed by any
   word in any case ("ing. juan"), a salutation or a closing that is followed by a name, an e-mail
   address, a telephone number;
5. the deny-by-default screen of `domain.quotes.strict`: nothing that could be a person may remain
   (sign-offs, first-person identification, titles, credentials, plates, long numbers, any capitalised word
   the data does not show to be institutional vocabulary, person-name tokens in any case);
6. the unsafe-text screen of the dossier layer (`is_unsafe_text`: accusation and inference wording,
   links, markup, instruction-like text, hidden or look-alike characters), the third-party allegation
   stems of `domain.quotes.allegation` and an obfuscation pass (digit and symbol look-alikes, letters
   separated by spaces, dots or hyphens).

A passage is never rewritten: it is shown exactly as published or not at all. When masking would have
to replace anything the whole passage is dropped, so no quote ever contains a placeholder.

The result is a category for the counters (`personal` or `unsafe`) and a fine-grained reason.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from veedor.domain.dossier.safety import is_unsafe_text
from veedor.domain.dossier.text import canonical
from veedor.domain.investigation.identifiers import document_has_personal_identifier
from veedor.domain.masking import MASKED_NAME, TEXT_PLACEHOLDER, UNIDENTIFIED_NAME, safe_free_text
from veedor.domain.quotes.allegation import has_allegation_wording
from veedor.domain.quotes.deny import is_denied
from veedor.domain.quotes.gate import rules_hit
from veedor.domain.quotes.lexicon import Lexicon
from veedor.domain.quotes.names import probable_person_name
from veedor.domain.quotes.strict import blank_protected, strict_reason

PERSONAL = "personal"
UNSAFE = "unsafe"


@dataclass(frozen=True, slots=True)
class Verdict:
    eligible: bool
    category: str | None = None
    reason: str | None = None


ELIGIBLE = Verdict(True)


def _drop(category: str, reason: str) -> Verdict:
    return Verdict(False, category, reason)


# --- stricter personal-data cues (matched on `canonical`: lowercase, accents and look-alikes folded) ---
_HONORIFIC = re.compile(
    r"(?<![a-z])(?:sr|sra|srta|dr|dra|ing|arq|abg|lcdo|lcda|lic|econ|msc|mgs|prof|tnte|crnl|cpnv"
    r"|don|dona)\.?\s+[a-z]{2,}"
)
# "señor Rúales" names a person; "señor oferente" and "señora presidenta" address a role.
_SENOR = re.compile(
    r"(?<![a-z])(?:senor|senora|senorita)\.?\s+(?!(?:oferente|proveedor|president|ministr|alcalde|"
    r"gerente|director|administrador|contratista|participante|comision|delegad|represent)\w*)[a-z]{2,}"
)
_NAME = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{1,}"
_TWO_NAMES = re.compile(rf"{_NAME}(?:\s+(?:de|del|la|los|las|y)){{0,2}}\s+{_NAME}")
_CLOSING = re.compile(r"\b(?:atentamente|cordialmente|saludos cordiales|saludo cordial|saludos|att)\b", re.I)
_ATTRIBUTION = re.compile(r"\b(?:firmado por|elaborado por|suscrito por)\b", re.I)
_CLOSING_FILLER = frozenset(
    "cordial cordiales saludos saludo estimado estimados estimada estimadas de usted ustedes muy su sus att "
    "atentamente cordialmente gracias por favor un con y a el la".split()
)
_TAIL_CHARS = 80
_GENERIC_ADDRESSEE = frozenset(
    "oferente oferentes proveedor proveedores entidad entidades participante participantes ofertante "
    "ofertantes contratista contratistas postulante postulantes senor senora senores usuario usuarios "
    "cliente clientes comision comisiones companero companeros colega colegas equipo todos interesado "
    "interesados interesadas posible posibles cuerpo miembros gad gobierno ministerio municipio municipal "
    "hospital universidad empresa direccion junta consejo secretaria prefectura alcaldia instituto banco "
    "camara federacion area departamento unidad personal compras comite sres".split()
)
# Cues on the original text. A professional title followed by two capitalised words names a person
# ("Ingeniera Kerlly Lizbeth ..."); "Señor" glued to capitals is a letter's address line ("SeñorBORIS ...");
# "yo <name>, en mi calidad de" is a person introducing themselves.
_TITLE_NAME = re.compile(
    rf"\b(?:Ingenier[oa]|Doctor[a]?|Licenciad[oa]|Abogad[oa]|Arquitect[oa]|Economista)\s+{_NAME}\s+{_NAME}"
)
# A name followed by an official title in capitals ("Pedro Mora SECRETARIO DE ...") is a signature or an
# address line. (Patterns for "role noun + name" and for owner lists were tried and removed: 289 and 82
# stored passages matched, nearly all ordinary requirements such as "Personal Técnico Clave"; the few real
# cases are in `domain.quotes.deny`.)
_TITLE_AFTER_NAME = re.compile(
    rf"{_NAME}\s+{_NAME}(?:\s+{_NAME})?\s*(?:SECRETARI|DIRECTOR|GERENTE|ADMINISTRADOR|ALCALD|MINISTR|COORDINADOR|"
    r"PRESIDENT|SUBSECRETARI|RECTOR|JEFE|DELEGAD|REPRESENTANTE|COMISARI|CONCEJAL|PREFECT)"
)
_ATTACHED_SENOR = re.compile(r"\bSe[ñn]or(?:a|ita)?(?=[A-ZÁÉÍÓÚÑ]{2})")
_SELF_INTRODUCTION = re.compile(
    r"\byo\s+(?:[a-záéíóúñ]+,?\s+){2,5}en\s+mi\s+(?:calidad|condici[oó]n)\b", re.IGNORECASE
)
_SALUTATION = re.compile(rf"\bEstimad[oa]s?\s+({_NAME})")
_EMAIL = re.compile(
    r"[a-z0-9._%+\-]+\s?(?:@|\(\s?at\s?\)|\[\s?at\s?\]|\sarroba\s)\s?[a-z0-9\-]+"
    r"(?:\s?(?:\.|punto|dot)\s?[a-z0-9\-]+)+"
)
_PHONE_NUMBER = re.compile(r"(?<![0-9])(?:\+?593|0)[\s.\-()]*[2-9](?:[\s.\-()]*[0-9]){7,8}(?![0-9])")
_PHONE_CUE = re.compile(
    r"\b(?:tel|telf|telef\w*|celular|cel|whatsapp|fono|movil|convencional|ext)\b[^0-9]{0,12}[0-9]"
    r"(?:[\s.\-()]*[0-9]){4,}"
)

# --- obfuscated accusation wording ---
_LEET = str.maketrans("013457@$", "oieastas")
_EXTRA_FORBIDDEN = re.compile(r"\b(?:rob(?:ar|aron|aba\w*|ad[oa]s?)|hurt(?:ar|aron|o|ado))\b")
_SEPARATORS = re.compile(r"[\s.\-_*·•,;:/|\\'\"`~^+=()\[\]{}<>]+")
# Stems of at least five letters, searched in the text with every separator removed ("f r a u d e").
_COMPACT_STEMS = (
    "fraud", "corrupt", "corrupci", "soborn", "cohecho", "colusi", "malvers", "peculad", "prevaric",
    "defraud", "testaferr", "extors", "chantaj", "sobreprecio", "delincu", "mafia", "coima", "desfalco",
    "lavadodeactivos", "lavadodedinero",
)  # fmt: skip


def _ascii_digits(text: str) -> str:
    """NFKC, format characters removed, every Unicode decimal digit written as ASCII."""
    out = []
    for ch in unicodedata.normalize("NFKC", text):
        if unicodedata.category(ch) == "Cf":
            continue
        out.append(str(unicodedata.decimal(ch)) if unicodedata.category(ch) == "Nd" else ch)
    return "".join(out)


def _without_names(canon: str, protected: Iterable[str]) -> str:
    for name in protected:
        needle = canonical(name).strip()
        if len(needle) >= 3:
            canon = canon.replace(needle, " ")
    return canon


def _is_mixed_case(text: str) -> bool:
    """Capitalisation carries information only when the text is not written in capitals."""
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 10 and sum(ch.isupper() for ch in letters) / len(letters) < 0.6


def _signature_cue(text: str) -> bool:
    """A closing or an attribution that is followed by a name (mixed case) or, in capitals, by words."""
    mixed = _is_mixed_case(text)
    for match in _CLOSING.finditer(text):
        tail = text[match.end() : match.end() + _TAIL_CHARS]
        if mixed and _TWO_NAMES.search(tail):
            return True
        words = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", tail) if canonical(w) not in _CLOSING_FILLER]
        if not mixed and len(text) - match.end() <= _TAIL_CHARS and len(words) >= 2:
            return True
    return mixed and any(_TWO_NAMES.match(text[m.end() :].lstrip()) for m in _ATTRIBUTION.finditer(text))


def _salutation_cue(text: str) -> bool:
    if not _is_mixed_case(text):
        return False
    return any(canonical(m.group(1)) not in _GENERIC_ADDRESSEE for m in _SALUTATION.finditer(text))


def _personal_cue(text: str, protected: Iterable[str]) -> str | None:
    canon = canonical(text)
    plain = _without_names(canon, protected)
    if _HONORIFIC.search(plain) or _SENOR.search(plain):
        return "honorific"
    if _signature_cue(text):
        return "signature"
    if _ATTACHED_SENOR.search(text) or _SELF_INTRODUCTION.search(text):
        return "self_or_address_line"
    if _is_mixed_case(text) and _TITLE_NAME.search(text):
        return "honorific"
    if _salutation_cue(text):
        return "salutation"
    if _TITLE_AFTER_NAME.search(text):
        return "name_before_title"
    ascii_text = _ascii_digits(canon)
    if _EMAIL.search(ascii_text):
        return "email"
    if _PHONE_NUMBER.search(ascii_text) or _PHONE_CUE.search(ascii_text):
        return "phone"
    return None


def has_accusation_wording(text: str) -> bool:
    """Accusation or inference wording, also hidden by look-alike digits or symbols or by separators between
    letters (and nothing else: links, markup and instruction-like text are not considered)."""
    from veedor.domain.dossier.vocabulary import FORBIDDEN_PATTERN, INFERENCE_PATTERN

    canon = canonical(text)
    leet = canon.translate(_LEET)
    if _EXTRA_FORBIDDEN.search(canon) or _EXTRA_FORBIDDEN.search(leet):
        return True
    if has_allegation_wording(text) or has_allegation_wording(text.translate(_LEET)):
        return True
    if any(p.search(form) for p in (FORBIDDEN_PATTERN, INFERENCE_PATTERN) for form in (canon, leet)):
        return True
    compact = _SEPARATORS.sub("", leet)
    return any(stem in compact for stem in _COMPACT_STEMS)


def has_obfuscated_wording(text: str) -> bool:
    """Accusation wording hidden by look-alike digits or symbols, or by separators between letters."""
    canon = canonical(text)
    leet = canon.translate(_LEET)
    if _EXTRA_FORBIDDEN.search(canon) or _EXTRA_FORBIDDEN.search(leet):
        return True
    if is_unsafe_text(text.translate(_LEET)):
        return True
    compact = _SEPARATORS.sub("", leet)
    return any(stem in compact for stem in _COMPACT_STEMS)


def check_passage(
    text: str,
    *,
    person_names: Iterable[str] = (),
    protected_names: Iterable[str] = (),
    asker_is_person: bool = False,
    name_vocabulary: frozenset[str] = frozenset(),
    lexicon: Lexicon | None = None,
) -> Verdict:
    """Run the whole pipeline over one passage (see the module docstring for the order)."""
    names = list(person_names)
    protected = list(protected_names)
    if asker_is_person:
        return _drop(PERSONAL, "asker_person")
    if is_denied(text):
        return _drop(PERSONAL, "denied_passage")
    if safe_free_text(text, names, protected_names=protected)[1]:
        return _drop(PERSONAL, "name_or_identifier")
    if TEXT_PLACEHOLDER in text or MASKED_NAME in text or UNIDENTIFIED_NAME in text:
        return _drop(PERSONAL, "placeholder")
    if document_has_personal_identifier(text):
        return _drop(PERSONAL, "identifier")
    cue = _personal_cue(text, protected)
    if cue:
        return _drop(PERSONAL, cue)
    if probable_person_name(text, name_vocabulary, protected):
        return _drop(PERSONAL, "probable_person_name")
    if has_allegation_wording(text):
        return _drop(UNSAFE, "allegation_wording")
    if is_unsafe_text(text):
        return _drop(UNSAFE, "unsafe_text")
    if has_obfuscated_wording(text):
        return _drop(UNSAFE, "obfuscated_wording")
    if reason := strict_reason(
        text, lexicon=lexicon, protected_names=protected, name_vocabulary=name_vocabulary
    ):
        return _drop(PERSONAL, f"strict_{reason}")
    # The release gate (`domain.quotes.gate`: the reviewer's seven rules and the project's own) is part of the
    # screen, so a mart built by this function cannot fail the gate by construction; the gate script then
    # checks it independently.
    if hits := [r for r in rules_hit(blank_protected(text, protected)) if r != "o9_accusation_stem"]:
        return _drop(PERSONAL, f"gate_{hits[0]}")
    return ELIGIBLE
