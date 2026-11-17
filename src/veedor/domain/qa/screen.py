# ruff: noqa: E501
"""Screening of a visitor's question (pure). The question is untrusted text.

It is never used as SQL, a path, a URL, a tool argument or a template. This module decides only:

* whether it is well formed (`validate_question`): 3 to 300 characters, one question, no control, format,
  private-use or surrogate characters, at least two letters;
* whether it asks for something Veedor never answers (`classify_question`): a judgement about conduct, data of
  a natural person, or an instruction to the system. Those get a fixed sentence, whatever the evidence says.

Nothing here keeps the text: `fingerprint` returns the only things that may be logged or stored.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from veedor.domain.dossier.text import CONFUSABLES, canonical
from veedor.domain.dossier.vocabulary import MARKUP, NON_LATIN_LETTERS
from veedor.domain.investigation.identifiers import document_has_personal_identifier
from veedor.domain.quotes.screen import has_accusation_wording

MIN_CHARS = 3
MAX_CHARS = 300
_BAD_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class Problem(StrEnum):
    """Why a question is rejected before any retrieval. Closed set: it is logged and counted."""

    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    CONTROL_CHARACTERS = "control_characters"
    NO_LETTERS = "no_letters"
    SEVERAL_QUESTIONS = "several_questions"


class Intent(StrEnum):
    """What a well-formed question is asking for."""

    ANSWERABLE = "answerable"  # goes on to retrieval
    JUDGEMENT = "judgement"  # asks whether someone did wrong, who is to blame, whether it is legal
    PERSON = "person"  # asks for a name, an identity number or a contact of a natural person
    INSTRUCTION = "instruction"  # tries to instruct the system, or carries links, markup or hidden text


@dataclass(frozen=True, slots=True)
class Screened:
    text: str  # the question, NFKC-normalised and whitespace-collapsed (never stored)
    problem: Problem | None = None

    @property
    def ok(self) -> bool:
        return self.problem is None


def validate_question(raw: str) -> Screened:
    """Well-formedness only. A rejected question is answered with a 422 that never echoes it."""
    if len(raw) > 4 * MAX_CHARS:
        return Screened("", Problem.TOO_LONG)
    if any(unicodedata.category(ch) in _BAD_CATEGORIES for ch in raw):  # includes tabs and line breaks
        return Screened("", Problem.CONTROL_CHARACTERS)
    text = " ".join(unicodedata.normalize("NFKC", raw).split())
    if any(unicodedata.category(ch) in _BAD_CATEGORIES for ch in text):
        return Screened("", Problem.CONTROL_CHARACTERS)
    if len(text) < MIN_CHARS:
        return Screened("", Problem.TOO_SHORT)
    if len(text) > MAX_CHARS:
        return Screened("", Problem.TOO_LONG)
    if sum(ch.isalpha() for ch in text) < 2:
        return Screened("", Problem.NO_LETTERS)
    if _several_questions(text):
        return Screened("", Problem.SEVERAL_QUESTIONS)
    return Screened(text)


_QUESTION_PART = re.compile(r"[^?¿]*[A-Za-zÁÉÍÓÚÑáéíóúñ0-9][^?¿]*\?+")


def _several_questions(text: str) -> bool:
    """More than one sentence ending in a question mark with words in it."""
    return len(_QUESTION_PART.findall(text)) > 1


# --- what is never answered -----------------------------------------------------------------------

_JUDGEMENT = re.compile(
    r"\b(?:quien\w* (?:es|son|fue|fueron|sera|seran) (?:el |la |los |las )?(?:responsable|culpable)\w*"
    r"|(?:es|son|fue|fueron|esta|estan|hay|hubo|existe|existio) (?:algo |alguna |algun )?"
    r"(?:legal|ilegal|licito|ilicito|legitim\w*|honest\w*|limpi\w*|transparent\w*|raro\w*(?! que\b)|extran\w*|"
    r"inocente\w*|confiable\w*|seguro\w*|bueno\w*|malo\w*|correct\w*|incorrect\w*|valid\w*|dudos\w*)"
    r"|(?:actuo|actuaron|obro|obraron|hizo|hicieron) (?:mal|bien|correctamente|incorrectamente)"
    r"|(?:debe|deben|deberia|deberian|hay que|habria que) (?:ser )?(?:sancion\w*|investigar\w*|denunci\w*|"
    r"castig\w*|procesar\w*|auditar\w*|cancelar\w*|anular\w*)"
    r"|(?:es|esta|fue|son) (?:un )?(?:negocio|contrato|proceso|licitacion|compra|adjudicacion) "
    r"(?:turbio|sucio|dudoso|raro|limpio|legal|ilegal|trucado\w*|amanado\w*)"
    r"|a quien (?:favorec\w*|beneficia\w*|perjudic\w*|conviene)"
    r"|(?:hay|hubo|existe|existio|existen|existieron) (?:alguna? )?(?:irregularidad\w*|anomalia\w*|"
    r"problema\w*|falta\w*|violacion\w*|infraccion\w*|incumplimiento\w*)"
    r"|(?:cometio|cometieron|incumplio|incumplieron|violo|violaron|infringio|infringieron)\b"
    r"|quien (?:gano|se llevo|se quedo con) (?:de manera|de forma) \w+"
    r"|(?:me )?(?:recomiendas|recomienda|aconsejas|aconseja) (?:denunci\w*|investigar\w*|sancion\w*)"
    r"|(?:contrato|proceso|licitacion|compra|adjudicacion|concurso)s? (?:esta |fue |era |es )?(?:dirigid|arreglad|cuadrad|armad|trucad)\w*"
    r"|(?:favoritism|nepotism|dedazo)\w*|a dedo|entre (?:amigos|panas|familiares|compadres)"
    r"|(?:se )?aprovech\w* (?:del|de la|de los)|se (?:la )?(?:repartier|reparten|repartio)\w*)\b"
)
_PERSON = re.compile(
    r"\b(?:cedula\w*|pasaporte\w*|telefono\w*|celular\w*|whatsapp|correo\w*|e ?mail|direccion (?:de |del |"
    r"particular|domiciliaria)\w*|domicilio\w*|casa de|(?<!de que )vive\w*|(?:nombre|nombres|apellido\w*|identidad|datos) "
    r"(?!(?:de|del) (?:la |el )?(?:empresa|compania|firma|proveedor|ganador|ganadora|adjudicatari\w*|entidad|"
    r"institucion|contratista|comprador)\b|de la (?:empresa|compania|firma|entidad|institucion)\b)"
    r"(?:de|del|de la|completo|personales)\b|"
    r"(?:representante legal|accionista\w*|socio\w*|duen[oa]\w*|propietari\w*|gerente\w*|administrador\w*|"
    r"director\w*|funcionari\w*|servidor\w* public\w*|alcalde\w*|ministr\w*|prefect\w*|concejal\w*|"
    r"presidente\w*|directivo\w*|secretari\w*|tecnic\w*|ingenier\w*|abogad\w*|contador\w*|firmante\w*|apoderad\w*|"
    r"delegad\w*|supervisor\w*|fiscalizador\w*|evaluador\w*|miembro\w* de la comision|"
    r"hijo\w*|espos[oa]\w*|famili\w*|parent\w*|pariente\w*|conyuge\w*|hermano\w*|primo\w*|cunad\w*|"
    r"persona natural|personas naturales)\b|"
    r"quien (?:firmo|aprobo|autorizo|elaboro|evaluo|califico|adjudico|calific\w*|redacto|reviso|dirigio|decidio)|"
    r"como se llama\w*(?! (?:la |el )?(?:empresa|compania|firma|proveedor|ganador|ganadora|adjudicatari\w*|entidad|"
    r"institucion|contratista|comprador)\b)|cual es el nombre(?! (?:de|del) (?:la |el )?(?:empresa|compania|firma|proveedor|ganador|ganadora|"
    r"adjudicatari\w*|entidad|institucion|contratista|comprador)\b)|(?:dime|dame|indica|indicame|muestra|muestrame|revela|revelame) "
    r"(?:el |los |su )?(?:nombre|nombres|datos)\b(?! (?:de|del) (?:la |el )?(?:empresa|compania|firma|proveedor|ganador|"
    r"ganadora|adjudicatari\w*|entidad|institucion|contratista|comprador)\b))"
)
_INSTRUCTION = re.compile(
    r"\b(?:sin (?:restricciones|limites|filtros|reglas|censura)|(?:hidden|secret|reglas ocultas|reglas internas)\b|"
    r"(?:que )?(?:tengas|tienes|posees|conoces) (?:guardad\w*|almacenad\w*)|ignor\w*|ignore|olvid\w*|forget|disregard|desobedec\w*|bypass|override|jailbreak|instrucciones|"
    r"instructions|prompt|developer mode|modo (?:desarrollador|dios|libre)|"
    r"(?:tus|your|sus) (?:reglas|directrices|rules|guidelines|configuracion|restricciones)|"
    r"(?:actua|finge|fingir|pretend\w*|simula|hazte|comportate|roleplay|role play|act) (?:como|que|as|like)|"
    r"imagina que (?:eres|tu|you)|(?:eres|you are|ahora eres|from now on|a partir de ahora|"
    r"de ahora en adelante)|"
    r"(?:escribe|redacta|compon\w*|inventa|write|compose) (?:\w+ ){0,3}(?:poema|cuento|cancion|historia|ensayo|carta|rima|poem|story|song)\w*|"
    r"(?:responde|contesta|answer|reply|respond|escribe|write|repite|repeat|imprime|print|traduce|translate|"
    r"output|say|di|resume|summari[sz]e|devuelve|return|muestra|show) (?:\w+ ){0,5}(?:solo|unicamente|only|"
    r"exactamente|exactly|literalmente|verbatim|palabra por palabra|con la palabra|"
    r"en (?:ingles|english|json|markdown|html|base64|mayusculas)|in (?:english|json|markdown|html|base64)))\b"
)
_LINK = re.compile(r"\bhttps?\b|\bftp\b|\bwww\b|\bmailto\b|\b[\w-]+ (?:punto|dot) (?:com|net|org|ec)\b|\b[\w-]+\.(?:com|net|org|ec|io)\b")
_PAYLOAD_SYMBOLS = re.compile(
    r"[<>{}\[\]\\`|]|\.\./|--|;\s*(?:drop|select|insert|delete|update)\b|\$\(|%(?:2[0-9a-f]|3[0-9a-f]|5[c-f]|7[b-f])",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z?¿]+", " ", canonical(text)).split())


def classify_question(text: str) -> Intent:
    """Order matters: instructions and hidden payloads first (they may carry any other wording), then
    judgements, then requests about persons."""
    folded = _fold(text)
    if _INSTRUCTION.search(folded) or _carries_payload(text):
        return Intent.INSTRUCTION
    if _is_judgement(text, folded):
        return Intent.JUDGEMENT
    if _PERSON.search(folded) or document_has_personal_identifier(text):
        return Intent.PERSON
    return Intent.ANSWERABLE


def _carries_payload(text: str) -> bool:
    """Links, markup, look-alike alphabets and symbols that only a payload needs."""
    folded = canonical(text)
    unmasked = text.translate(CONFUSABLES)  # a look-alike letter is an evasion of a word, handled as such
    return bool(
        _LINK.search(folded) or MARKUP.search(text) or NON_LATIN_LETTERS.search(unmasked) or _PAYLOAD_SYMBOLS.search(text)
    )


def _is_judgement(text: str, folded: str) -> bool:
    return bool(
        _JUDGEMENT.search(folded)
        or has_accusation_wording(text)
    )


# --- what may be logged or stored --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """The only trace of a question that may be logged or stored: a salted hash and its length."""

    digest: str  # 16 hex characters of SHA-256(salt + normalised question)
    length: int


def normalise_for_key(text: str) -> str:
    """Accent, case and punctuation insensitive key (an informal spelling hits the same cache entry)."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", canonical(text)).split())


def fingerprint(text: str, salt: bytes) -> Fingerprint:
    digest = hashlib.sha256(salt + normalise_for_key(text).encode("utf-8")).hexdigest()[:16]
    return Fingerprint(digest, len(text))
