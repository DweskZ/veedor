"""Personal-data masking rules (pure, no I/O).

Structured parties
    A RUC whose third digit is 0-5 belongs to a natural person. Natural persons are never named in
    API responses: the name becomes ``"Persona natural"`` and the RUC keeps its first four digits
    followed by nine asterisks. Companies (third digit 9) and public entities (6) are shown as is.
    A party with no usable RUC is masked by default (``"Persona natural o sin identificar"``) unless
    its name carries an explicit legal-entity marker (see `is_legal_entity_name`).

Free text (`mask_free_text`)
    Descriptions, notes and dossier text can contain personal data. The function masks natural-person
    RUCs, cédulas (check-digit validated, or following a keyword such as "C.I."), the known names of
    the process's natural-person parties (case, accent and word-order tolerant) and
    honorific-plus-name runs ("Ing. Juan Pérez"). It is a heuristic: it can miss a name that is not in
    ``known_person_names`` and has no honorific. Callers that need certainty withhold the text
    (`safe_free_text`).

Internal tables keep the real values; masking happens at the API boundary.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

NATURAL_PERSON = "natural_person"
COMPANY = "company"
PUBLIC_ENTITY = "public_entity"
UNKNOWN = "unknown"

MASKED_NAME = "Persona natural"
UNIDENTIFIED_NAME = "Persona natural o sin identificar"
TEXT_PLACEHOLDER = "[persona natural]"
_MASK_SUFFIX = "*********"
_PLACEHOLDER_NAMES = frozenset({MASKED_NAME, UNIDENTIFIED_NAME})
_MASKED_RUC = re.compile(r"^[0-9]{4}\*{9}$")
_NATURAL_HINTS = {NATURAL_PERSON, "natural", "persona_natural", "persona natural"}
_NAME_KEYS_FOR_BARE_RUC = ("name", "legal_name", "supplier_name")

# (ruc field, name field, kind field or None)
PartyFields = tuple[str, str, str | None]


# --------------------------------------------------------------------------- structured parties


def kind_from_ruc(ruc: str | None) -> str:
    """Classify a RUC (13 digits) or cédula (10 digits) by its third digit."""
    if not ruc or not _is_ascii_digits(ruc) or len(ruc) not in (10, 13):
        return UNKNOWN
    third = ruc[2]
    if third in "012345":
        return NATURAL_PERSON
    if third == "6":
        return PUBLIC_ENTITY
    if third == "9":
        return COMPANY
    return UNKNOWN


def _is_ascii_digits(text: str) -> bool:
    return text.isascii() and text.isdigit()


def is_natural_person(ruc: str | None, kind: str | None = None) -> bool:
    """True when the RUC or an explicit kind hint says natural person (conservative)."""
    if kind_from_ruc(ruc) == NATURAL_PERSON:
        return True
    return (kind or "").strip().lower() in _NATURAL_HINTS


def mask_ruc(ruc: str) -> str:
    return ruc[:4] + _MASK_SUFFIX


# Legal-entity markers. Anything without one of them and without a company/public RUC is masked.
_WORD_MARKERS = frozenset(
    "CONSORCIO ASOCIACION FUNDACION CORPORACION COOPERATIVA COMPANIA EMPRESA UNIVERSIDAD GAD GOBIERNO "
    "MUNICIPIO MUNICIPAL MINISTERIO INSTITUTO HOSPITAL SECRETARIA PREFECTURA CONSEJO JUNTA DIRECCION "
    "SUPERINTENDENCIA BANCO CAMARA FEDERACION SINDICATO COMITE EP".split()
)
_SUFFIX_MARKER = re.compile(
    r"(?:^|[\s,])(?:S\.?\s?A\.?\s?S?\.?|CIA\.?(?:\s+LTDA\.?)?|LTDA\.?|C\.?\s?A\.?|E\.?\s?P\.?"
    r"|S\.?\s?R\.?\s?L\.?|CORP\.?|INC\.?|LLC)\s*$"
)


def _fold(text: str) -> str:
    """Uppercase and strip accents character by character, so offsets stay aligned with `text`."""
    out: list[str] = []
    for ch in text:
        base = unicodedata.normalize("NFD", ch)[0]
        up = base.upper()
        out.append(up if len(up) == 1 else base)
    return "".join(out)


def is_legal_entity_name(name: str | None) -> bool:
    """True only when the name carries an explicit legal-entity marker (S.A., CIA. LTDA., EP,
    CONSORCIO, FUNDACIÓN, UNIVERSIDAD, GAD, MINISTERIO, HOSPITAL ...). The default is "not an entity"."""
    if not name:
        return False
    folded = _fold(name).strip()
    if any(word in _WORD_MARKERS for word in re.findall(r"[A-Z0-9]+", folded)):
        return True
    return bool(_SUFFIX_MARKER.search(folded))


def mask_party(
    ruc: str | None, name: str | None, kind: str | None = None
) -> tuple[str | None, str | None, str]:
    """Return ``(ruc, name, kind)`` with the masking rules applied."""
    if is_natural_person(ruc, kind):
        return (mask_ruc(ruc) if ruc else None, MASKED_NAME if name else None, NATURAL_PERSON)
    derived = kind_from_ruc(ruc)
    if derived != UNKNOWN:
        return ruc, name, derived
    if is_legal_entity_name(name):
        return ruc, name, UNKNOWN
    if name in _PLACEHOLDER_NAMES or (ruc and _MASKED_RUC.match(ruc)):  # already masked: stay idempotent
        return ruc, name, NATURAL_PERSON if name == MASKED_NAME or ruc else UNKNOWN
    return (mask_ruc(ruc) if ruc else None, UNIDENTIFIED_NAME if name else None, UNKNOWN)


def is_masked_party(ruc: str | None, name: str | None, kind: str | None = None) -> bool:
    """True when `mask_party` would hide this party's name."""
    return bool(name) and mask_party(ruc, name, kind)[1] != name


def _mask_institution(ruc: str | None, name: str | None) -> tuple[str | None, str | None]:
    """Buyers are public entities: only a natural-person RUC is masked."""
    if is_natural_person(ruc):
        return (mask_ruc(ruc) if ruc else None, MASKED_NAME if name else None)
    return ruc, name


def mask_fields(data: dict[str, Any], parties: Iterable[PartyFields]) -> dict[str, Any]:
    """Apply the party rules to the declared field triples of a flat record (returns a copy).

    Fields whose RUC key starts with ``buyer`` are institutions and use the natural-RUC rule only.
    """
    out = dict(data)
    for ruc_key, name_key, kind_key in parties:
        if ruc_key not in out and name_key not in out:
            continue
        if ruc_key.startswith("buyer"):
            out[ruc_key], out[name_key] = _mask_institution(out.get(ruc_key), out.get(name_key))
            continue
        kind_in = out.get(kind_key) if kind_key else None
        ruc, name, kind = mask_party(out.get(ruc_key), out.get(name_key), kind_in)
        out[ruc_key], out[name_key] = ruc, name
        if kind_key:
            out[kind_key] = kind
    return out


# --------------------------------------------------------------------------------- free text

_RUC_IN_TEXT = re.compile(r"(?<![0-9])[0-9]{13}(?![0-9])")
_CEDULA_IN_TEXT = re.compile(r"(?<![0-9])[0-9]{10}(?![0-9])")
_CEDULA_DASHED = re.compile(r"(?<![0-9])([0-9]{9})-([0-9])(?![0-9])")
_ID_KEYWORD = re.compile(
    r"(?i)(?<![A-Za-z])((?:c\.?\s?c\.?|c\.?\s?i\.?|c[eé]dula(?:\s+de\s+(?:identidad|ciudadan[ií]a))?"
    r"|ruc\s*/\s*pasaporte|pasaporte|ruc)\s*(?:n[°ºo]\.?\s*)?[:#.]?\s*)([0-9]{10})(?![0-9])"
)
_HONORIFIC_RUN = re.compile(
    r"(?<![A-Za-zÁÉÍÓÚÑáéíóúñ])(?i:sr|sra|srta|dr|dra|ing|arq|ab|abg|lcdo|lcda|econ|msc|mgs|prof|tnte"
    r"|crnl|cpnv)(?![A-Za-zÁÉÍÓÚÑáéíóúñ])\.?\s+"
    r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’]+"
    r"(?:\s+(?:(?i:de|del|la|las|los|y)\s+){0,2}[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’]+){0,3}"
)
_NAME_STOPWORDS = frozenset({"DE", "DEL", "LA", "LAS", "LOS", "Y", "E"})
_WORD = re.compile(r"[A-Z0-9]+")
_GAP = re.compile(r"^[\s,.\-]*$")
_MIN_SINGLE_TOKEN = 4


def is_valid_cedula(number: str) -> bool:
    """Ecuadorian cédula check: province 01-24 or 30, third digit < 6, modulo-10 check digit."""
    if len(number) != 10 or not _is_ascii_digits(number):
        return False
    if not (1 <= int(number[:2]) <= 24 or int(number[:2]) == 30) or int(number[2]) > 5:
        return False
    total = 0
    for index, digit in enumerate(number[:9]):
        product = int(digit) * (2 if index % 2 == 0 else 1)
        total += product - 9 if product > 9 else product
    return (10 - total % 10) % 10 == int(number[9])


def _mask_cedula(number: str) -> str:
    return number[:4] + "******"


def _name_token_sets(names: Iterable[str]) -> list[frozenset[str]]:
    sets = []
    for name in names:
        tokens = frozenset(t for t in _WORD.findall(_fold(name)) if t not in _NAME_STOPWORDS and len(t) >= 2)
        if tokens:
            sets.append(tokens)
    return sets


def _mask_known_names(text: str, token_sets: list[frozenset[str]]) -> tuple[str, int]:
    """Replace runs of consecutive words that belong to one known name (any order, partial >= 2 words)."""
    folded = _fold(text)
    words = [(m.group(), m.start(), m.end()) for m in _WORD.finditer(folded)]
    spans: list[tuple[int, int]] = []
    for tokens in token_sets:
        needed = min(2, len(tokens))
        run: list[int] = []  # indexes of words in the current run (connectors included)
        matched: set[str] = set()

        def flush(run: list[int] = run, matched: set[str] = matched, needed: int = needed) -> None:
            while run and words[run[-1]][0] in _NAME_STOPWORDS:
                run.pop()
            single_ok = needed > 1 or all(len(words[i][0]) >= _MIN_SINGLE_TOKEN for i in run)
            if run and len(matched) >= needed and single_ok:
                spans.append((words[run[0]][1], words[run[-1]][2]))
            run.clear()
            matched.clear()

        for index, (word, start, _end) in enumerate(words):
            in_name = word in tokens
            connector = word in _NAME_STOPWORDS and bool(run)
            if run and not _GAP.match(folded[words[run[-1]][2] : start]):
                flush()
                connector = False
            if in_name or connector:
                run.append(index)
                if in_name:
                    matched.add(word)
            else:
                flush()
        flush()
    return _apply_spans(text, spans, TEXT_PLACEHOLDER)


def _apply_spans(text: str, spans: list[tuple[int, int]], replacement: str) -> tuple[str, int]:
    if not spans:
        return text, 0
    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out, cursor = [], 0
    for start, end in merged:
        out.append(text[cursor:start])
        out.append(replacement)
        cursor = end
    out.append(text[cursor:])
    return "".join(out), len(merged)


def _mask_identifiers(text: str) -> tuple[str, int]:
    count = 0

    def ruc(match: re.Match[str]) -> str:
        nonlocal count
        if kind_from_ruc(match.group()) == NATURAL_PERSON:
            count += 1
            return mask_ruc(match.group())
        return match.group()

    def keyword(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group(1) + _mask_cedula(match.group(2))

    def cedula(match: re.Match[str]) -> str:
        nonlocal count
        if is_valid_cedula(match.group()):
            count += 1
            return _mask_cedula(match.group())
        return match.group()

    def dashed(match: re.Match[str]) -> str:
        nonlocal count
        if is_valid_cedula(match.group(1) + match.group(2)):
            count += 1
            return match.group(1)[:4] + "*****-" + match.group(2)
        return match.group()

    text = _RUC_IN_TEXT.sub(ruc, text)
    text = _ID_KEYWORD.sub(keyword, text)
    text = _CEDULA_IN_TEXT.sub(cedula, text)
    return _CEDULA_DASHED.sub(dashed, text), count


def _protected_spans(text: str, protected_names: Iterable[str]) -> list[tuple[int, int]]:
    folded = _fold(text)
    spans = []
    for name in protected_names:
        needle = _fold(name).strip()
        start = folded.find(needle) if needle else -1
        while start != -1:
            spans.append((start, start + len(needle)))
            start = folded.find(needle, start + len(needle))
    return spans


def _mask_honorific_runs(text: str, protected: list[tuple[int, int]]) -> tuple[str, int]:
    """Honorific + name runs, except inside a protected string (an entity name such as
    "HOSPITAL DR. GUSTAVO DOMINGUEZ Z." must stay as it is)."""
    spans = [
        m.span()
        for m in _HONORIFIC_RUN.finditer(text)
        if not any(m.start() < end and start < m.end() for start, end in protected)
    ]
    return _apply_spans(text, spans, TEXT_PLACEHOLDER)


def mask_free_text_counted(
    text: str,
    known_person_names: Iterable[str] = (),
    protected_names: Iterable[str] = (),
    *,
    honorifics: bool = True,
) -> tuple[str, int]:
    """Like `mask_free_text`, also returning how many personal items were replaced."""
    text, names = _mask_known_names(text, _name_token_sets(known_person_names))
    text, ids = _mask_identifiers(text)
    runs = 0
    if honorifics:
        text, runs = _mask_honorific_runs(text, _protected_spans(text, protected_names))
    return text, names + ids + runs


def mask_free_text(
    text: str,
    known_person_names: Iterable[str] = (),
    protected_names: Iterable[str] = (),
    *,
    honorifics: bool = True,
) -> str:
    """Mask personal data in free text (see the module docstring). Pure and idempotent.

    `protected_names` are legal-entity, public-entity and buyer names of the process: the honorific
    rule never rewrites text inside them.
    """
    return mask_free_text_counted(text, known_person_names, protected_names, honorifics=honorifics)[0]


def safe_free_text(
    text: str | None,
    known_person_names: Iterable[str] = (),
    *,
    withhold: bool = False,
    protected_names: Iterable[str] = (),
) -> tuple[str | None, bool]:
    """Return ``(text, withheld)``. The text is withheld (``None``) when `withhold` is set or when
    masking found any personal item in it: a heuristic that found one cannot vouch for the rest."""
    if withhold:
        return None, True
    if text is None:
        return None, False
    masked, replaced = mask_free_text_counted(text, known_person_names, protected_names)
    return (None, True) if replaced else (masked, False)


# ----------------------------------------------------------------------------- nested payloads


def mask_payload(
    payload: Any,
    known_person_names: Iterable[str] = (),
    protected_names: Iterable[str] = (),
    *,
    honorifics: bool = True,
) -> Any:
    """Deep-mask arbitrary JSON-like data (evidence, dossiers).

    Dicts holding a ``ruc``/``*_ruc`` key are parties: their ruc and sibling name keys are masked by
    the party rules (``buyer_*`` only for natural RUCs). The names found that way are then removed from
    every string with `mask_free_text`, together with `known_person_names` (names the caller knows
    belong to natural persons, e.g. the process's parties), which also masks RUCs, cédulas and honorific
    runs.
    """
    names: set[str] = set(known_person_names)
    protected: set[str] = set(protected_names)
    masked = _mask_parties(payload, names, protected)
    return _scrub(masked, sorted(names), sorted(protected), honorifics)


def _name_keys(ruc_key: str) -> tuple[str, ...]:
    prefix = ruc_key[: -len("ruc")]
    return _NAME_KEYS_FOR_BARE_RUC if not prefix else (f"{prefix}name",)


def _mask_parties(node: Any, names: set[str], protected: set[str]) -> Any:
    if isinstance(node, list):
        return [_mask_parties(item, names, protected) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: _mask_parties(value, names, protected) for key, value in node.items()}
    for key in node:
        if not (key == "ruc" or key.endswith("_ruc")):
            continue
        ruc = node[key] if isinstance(node[key], str) or node[key] is None else None
        kind = node.get(key[: -len("ruc")] + "kind")
        kind = kind if isinstance(kind, str) else None
        institution = key.startswith("buyer")
        for name_key in _name_keys(key):
            name = node.get(name_key)
            if not isinstance(name, str) or not name.strip():
                continue
            if institution:
                _, new_name = _mask_institution(ruc, name)
            else:
                new_name = mask_party(ruc, name, kind)[1]
            if new_name != name:
                names.add(name.strip())
                out[name_key] = new_name
            else:
                protected.add(name.strip())  # a company or public entity: never rewritten as a person
        if isinstance(ruc, str):
            new_ruc = _mask_institution(ruc, "x")[0] if institution else mask_party(ruc, "x", kind)[0]
            out[key] = new_ruc
    return out


def _scrub(node: Any, names: list[str], protected: list[str], honorifics: bool) -> Any:
    if isinstance(node, str):
        return mask_free_text(node, names, protected, honorifics=honorifics)
    if isinstance(node, list):
        return [_scrub(item, names, protected, honorifics) for item in node]
    if isinstance(node, dict):
        return {key: _scrub(value, names, protected, honorifics) for key, value in node.items()}
    return node
