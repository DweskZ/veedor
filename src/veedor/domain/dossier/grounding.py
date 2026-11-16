"""Grounding verifier: every checkable token of a text must be supported by the EvidencePack.

`verify(text, pack)` is a pure function. Checks, in this order (each matched span is blanked
out so later checks do not see it again, and offsets always refer to the original text):

1. **Quotes** ``«...»``: accepted only when the inner text is a verbatim substring (accent, case
   and punctuation insensitive) of a free-text field of the pack. Tokens inside are not checked
   separately, and forbidden wording inside a verbatim quote is not flagged (it is source data).
2. **Forbidden wording** (`FORBIDDEN_PATTERN`) on the remaining text.
3. **RUCs**: 13 digits must be a RUC of the pack; ``dddd*********`` must be a masked RUC of the pack.
4. **Codes**: hyphenated process codes with a digit, and digit-only codes of 10+ digits (CPC).
5. **Dates**: ISO (``2023-08-25``), ``dd/mm/yyyy``, Spanish long (``25 de agosto de 2023``) and
   month-year (``agosto de 2023``). Must be a valid date present in the pack (month-year: a pack
   date in that month).
6. **Numbers and percentages** (see `_number_candidates` and `_matches`).
7. **Proper names**: spans of capitalised words (``de/del/la/las/los`` may join them) must be a
   word-aligned part of a name in the pack or of a fixed term. A lone capitalised word that opens a
   sentence is ignored only if it is in `SENTENCE_STARTERS`.

Number normalisation. Both ``1.234,56`` and ``1,234.56`` are read; the last separator is the
decimal mark when both appear, a single separator followed by exactly three digits is ambiguous
(``1.234`` = 1234 or 1.234) and both readings are tried, repeated separators are thousands marks.
A reading ``v`` with ``d`` displayed decimals is supported by a pack value ``a`` when ``v == a`` or
when ``v`` is ``a`` rounded half-up to ``d`` decimals, only if ``d`` is smaller than the decimals
of ``a`` and at least ``_min_decimals(a)`` (0 for |a| >= 100, 1 for |a| >= 10, otherwise 2), so
amounts may be shown to the unit but small ratios may not be rounded away. A ``%`` token is
compared with the pack numbers and with 100 x every pack ratio (derived values must be added to
the pack by the reader). Limits: the check is membership, not meaning: two pack numbers swapped
in a sentence still pass, and capitalised names are the only names detected (an invented name
written in lowercase is not).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from veedor.domain.dossier.allowed import AllowedValues
from veedor.domain.dossier.bindings import CONTINUATIONS
from veedor.domain.dossier.models import EvidencePack, GroundedToken, GroundingReport
from veedor.domain.dossier.safety import is_unsafe_text
from veedor.domain.dossier.text import canonical, fold_chars, norm, pad
from veedor.domain.dossier.vocabulary import (
    FORBIDDEN_PATTERN,
    FUNCTION_WORDS,
    HIDDEN_CHARS,
    INFERENCE_PATTERN,
    MARKUP,
    MONTHS_ES,
    NON_LATIN_LETTERS,
    NUMBER_WORDS,
    SENTENCE_STARTERS,
)

_CHAR_RULES = (
    (HIDDEN_CHARS, "hidden character"),
    (NON_LATIN_LETTERS, "look-alike or non-Latin letter"),
    (MARKUP, "markup or link syntax"),
)
_QUOTE = re.compile(r"«([^»]*)»")
_RUC = re.compile(r"(?<![\w*-])\d{13}(?![\w-])")
_MASKED_RUC = re.compile(r"(?<![\w*-])\d{4}\*{9}(?![\w-])")
_SEG = r"(?:[A-Za-z0-9]|\.(?=[A-Za-z0-9-]))+"
_CODE = re.compile(rf"(?<![\w-])[A-Za-z]{_SEG}(?:-{_SEG}){{2,}}(?![\w-])")
_LONG_DIGITS = re.compile(r"(?<![\w.,])\d{8,}(?![.,]?\w)")
_MONTHS = "|".join(MONTHS_ES)
_ISO = re.compile(
    r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?!\d)"
)
_SLASH = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")
_LONG = re.compile(rf"(?<!\d)(\d{{1,2}})\s+de\s+({_MONTHS})\s+de\s+(\d{{4}})(?!\d)", re.IGNORECASE)
_MONTH_YEAR = re.compile(rf"(?<!\w)({_MONTHS})\s+de\s+(\d{{4}})(?!\d)", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)*)(?!\w)(\s?%)?")
_CAP = r"(?:[A-ZÁÉÍÓÚÑÜ]|\d+(?=[A-ZÁÉÍÓÚÑÜ]))[\wÁÉÍÓÚÑÜáéíóúñü&']*(?:\.[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü&']*)*"
_NAME_SPAN = re.compile(rf"{_CAP}(?:\s+(?:(?:de|del|la|las|los)\s+|\d+(?:[.,]\d+)*\s+)*{_CAP})*")
_NUMBER_WORD = re.compile(r"\b(?:" + "|".join(NUMBER_WORDS) + r")\b")
_CONNECTORS = frozenset({"de", "del", "la", "las", "los"})
_LABEL_TOKEN = re.compile(r"\b(?:USD|RUC|CPC|CIIU)\b")
_SENTENCE_START = re.compile(r"(?:^|[.!?:;\n])\s*(?:[-•*]\s*)?$")


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _min_decimals(allowed: Decimal, percent: bool = False) -> int:
    magnitude = abs(allowed)
    if percent:  # a percentage may be shown with one decimal even below 10 %
        return 0 if magnitude >= 100 else 1
    if magnitude >= 100:
        return 0
    return 1 if magnitude >= 10 else 2


def _decimals(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _matches(
    allowed: list[Decimal], value: Decimal, shown_decimals: int, *, percent: bool = False
) -> Decimal | None:
    for raw in allowed:
        candidate = abs(raw)  # a minus sign in the text is not read, so compare magnitudes
        if value == candidate:
            return candidate
        floor = _min_decimals(candidate, percent)
        if shown_decimals < _decimals(candidate) and shown_decimals >= floor:
            quantum = Decimal(1).scaleb(-shown_decimals)
            try:
                if candidate.quantize(quantum, rounding=ROUND_HALF_UP) == value.quantize(quantum):
                    return candidate
            except InvalidOperation:
                continue
    return None


def _number_candidates(token: str) -> list[tuple[Decimal, int]]:
    """Possible readings (value, displayed decimals) of a numeric token; empty if malformed."""
    dots, commas = token.count("."), token.count(",")
    if dots == 0 and commas == 0:
        return [(Decimal(token), 0)]
    if dots and commas:
        decimal_mark = "." if token.rfind(".") > token.rfind(",") else ","
        thousands_mark = "," if decimal_mark == "." else "."
        integer, _, fraction = token.rpartition(decimal_mark)
        groups = integer.split(thousands_mark)
        if thousands_mark == decimal_mark or token.count(decimal_mark) != 1:
            return []
        if not _valid_groups(groups):
            return []
        return [(Decimal("".join(groups) + "." + fraction), len(fraction))]
    mark = "." if dots else ","
    parts = token.split(mark)
    if len(parts) > 2:
        return [(Decimal("".join(parts)), 0)] if _valid_groups(parts) else []
    integer, fraction = parts
    readings = [(Decimal(f"{integer}.{fraction}"), len(fraction))]
    if len(fraction) == 3 and 1 <= len(integer) <= 3 and not integer.startswith("0"):
        readings.append((Decimal(integer + fraction), 0))
    return readings


def _valid_groups(groups: list[str]) -> bool:
    return bool(groups[0]) and 1 <= len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:])


def _short(value: Decimal) -> str:
    """The matched pack value for the report: at most 4 decimals, so float artifacts never leak in."""
    try:
        return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize(), "f")
    except InvalidOperation:
        return str(value)[:24]


def _token(kind, text, span, matched=None, reason=None) -> GroundedToken:  # noqa: ANN001
    return GroundedToken(kind=kind, text=text, start=span[0], end=span[1], matched=matched, reason=reason)


class _Run:
    def __init__(self, text: str, allowed: AllowedValues) -> None:
        self.original = text
        self.work = text
        self.allowed = allowed
        self.supported: list[GroundedToken] = []
        self.unsupported: list[GroundedToken] = []
        self.forbidden: list[GroundedToken] = []

    def record(self, ok: bool, token: GroundedToken) -> None:
        (self.supported if ok else self.unsupported).append(token)

    # 1 ---------------------------------------------------------------------------------------
    def quotes(self) -> None:
        for match in list(_QUOTE.finditer(self.work)):
            raw = match.group(1)
            inner = norm(raw)
            if not inner:  # punctuation only, e.g. «-»: nothing to ground
                self.work = _blank(self.work, *match.span())
                continue
            verbatim = any(pad(inner) in field for field in self.allowed.quotable + self.allowed.names)
            ok = verbatim or _is_grounded_value(raw, self.allowed)
            reason = None if ok else "quoted text is not a verbatim excerpt of the evidence"
            if ok and is_unsafe_text(raw):
                ok, reason = False, "quoted text contains links or instruction-like wording"
            self.record(ok, _token("quote", match.group(0), match.span(), reason=reason))
            self.work = _blank(self.work, *match.span())

    # 1b: exact pack names ------------------------------------------------------------------
    def bypass_names(self) -> None:
        """Entity and place names that equal a pack value verbatim are verified spans.

        They bypass the forbidden-word, number and name checks, but only for the exact span; the role
        they fill (supplier vs entity) is checked, and the surrounding prose is still verified.
        """
        for name in sorted(set(self.allowed.names_exact), key=len, reverse=True):
            pattern = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
            for match in list(pattern.finditer(self.work)):
                reason = self._wrong_role(match.start(), name)
                self.record(
                    reason is None,
                    _token("name", match.group(), match.span(), name if reason is None else None, reason),
                )
                self.work = _blank(self.work, *match.span())

    def _wrong_role(self, start: int, name: str) -> str | None:
        prefix = fold_chars(self.original[:start])
        for role in self.allowed.roles:
            if role.pattern.search(prefix):
                if fold_chars(name) in role.names:
                    return None
                return f"name does not fill the role «{role.role}»"
        return None

    def roles(self) -> None:
        """After a strong role label (`Proveedor adjudicado:`) only a pack name may follow."""
        folded = fold_chars(self.original)
        for role in self.allowed.roles:
            for match in role.strong.finditer(folded):
                if any(folded.startswith(n, match.end()) for n in role.names) or any(
                    folded.startswith(c, match.end()) for c in CONTINUATIONS
                ):
                    continue
                span = (match.start(), min(len(self.original), match.end() + 40))
                self.unsupported.append(
                    _token("name", self.original[span[0] : span[1]], span,
                           reason=f"value after the «{role.role}» label is not a known name")
                )  # fmt: skip

    # 2 ---------------------------------------------------------------------------------------
    def forbidden_wording(self) -> None:
        """Wording that asserts wrongdoing or concludes; hidden, look-alike and markup characters."""
        for pattern, reason in _CHAR_RULES:
            for match in pattern.finditer(self.work):
                span = match.span()
                self.forbidden.append(
                    _token("forbidden", self.original[span[0] : span[1]], span, reason=reason)
                )
        canon = canonical(self.work)
        for pattern, reason in (
            (FORBIDDEN_PATTERN, "forbidden wording"),
            (INFERENCE_PATTERN, "inference or intensifier wording"),
        ):
            for match in pattern.finditer(canon):
                span = match.span()
                self.forbidden.append(_token("forbidden", canon[span[0] : span[1]], span, reason=reason))

    def claims(self) -> None:
        """A few factual claims that are checked against the pack, not only by their figures."""
        text = canonical(self.work)
        single = self.allowed.claims.get("single_bidder")
        for match in re.finditer(r"un solo oferente", text):
            context = text[max(0, match.start() - 40) : match.start()]
            if re.search(r"procesos con\s*$", context):
                continue
            negated = bool(re.search(r"\b(?:no|ni|sin|nunca|tampoco)\b[^.;:\n]*$", context))
            if (negated and single) or (not negated and not single):
                self.unsupported.append(
                    _token("name", match.group(), match.span(), reason="claim contradicts the evidence")
                )
        n_risk = self.allowed.claims.get("n_risk_signals")
        for match in re.finditer(r"no se detectaron senales", text):
            if n_risk:
                self.unsupported.append(
                    _token("name", match.group(), match.span(), reason="claim contradicts the evidence")
                )
        previous = self.allowed.claims.get("n_previous_awards")
        for match in re.finditer(r"sin adjudicaciones previas", text):
            if previous:
                self.unsupported.append(
                    _token("name", match.group(), match.span(), reason="claim contradicts the evidence")
                )

    # 3-4 -------------------------------------------------------------------------------------
    def identifiers(self) -> None:
        for match in list(_RUC.finditer(self.work)):
            ok = match.group() in self.allowed.rucs
            self.record(
                ok,
                _token(
                    "ruc",
                    match.group(),
                    match.span(),
                    match.group() if ok else None,
                    None if ok else "RUC not in evidence",
                ),
            )
            self.work = _blank(self.work, *match.span())
        for match in list(_MASKED_RUC.finditer(self.work)):
            ok = match.group() in self.allowed.masked_rucs
            self.record(
                ok,
                _token(
                    "ruc",
                    match.group(),
                    match.span(),
                    match.group() if ok else None,
                    None if ok else "masked RUC not in evidence",
                ),
            )
            self.work = _blank(self.work, *match.span())
        for match in list(_CODE.finditer(self.work)):
            if not any(ch.isdigit() for ch in match.group()):
                continue
            ok = match.group().casefold() in self.allowed.codes
            self.record(
                ok,
                _token(
                    "code",
                    match.group(),
                    match.span(),
                    match.group() if ok else None,
                    None if ok else "code not in evidence",
                ),
            )
            self.work = _blank(self.work, *match.span())
        for match in list(_LONG_DIGITS.finditer(self.work)):
            if match.group() in self.allowed.codes:  # otherwise checked as a plain number
                self.record(True, _token("code", match.group(), match.span(), match.group()))
                self.work = _blank(self.work, *match.span())

    def _wrong_noun(self, end: int, readings: list[tuple]) -> str | None:
        """A count right before a noun (`2023 oferentes`) must be a pack value for that noun."""
        after = fold_chars(self.original[end : end + 24])
        for binding in self.allowed.nouns:
            if binding.pattern.match(after):
                ok = any(_matches(list(binding.values), v, d) is not None for v, d in readings)
                return None if ok else f"figure does not belong to «{binding.noun}»"
        return None

    def _wrong_label(self, start: int, kind: str, readings: list[tuple]) -> str | None:
        """Reason if the figure directly follows a known label whose value it does not match.

        A date token is checked against date labels; a percent token against ratio labels (x 100);
        a plain number against amount, count and ratio labels (a ratio label also accepts the plain
        fraction, e.g. 0,9706). The longest label phrase that ends right before the figure wins, so
        "mediana de la relación entre monto adjudicado y presupuesto" is never read as "presupuesto".
        """
        prefix = fold_chars(self.original[:start])
        applicable = {"date": {"date"}, "percent": {"ratio"}, "number": {"amount", "count", "ratio"}}[kind]
        candidates = [
            (found.start(), binding)
            for binding in self.allowed.bindings
            if binding.kind in applicable and (found := binding.pattern.search(prefix))
        ]
        if not candidates:
            return None
        binding = min(candidates, key=lambda c: c[0])[1]
        if kind == "date":
            ok = readings[0][0] in binding.values
        else:
            scale = 100 if kind == "percent" else 1
            pool = [v * scale for v in binding.values]
            ok = any(_matches(pool, v, d, percent=kind == "percent") is not None for v, d in readings)
        return None if ok else f"figure does not belong to «{binding.phrases[0]}»"

    # 5 ---------------------------------------------------------------------------------------
    def dates(self) -> None:
        month_index = {name: i + 1 for i, name in enumerate(MONTHS_ES)}
        for pattern, build in (
            (_ISO, lambda m: (int(m[1]), int(m[2]), int(m[3]))),
            (_SLASH, lambda m: (int(m[3]), int(m[2]), int(m[1]))),
            (_LONG, lambda m: (int(m[3]), month_index[m[2].lower()], int(m[1]))),
        ):
            for match in list(pattern.finditer(self.work)):
                self._check_date(match, build(match))
        for match in list(_MONTH_YEAR.finditer(self.work)):
            key = (int(match[2]), month_index[match[1].lower()])
            ok = key in self.allowed.year_months
            self.record(
                ok,
                _token("date", match.group(), match.span(), reason=None if ok else "month not in evidence"),
            )
            self.work = _blank(self.work, *match.span())

    def _check_date(self, match: re.Match[str], parts: tuple[int, int, int]) -> None:
        try:
            value: date | None = date(*parts)
        except ValueError:
            value = None
        ok = value is not None and value in self.allowed.dates
        reason = None if ok else ("invalid date" if value is None else "date not in evidence")
        if ok and value is not None and (wrong := self._wrong_label(match.start(), "date", [(value, 0)])):
            ok, reason = False, wrong
        matched = value.isoformat() if ok and value else None
        self.record(ok, _token("date", match.group(), match.span(), matched, reason))
        self.work = _blank(self.work, *match.span())

    # 6 ---------------------------------------------------------------------------------------
    def numbers(self) -> None:
        pct_values = [r * 100 for r in self.allowed.ratios]
        for match in list(_NUMBER.finditer(self.work)):
            is_percent = match.group(2) is not None
            readings = _number_candidates(match.group(1))
            pool = self.allowed.numbers + pct_values if is_percent else self.allowed.numbers
            hit = next(
                (m for v, d in readings if (m := _matches(pool, v, d, percent=is_percent)) is not None),
                None,
            )
            reason = (
                None
                if hit is not None
                else ("malformed number" if not readings else "number not in evidence")
            )
            kind = "percent" if is_percent else "number"
            if hit is not None and (wrong := self._wrong_label(match.start(), kind, readings)):
                hit, reason = None, wrong
            if hit is not None and not is_percent and (wrong := self._wrong_noun(match.end(), readings)):
                hit, reason = None, wrong
            self.record(
                hit is not None,
                _token(
                    kind,
                    match.group(),
                    match.span(),
                    None if hit is None else _short(hit),
                    reason,
                ),
            )
            self.work = _blank(self.work, *match.span())

    def number_words(self) -> None:
        folded = fold_chars(self.work)
        for match in _NUMBER_WORD.finditer(folded):
            value = Decimal(NUMBER_WORDS[match.group()])
            hit = _matches(self.allowed.numbers, value, 0) is not None
            reason = None if hit else "number word not in evidence"
            self.record(
                hit, _token("number", self.original[match.start() : match.end()], match.span(), reason=reason)
            )

    # 7 ---------------------------------------------------------------------------------------
    def names(self) -> None:
        view = _LABEL_TOKEN.sub(lambda m: " " * len(m.group()), self.work)
        for match in _NAME_SPAN.finditer(view):
            sentence_start = bool(_SENTENCE_START.search(self.work[: match.start()]))
            words = [(m.group(), match.start() + m.start()) for m in re.finditer(r"\S+", match.group())]
            while words and (
                words[0][0] in FUNCTION_WORDS
                or (sentence_start and words[0][0] in SENTENCE_STARTERS)
                or words[0][0] in _CONNECTORS
            ):
                words.pop(0)
            if not words:
                continue
            start = words[0][1]
            end = match.end()
            text = self.work[start:end]
            key = pad(norm(text))
            if key.strip() == "":
                continue
            ok = any(key in name for name in self.allowed.names)
            if not ok and sentence_start and len(words) == 1 and words[0][0] in SENTENCE_STARTERS:
                continue
            self.record(ok, _token("name", text, (start, end), reason=None if ok else "name not in evidence"))


def _is_grounded_value(raw: str, allowed: AllowedValues) -> bool:
    """A quote made only of grounded values (a date, an amount, a code), nothing else."""
    if _QUOTE.search(raw):
        return False
    report = verify_with(raw, allowed)
    if not report.passed or not report.supported:
        return False
    rest = list(raw)
    for token in report.supported:
        rest[token.start : token.end] = " " * (token.end - token.start)
    return not re.sub(r"[\W_]+|\bde\b", "", "".join(rest))


def verify_with(text: str, allowed: AllowedValues) -> GroundingReport:
    run = _Run(text, allowed)
    run.quotes()
    run.bypass_names()
    run.forbidden_wording()
    run.claims()
    run.roles()
    run.identifiers()
    run.dates()
    run.names()
    run.numbers()
    run.number_words()
    key = lambda t: t.start  # noqa: E731
    supported, unsupported, forbidden = (
        sorted(x, key=key) for x in (run.supported, run.unsupported, run.forbidden)
    )
    return GroundingReport(
        passed=not unsupported and not forbidden,
        n_checked=len(supported) + len(unsupported) + len(forbidden),
        supported=supported,
        unsupported=unsupported,
        forbidden=forbidden,
    )


def verify(text: str, pack: EvidencePack) -> GroundingReport:
    """Check `text` against `pack`; any unsupported or forbidden token makes `passed` False."""
    return verify_with(text, pack.allowed_values())
