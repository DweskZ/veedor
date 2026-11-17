"""Content rules of the release gate for the quotes mart (pure).

`scripts/check_quotes_privacy.py` refuses a data bundle when any stored quote matches one of these rules.
The first seven are the regular expressions of the fifth independent review (reconstructed from its sweep
scripts: titles followed by names, role words followed by names, honorifics followed by a capitalised word,
sign-off and first-person cues, vehicle plates, telephone numbers, identity-document words). The others are
this project's own: glued honorifics, partial mobile numbers, e-mail, valid cédulas, natural-person RUCs,
long numbers, health references, accusation stems. A rule that matches is a failure, not a warning.

The rules are deliberately broader than the screen of `domain.quotes.strict`: the screen decides what is
eligible, the gate proves that nothing it was meant to remove is still in the mart.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from veedor.domain.investigation.identifiers import document_has_personal_identifier
from veedor.domain.quotes.allegation import has_allegation_wording

_STOP = frozenset(
    "oferente oferentes alcalde alcaldesa presidente presidenta ministro ministra civil mecanico mecánico "
    "electrico eléctrico electricista electronico electrónico industrial sistemas naval biomedico biomédico "
    "comercial quimico químico ambiental agronomo agrónomo jefe director directora gerente proveedor "
    "proveedores delegado delegada administrador administradora contratista subsecretario secretario "
    "secretaria entidad entidades contratante fiscalizador fiscalizadora residente de del la el los las en "
    "civiles mecatrónico mecatronico geólogo geologo forestal telecomunicaciones electrónica electrica "
    "eléctrica hidraulico hidráulico sanitario sanitaria obra supervisor técnico tecnico tecnica técnica "
    "general especialista responsable coordinador coordinadora analista asesor asesora prefecto prefecta "
    "concejal juez fiscal comisaria comisario rector rectora decano decana medico médico medica médica "
    "odontologo odontólogo veterinario enfermero enfermera titular nacional".split()
)
_TITLE_WORDS = (
    r"(?:ingeniero|ingeniera|ing|doctor|doctora|dr|dra|licenciado|licenciada|lic|licda|abogado|abogada|abg|"
    r"economista|econ|arquitecto|arquitecta|arq|tecn[oó]logo|tnlgo|magister|mgs|mag|msc|phd|ph\.d|"
    r"se[ñn]or|se[ñn]ora|se[ñn]orita|sr|sra|srta|coronel|crnl|capit[aá]n|cpnv|mayor|general|sargento|ec|eco|"
    r"psic|psic[oó]logo|psic[oó]loga|odont[oó]logo|dr\.|prof|profesor|profesora|master|m\.sc)"
)
_TITLE_NAME = re.compile(
    r"\b(?i:" + _TITLE_WORDS + r")\b\.?\s*[:\-]?\s*((?:[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\.]+\s*){2,4})"
)
_ROLE_NAME = re.compile(
    r"\b(?:representad[oa]s?|suscrit[oa]s?|firmad[oa]s?|elaborad[oa]s?|a cargo de|presentad[oa]s? por|"
    r"designad[oa]s? (?:a|al|como|por)|gerente|director[a]?|administrador[a]?|delegad[oa]|apoderad[oa]|"
    r"procurador[a]?)\b[^.]{0,40}?((?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+){2,3}[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)"
)
_HONORIFIC = re.compile(
    r"\b(?i:ing|econ|mgs|mg|abg|dr|dra|lic|licda|arq|tnlgo|tlgo|crnl|cpnv|cap|tcrn|sr|sra|srta|msc|phd|ph\.d|cpa|"
    r"eco|ab|dip|psic|mtr|mba|gral|sgos|sgop|tnte|cbos|sargento|coronel|capitan|ingeniero|ingeniera|doctor|"
    r"doctora|licenciado|licenciada|abogado|abogada|economista|arquitecto|arquitecta|se[ñn]or|se[ñn]ora|"
    r"se[ñn]orita|tecn[oó]logo)\b\.?\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+",
    re.UNICODE,
)
_SIGN = re.compile(
    r"(atentamente|cordialmente|saludos|saludos cordiales|firma|firmado|suscrito|suscrita|"
    r"representante legal|"
    r"administrador(a)? del contrato|delegad[oa]|gerente general|apoderad[oa]|\byo,)\b",
    re.IGNORECASE,
)
_PLATE = re.compile(r"\b[A-Z]{3}[\s\-]?\d{3,4}\b")
_PHONE = re.compile(
    r"(?:\+?\s?593[\s\-.]?|\b0)\s?[2-9][\s\-.]?\d{3}[\s\-.]?\d{3,4}\b|\b09\d[\s\-.]?\d{3}[\s\-.]?\d{3}\b"
)
_ID_WORD = re.compile(
    r"\b(licencia|registro\s+senescyt|senescyt|cj\b|c\.i\.|c\.c\.|c[eé]dula|ci:|matr[ií]cula|"
    r"cuenta\s+(corriente|de ahorros?)|cta\.?|pasaporte|placa|credencial)\b[^.;\n]{0,30}?"
    r"\b[A-Za-z\-]*\d[A-Za-z0-9\-]{3,}",
    re.IGNORECASE,
)


def _title_name(text: str) -> bool:
    for match in _TITLE_NAME.finditer(text):
        tokens = [t.lower().strip(".") for t in match.group(1).split() if t.strip(".")]
        if len(tokens) < 2:
            continue
        if sum(1 for t in tokens if t in _STOP) >= 1 and len([t for t in tokens if t not in _STOP]) < 2:
            continue
        return True
    return False


# --- this project's own rules ---
def _long_number(text: str) -> bool:
    for match in _LONG_NUMBER.finditer(text):
        digits = match.group()
        if len(digits) == 13 and digits[2] in "69" and digits.endswith("001"):
            continue  # company or public-entity RUC
        if digits[0] != "0" and _AMOUNT_CONTEXT.search(text[max(0, match.start() - 20) : match.start()]):
            continue
        return True
    return False


_GLUED_HONORIFIC = re.compile(
    r"\b(?i:sr|sra|srta|ing|dr|dra|lic|abg|econ|arq)\b\.?(?=[A-ZÁÉÍÓÚÑ]{2})|"
    r"\b(?:Sr|Sra|Srta|Ing|Dr|Dra|Lic|Abg|Econ|Arq|sr|sra|srta|ing|dr|dra|lic|abg|econ|arq)(?=[A-ZÁÉÍÓÚÑ]{2})"
)
_MOBILE_PARTIAL = re.compile(r"(?<![\d.,])09\d{2,}")
_EMAIL = re.compile(
    r"[\w.+\-]+\s?(?:@|\(at\)|\[at\]|\barroba\b)\s?[\w\-]+|\b(?:gmail|hotmail|yahoo|outlook)\b", re.I
)
_LONG_NUMBER = re.compile(
    r"(?<![\d.,])\d{10,}(?![\d])"
)  # 10 or more digits in a row: a cédula, a phone, a RUC
_AMOUNT_CONTEXT = re.compile(r"(?:\$|usd|us\$|valor|monto|total|precio|presupuesto)\W{0,3}$", re.IGNORECASE)
_HEALTH = re.compile(r"\bpacientes?\b|\bhistorias?\s+cl[ií]nicas?\b", re.IGNORECASE)
_PLATE_LOWER = re.compile(r"(?<![A-Za-z0-9])[a-z]{3}-\d{3,4}(?![A-Za-z0-9])")


def _natural_ruc(text: str) -> bool:
    for match in re.finditer(r"(?<!\d)(?:\d[\s.\-]?){12}\d(?!\d)", text):
        digits = re.sub(r"\D", "", match.group())
        if digits.endswith("001") and digits[2] in "012345":
            return True
    return False


REVIEWER_RULES: dict[str, Callable[[str], bool]] = {
    "r1_title_then_name": _title_name,
    "r2_role_then_name": lambda t: bool(_ROLE_NAME.search(t)),
    "r3_honorific_then_capitalised": lambda t: bool(_HONORIFIC.search(t)),
    "r4_sign_off_or_first_person": lambda t: bool(_SIGN.search(t)),
    "r5_vehicle_plate": lambda t: bool(_PLATE.search(t)),
    "r6_telephone": lambda t: bool(_PHONE.search(t)),
    "r7_identity_document_word": lambda t: bool(_ID_WORD.search(t)),
}
OWN_RULES: dict[str, Callable[[str], bool]] = {
    "o1_glued_honorific": lambda t: bool(_GLUED_HONORIFIC.search(t)),
    "o2_partial_mobile": lambda t: bool(_MOBILE_PARTIAL.search(t)),
    "o3_email": lambda t: bool(_EMAIL.search(t)),
    "o4_identifier": document_has_personal_identifier,
    "o5_natural_ruc": _natural_ruc,
    "o6_long_number": _long_number,
    "o7_health": lambda t: bool(_HEALTH.search(t)),
    "o8_lowercase_plate": lambda t: bool(_PLATE_LOWER.search(t)),
    "o9_accusation_stem": has_allegation_wording,
}
ALL_RULES = REVIEWER_RULES | OWN_RULES


def rules_hit(text: str) -> list[str]:
    """Names of every gate rule that matches `text` (empty: clean)."""
    return [name for name, rule in ALL_RULES.items() if rule(text)]
