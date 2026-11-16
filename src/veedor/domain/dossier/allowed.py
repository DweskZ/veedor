"""Collect the values a generated text may mention, from a dumped EvidencePack (pure).

The walk is generic so every field of the pack, including signal evidence, is covered:

* numbers (int/float) -> `numbers`; keys ending in ``_ratio``/``_share`` and any float in (0, 1]
  also -> `ratios` (shown as a percentage, 100 x value)
* ISO dates -> `dates` (their year also -> `numbers`)
* 13-digit RUCs -> `rucs`; masked RUCs (4 digits + 9 asterisks) -> `masked_rucs`
* process codes (hyphenated with a digit) and long digit-only codes (CPC) -> `codes`
* free text fields (CPC description, activity, CIIU code and every string inside
  signal evidence) -> `quotable`: they may only be reproduced verbatim inside « » quotes, so text
  injected in the source data can never become a free-standing claim
* any other string (names, regions, labels, statuses) -> `names`
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from veedor.domain.dossier.bindings import Binding, NounBinding, RoleBinding
from veedor.domain.dossier.text import norm, pad
from veedor.domain.dossier.vocabulary import STATIC_NUMBERS, STATIC_TERMS

ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
RUC = re.compile(r"^\d{13}$")
MASKED_RUC = re.compile(r"^\d{4}\*{9}$")
_SEG = r"(?:[A-Za-z0-9]|\.(?=[A-Za-z0-9-]))+"
CODE = re.compile(rf"^(?=.*\d)[A-Za-z]{_SEG}(?:-{_SEG}){{2,}}$")
CODE_IN_TEXT = re.compile(rf"(?<![\w-])[A-Za-z]{_SEG}(?:-{_SEG}){{2,}}(?![\w-])")
LONG_DIGITS = re.compile(r"^\d{8,}$")
DIGIT_GROUPS = re.compile(r"\d+(?:[.,]\d+)*")
QUOTABLE_KEYS = frozenset({"main_cpc_description", "activity", "ciiu_code", "title"})
RATIO_SUFFIXES = ("_ratio", "_share")


@dataclass
class AllowedValues:
    numbers: list[Decimal] = field(default_factory=list)
    ratios: list[Decimal] = field(default_factory=list)
    dates: set[date] = field(default_factory=set)
    year_months: set[tuple[int, int]] = field(default_factory=set)
    rucs: set[str] = field(default_factory=set)
    masked_rucs: set[str] = field(default_factory=set)
    codes: set[str] = field(default_factory=set)
    names: list[str] = field(default_factory=list)
    quotable: list[str] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    nouns: list[NounBinding] = field(default_factory=list)
    roles: list[RoleBinding] = field(default_factory=list)
    names_exact: list[str] = field(default_factory=list)  # raw pack names, bypass spans
    claims: dict[str, Any] = field(default_factory=dict)


def _decimal(value: int | float) -> Decimal | None:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return Decimal(str(value))


def _add_date(out: AllowedValues, text: str) -> bool:
    match = ISO_DATE.match(text)
    if not match:
        return False
    year, month, day = (int(g) for g in match.groups())
    try:
        out.dates.add(date(year, month, day))
    except ValueError:
        return False
    out.year_months.add((year, month))
    out.numbers.append(Decimal(year))
    return True


def _add_string(out: AllowedValues, key: str, text: str, in_evidence: bool) -> None:
    text = text.strip()
    if not text:
        return
    if _add_date(out, text):
        return
    if RUC.match(text):
        out.rucs.add(text)
    elif MASKED_RUC.match(text):
        out.masked_rucs.add(text)
    elif CODE.match(text) or LONG_DIGITS.match(text):
        out.codes.add(text.casefold())
    elif key in QUOTABLE_KEYS or in_evidence:
        out.quotable.append(pad(norm(text)))
    else:
        out.names.append(pad(norm(text)))
        if len(text) >= 4:
            out.names_exact.append(text)
        out.codes.update(
            m.group().casefold() for m in CODE_IN_TEXT.finditer(text) if any(c.isdigit() for c in m.group())
        )
        for group in DIGIT_GROUPS.findall(text):
            if group.isdigit():
                out.numbers.append(Decimal(group))


def _walk(out: AllowedValues, node: Any, key: str, in_evidence: bool) -> None:
    if isinstance(node, dict):
        for child_key, child in node.items():
            _walk(out, child, str(child_key), in_evidence or child_key == "evidence")
    elif isinstance(node, list | tuple):
        for child in node:
            _walk(out, child, key, in_evidence)
    elif isinstance(node, bool) or node is None:
        return
    elif isinstance(node, int | float):
        value = _decimal(node)
        if value is None:
            return
        out.numbers.append(value)
        if key.endswith(RATIO_SUFFIXES) or (isinstance(node, float) and 0 < node <= 1):
            out.ratios.append(value)
    elif isinstance(node, str):
        _add_string(out, key, node, in_evidence)


def collect_allowed(dumped_pack: dict[str, Any]) -> AllowedValues:
    out = AllowedValues()
    _walk(out, dumped_pack, "", False)
    out.numbers.extend(Decimal(n) for n in STATIC_NUMBERS)
    out.names.extend(pad(norm(term)) for term in STATIC_TERMS)
    return out
