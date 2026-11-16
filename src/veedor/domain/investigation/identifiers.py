"""Detection of personal identifiers (natural-person RUC, cédula) in a stored JSON document (pure).

The scan walks every scalar value AND every dictionary key. Strings are normalised first (NFKC, every
Unicode decimal digit to ASCII, zero-width and bidi characters removed) and a digit run may be written
with single separators (space, dot, dash, non-breaking space) between digits.

What counts as an identifier
    * 13 digits, third digit 0-5: natural-person RUC. Companies (third digit 9) and public entities (6)
      are allowed. When the digits were written with separators the shape must also look like a RUC
      (last three digits ``001``, or the first ten pass the cédula check), because a spaced run of
      digits is otherwise too often a date or an amount.
    * 10 digits that pass the Ecuadorian modulo-10 check (`masking.is_valid_cedula`).
    * A plain digit run longer than 13 that starts or ends with a RUC-shaped token ending in ``001``.

Deliberate exemptions (each one is tested)
    * Decimals: ``1234567890123.45`` or ``991.3200000000001`` (one dot, fraction that is not all zeros)
      are numbers. A fraction of only zeros (``...001.0``) is an integral value and is still scanned.
    * Amounts written ``1.234.567.890.123,00`` (thousands dots followed by a decimal comma).
    * Values under keys in `NON_IDENTIFIER_KEYS`: numeric bookkeeping fields that are never identifiers.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

from veedor.domain.masking import NATURAL_PERSON, is_valid_cedula, kind_from_ruc

# Keys whose values are never scanned, and why. Everything else (every other key and every value) is.
NON_IDENTIFIER_KEYS: frozenset[str] = frozenset(
    {
        "ocid",  # the process's own public identifier (it may hold long digit runs)
        "duration_ms",  # elapsed milliseconds of a tool call (a float such as 1234.5)
        "start",  # character offset of a grounded span in the rendered text
        "end",  # same, end offset
        "attempts",  # retry counter of a tool call
        "n_tool_calls",  # count of tool calls of a specialist run
        "n_checked",  # count of figures checked by the grounding verifier
        "llm_attempts",  # count of model attempts for the dossier
        "renderer_version",  # integer version of the text renderer
        "calls",  # model-call counter
        "prompt_tokens",  # token counter
        "completion_tokens",  # token counter
        "invalid_choices",  # counter of rejected model answers
        "outcomes",  # {"ok": 3, ...}: a map of counts keyed by closed vocabulary words
    }
)

_SEP = r"[\s.\-‐-―−]"
_RUN = re.compile(rf"[0-9](?:{_SEP}{{0,2}}[0-9])*")
_THOUSANDS = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{3})+$")
_ID_LENGTHS = (10, 13)
_MAX_PLAIN_RUN = 40


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    out = []
    for ch in text:
        category = unicodedata.category(ch)
        if category == "Cf" or ch in "​‌‍⁠﻿":
            continue  # zero-width, bidi marks, soft hyphen: removed so that digits become adjacent
        if category == "Nd" and not ch.isascii():
            out.append(str(unicodedata.decimal(ch)))
        else:
            out.append(ch)
    return "".join(out)


def _ruc_shaped(digits: str) -> bool:
    """13 digits, third digit 0-5."""
    return len(digits) == 13 and kind_from_ruc(digits) == NATURAL_PERSON


def _strong_ruc(digits: str) -> bool:
    return _ruc_shaped(digits) and (digits.endswith("001") or is_valid_cedula(digits[:10]))


def _identifier_in_digits(digits: str) -> bool:
    if len(digits) == 13:
        return _ruc_shaped(digits)
    return len(digits) == 10 and is_valid_cedula(digits)


def _is_decimal_number(run: str) -> bool:
    """One dot, a fraction that is not all zeros and not three digits: 1234567890123.45, 991.32000001."""
    if run.count(".") != 1 or re.search(r"[^0-9.]", run):
        return False
    _, _, fraction = run.partition(".")
    return bool(fraction.strip("0")) and len(fraction) != 3


def _run_is_identifier(run: str, following: str) -> bool:
    digits = re.sub(r"[^0-9]", "", run)
    if run == digits:  # a plain digit run
        if _identifier_in_digits(digits):
            return True
        if 13 < len(digits) <= _MAX_PLAIN_RUN:  # a RUC followed or preceded by more digits
            edges = (digits[:13], digits[-13:])
            return any(candidate.endswith("001") and _ruc_shaped(candidate) for candidate in edges)
        return False
    if _is_decimal_number(run):
        return False
    if _THOUSANDS.match(run) and re.match(r",[0-9]", following):
        return False  # 1.234.567.890.123,00 is an amount
    if len(digits) == 13 and _strong_ruc(digits):
        return True
    if len(digits) == 10 and is_valid_cedula(digits):
        return True
    # a run joined by separators may hide a plain token ("1712345678001 2024", "1712345678 -2")
    return any(
        (len(group) == 13 and _strong_ruc(group)) or (len(group) == 10 and is_valid_cedula(group))
        for group in re.findall(r"[0-9]+", run)
    )


def _text_has_identifier(text: str) -> bool:
    text = _normalise(text)
    return any(_run_is_identifier(m.group(), text[m.end() : m.end() + 2]) for m in _RUN.finditer(text))


def _number_has_identifier(value: int | float) -> bool:
    if isinstance(value, float):
        if not math.isfinite(value) or value != int(value) or abs(value) >= 10**16:
            return False  # a fractional float is an amount or an artefact, never an identifier
    number = abs(int(value))
    return _identifier_in_digits(str(number))


def _walk(node: Any) -> bool:
    if isinstance(node, bool) or node is None:
        return False
    if isinstance(node, str):
        return _text_has_identifier(node)
    if isinstance(node, int | float):
        return _number_has_identifier(node)
    if isinstance(node, dict):
        for key, value in node.items():
            if _text_has_identifier(str(key)):
                return True
            if key in NON_IDENTIFIER_KEYS:
                continue
            if _walk(value):
                return True
        return False
    if isinstance(node, list | tuple):
        return any(_walk(item) for item in node)
    return False


def document_has_personal_identifier(document: Any) -> bool:
    """True when any value or key of a parsed JSON document holds a natural-person RUC or a cédula."""
    return _walk(document)


_OCID = re.compile(r"^ocds-[a-z0-9]{3,12}-(.+)$")


def _own_identifiers(document: Any) -> list[str]:
    """The process's own public identifier (``ocds-5wno2w-MCBS-EPMR-2019-003-322368``) and its code
    (``MCBS-EPMR-2019-003-322368``): dated sequence numbers that can pass the cédula check by chance."""
    ocid = document.get("ocid") if isinstance(document, dict) else None
    match = _OCID.match(ocid) if isinstance(ocid, str) else None
    return [ocid, match.group(1)] if match else []


def _without(node: Any, own: list[str]) -> Any:
    if isinstance(node, str):
        for item in own:
            node = node.replace(item, "#")
        return node
    if isinstance(node, dict):
        return {_without(k, own): _without(v, own) for k, v in node.items()}
    if isinstance(node, list):
        return [_without(v, own) for v in node]
    return node


def text_has_personal_identifier(text: str) -> bool:
    """True when a JSON text (or, when it does not parse, the raw text) holds one. The record's own
    process identifier is not personal data and is blanked before the scan."""
    try:
        document = json.loads(text)
    except ValueError:
        return _text_has_identifier(text)
    own = _own_identifiers(document)
    return _walk(_without(document, own) if own else document)
