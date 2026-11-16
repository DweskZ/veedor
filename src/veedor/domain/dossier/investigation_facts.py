# ruff: noqa: E501
"""Fact catalogue of the investigation (stage 2): one `FactSpec` per sentence the renderer may write.

Each spec has an id, a section, a Spanish label, the source entry it cites, an applicability predicate
and a renderer. `catalogue()` includes a spec only when it applies, so a pack without an
investigation renders exactly as before, and a failed lookup renders as ``no disponible`` instead of a
value. Sentences are built from typed pack fields only; the one source string they can quote (a
Contraloría report title) is screened before it reaches the pack and is hidden from the model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from veedor.domain.dossier.formatting import fmt_count, fmt_date, fmt_num, fmt_times, fmt_usd, fmt_year
from veedor.domain.dossier.models import (
    AuditFacts,
    AuditReportRef,
    CompanyFinancialsFacts,
    CompanyRegistryFacts,
    EnquiriesFacts,
    EvidencePack,
    InvestigationFacts,
    PairHistoryFacts,
    SimilarPurchasesFacts,
    TaxRegistryLiveFacts,
)
from veedor.domain.dossier.safety import is_unsafe_text
from veedor.domain.dossier.vocabulary import (
    SECTION_CONTEXT,
    SECTION_INVESTIGATION,
    SECTION_RELATION,
    SECTION_WINNER,
)
from veedor.domain.investigation.vocab import (
    OUTCOME_PHRASE_ES,
    REASON_PHRASE_ES,
    SOURCE_LABEL_ES,
    SPECIALIST_LABEL_ES,
    UNAVAILABLE_ES,
)

FAILED = ("timeout", "upstream_error", "invalid_result")
LEGAL_STATUS_ES = {
    "active": "activa",
    "dissolution_or_liquidation": "en disolución o en liquidación",
    "cancelled_or_inactive": "cancelada o inactiva",
    "other": "otra situación; consulte el registro de la fuente",
}
SRI_STATUS_ES = {"active": "activo", "suspended": "suspendido", "cancelled": "cancelado", "other": "otro"}
CLASS_ES = {"especial": "especial", "otro": "otro", "other": "otra clase"}
MIPYMES_ES = {
    "micro": "micro",
    "pequena": "pequeña",
    "mediana": "mediana",
    "grande": "grande",
    "no_declarado": "no declarada",
    "other": "otra categoría",
}
REPORT_TYPE_NOTE = "los tipos de informe se muestran solo cuando pertenecen a una lista cerrada"
OMITTED_QUOTE = "«[cita de la fuente omitida]»"


@dataclass(frozen=True)
class FactSpec:
    id: str
    section: str
    label_es: str
    source_key: str | None
    applies: Callable[[EvidencePack], bool]
    render: Callable[[EvidencePack], str]
    untrusted_quote: bool = False  # the sentence quotes third-party text that a model must not see


OUT_OF_RANGE = "no disponible (valor fuera de rango en la fuente)"
NOT_AVAILABLE_ES = "no disponible"
SNAPSHOT_CAVEAT = "no es necesariamente el vigente al momento del proceso"


def _unavailable(label: str) -> str:
    return f"{label}: {UNAVAILABLE_ES}."


def _shown(text: str | None, name: str, rejected: list[str]) -> str:
    """The rendered value, or the out-of-range / not-available wording when there is none."""
    if text is not None:
        return text
    return OUT_OF_RANGE if name in rejected else NOT_AVAILABLE_ES


# --- shared helpers ----------------------------------------------------------------------------


def reference_point(pack: EvidencePack) -> tuple[str | None, str | None]:
    """(ISO day, Spanish name of the field) of the process reference date, as used by every fact."""
    if pack.history is not None:
        return pack.history.reference_date, pack.history.reference_date_kind
    p = pack.process
    for value, name in (
        (p.first_award_date, "fecha de adjudicación"),
        (p.date_signed, "fecha de firma"),
        (p.tender_start, "inicio de ofertas"),
    ):
        if value:
            return value, name
    return None, None


def _failed(facts: Any) -> bool:
    return facts is not None and facts.outcome in FAILED


def _missing_record(facts: Any) -> bool:
    return facts is not None and facts.outcome == "ok" and facts.found is False


def _ok_record(facts: Any) -> bool:
    return facts is not None and facts.outcome == "ok" and facts.found is not False


def _inv(pack: EvidencePack) -> InvestigationFacts:
    assert pack.investigation is not None  # specs run only when an investigation exists
    return pack.investigation


# --- company (Superintendencia de Compañías) ---------------------------------------------------

_CO = "Registro de la compañía (Superintendencia de Compañías)"


def _co(pack: EvidencePack) -> CompanyRegistryFacts | None:
    c = _inv(pack).company
    return c if _ok_record(c) else None


def _co_has(pack: EvidencePack, field: str) -> bool:
    c = _co(pack)
    return c is not None and (getattr(c, field) is not None or field in c.out_of_range)


def _incorporation_text(pack: EvidencePack) -> str:
    c = _co(pack)
    assert c is not None
    if c.incorporation_date is None:
        return f"Fecha de constitución: {OUT_OF_RANGE}."
    text = f"Fecha de constitución: {fmt_date(c.incorporation_date)}."
    ref, kind = reference_point(pack)
    days = c.days_incorporation_to_process
    if days is None or ref is None:
        return text
    point = f"({kind}: {fmt_date(ref)})"
    if days >= 0:
        verb = "transcurrió" if days == 1 else "transcurrieron"
        return (
            f"{text} Entre la constitución y la fecha de referencia del proceso {point} "
            f"{verb} {fmt_count(days, 'día', 'días')}."
        )
    return (
        f"{text} La constitución es posterior a la fecha de referencia del proceso {point} "
        f"por {fmt_count(abs(days), 'día', 'días')}."
    )


def multiple_text(times: float) -> str:
    """A multiple; one that rounds to zero is written as a bound, never as "0 veces"."""
    return "menos de 0,01 veces" if times < 0.01 else fmt_times(times)


def _capital_text(pack: EvidencePack) -> str:
    c = _co(pack)
    assert c is not None
    if c.subscribed_capital is None:
        return f"Capital suscrito: {OUT_OF_RANGE}."
    text = (
        f"Capital suscrito: {fmt_usd(c.subscribed_capital)} "
        f"(cifra registrada a la fecha de la consulta; {SNAPSHOT_CAVEAT})."
    )
    if c.award_to_capital_times is not None:
        text += (
            " La relación compara el monto adjudicado con el capital registrado a la fecha de la consulta: "
            f"el monto adjudicado equivale a {multiple_text(c.award_to_capital_times)} el capital suscrito."
        )
    return text


def _legal_status_text(pack: EvidencePack) -> str:
    c = _co(pack)
    assert c is not None and c.legal_status is not None
    return (
        "Situación legal a la fecha de la consulta a la Superintendencia de Compañías: "
        f"{LEGAL_STATUS_ES[c.legal_status]}. {SNAPSHOT_CAVEAT.capitalize()}."
    )


def _has_legal_status(pack: EvidencePack) -> bool:
    c = _co(pack)
    return c is not None and c.legal_status is not None


def _filing_text(pack: EvidencePack) -> str:
    c = _co(pack)
    assert c is not None
    year = fmt_year(c.last_balance_year) if c.last_balance_year is not None else OUT_OF_RANGE
    return f"Último ejercicio fiscal con balance presentado a la Superintendencia de Compañías: {year}."


# --- financial statements ----------------------------------------------------------------------

_FIN = "Estados financieros (Superintendencia de Compañías)"


def _fin(pack: EvidencePack) -> CompanyFinancialsFacts | None:
    f = _inv(pack).financials
    return f if f is not None and f.outcome == "ok" and f.found else None


def _financials_text(pack: EvidencePack) -> str:
    f = _fin(pack)
    assert f is not None
    bad = f.out_of_range
    employees = _shown(None if f.employees is None else fmt_num(f.employees), "employees", bad)
    equity = _shown(None if f.equity is None else fmt_usd(f.equity), "equity", bad)
    assets = _shown(None if f.assets is None else fmt_usd(f.assets), "assets", bad)
    return (
        "Últimos estados financieros presentados de un ejercicio anterior al del proceso: "
        f"ejercicio {fmt_year(f.fiscal_year)}; empleados reportados: {employees}; patrimonio: {equity}; "
        f"activos: {assets}."
    )


# --- tax registry (SRI live) -------------------------------------------------------------------

_SRI = "Consulta en línea al SRI"


def _tax(pack: EvidencePack) -> TaxRegistryLiveFacts | None:
    t = _inv(pack).tax_registry
    return t if _ok_record(t) else None


def _tax_text(pack: EvidencePack) -> str:
    t = _tax(pack)
    assert t is not None
    parts = [
        f"{_SRI} (estado a la fecha de la consulta): estado {SRI_STATUS_ES.get(t.status or '', 'no disponible')}; "
        f"clase de contribuyente: {CLASS_ES.get(t.taxpayer_class or '', 'no disponible')}; "
        f"categoría de empresa: {MIPYMES_ES.get(t.mipymes or '', 'no disponible')}."
    ]
    if t.activity_start_date:
        parts.append(f"Inicio de actividades según la consulta: {fmt_date(t.activity_start_date)}.")
    elif "activity_start_date" in t.out_of_range:
        parts.append(f"Inicio de actividades según la consulta: {OUT_OF_RANGE}.")
    if t.cessation_reported:
        parts.append("La consulta informa una fecha de cese de actividades.")
    elif "cessation_date" in t.out_of_range:
        parts.append(f"Fecha de cese de actividades según la consulta: {OUT_OF_RANGE}.")
    return " ".join(parts)


def _has_tax_match(pack: EvidencePack) -> bool:
    t = _tax(pack)
    return t is not None and t.status_matches_download is not None


def _tax_match_text(pack: EvidencePack) -> str:
    t = _tax(pack)
    assert t is not None
    verb = "coincide" if t.status_matches_download else "no coincide"
    return f"El estado de la consulta en línea {verb} con el estado del listado descargado del SRI."


# --- history -----------------------------------------------------------------------------------


def _pair(pack: EvidencePack) -> PairHistoryFacts | None:
    p = _inv(pack).pair_history
    return p if p is not None and p.outcome == "ok" else None


def _pair_text(pack: EvidencePack) -> str:
    p = _pair(pack)
    assert p is not None
    n = p.n_other_awards or 0
    if n == 0:
        return (
            "Sin contar este proceso, el conjunto de datos no registra otras adjudicaciones de esta entidad "
            "a este proveedor en ninguna fecha."
        )
    noun = "una adjudicación" if n == 1 else f"{n} adjudicaciones"
    if n == 1:
        informed = "con monto informado" if p.n_with_amount else "sin monto informado"
    else:
        informed = f"con monto informado en {p.n_with_amount} de ellas"
    return (
        f"Sin contar este proceso, el conjunto de datos registra {noun} de esta entidad a este proveedor "
        f"en cualquier fecha, {informed}. "
        f"El monto acumulado de esas adjudicaciones es {fmt_usd(p.total_other_amount)}."
    )


def _similar(pack: EvidencePack) -> SimilarPurchasesFacts | None:
    s = _inv(pack).similar
    return s if s is not None and s.outcome == "ok" else None


def _similar_text(pack: EvidencePack) -> str:
    s = _similar(pack)
    assert s is not None
    basis = "descripción del objeto" if s.basis == "description" else "clasificación del objeto"
    floor = fmt_num(s.similarity_floor)
    window = f"{fmt_count(s.window_days, 'día', 'días')} o menos de la fecha de referencia del proceso"
    if s.neighbours_examined == 0:
        return f"No hay compras similares de la misma entidad según la {basis} para comparar."
    if s.neighbours_examined == 1:
        head = f"La compra más similar de la misma entidad según la {basis} "
        if not s.n_above_floor:
            return f"{head}no supera una similitud mínima de {floor}."
        if not s.n_in_window:
            return f"{head}supera una similitud mínima de {floor}, pero no está a {window}."
        amount = f"su monto es {fmt_usd(s.combined_amount)}" + (
            "" if s.n_with_amount else " (monto no informado)"
        )
        return f"{head}supera una similitud mínima de {floor} y está a {window}; {amount}."
    head = f"Entre las {s.neighbours_examined} compras más similares de la misma entidad según la {basis}, "
    if not s.n_above_floor:
        return f"{head}ninguna supera una similitud mínima de {floor}."
    verb = "supera" if s.n_above_floor == 1 else "superan"
    head += f"{s.n_above_floor} {verb} una similitud mínima de {floor}"
    if not s.n_in_window:
        return f"{head}, y ninguna está a {window}."
    if s.n_in_window == 1:
        return (
            f"{head}, y 1 de ellas está a {window}; su monto es {fmt_usd(s.combined_amount)} "
            f"({'monto informado' if s.n_with_amount else 'monto no informado'})."
        )
    return (
        f"{head}, y {s.n_in_window} de ellas están a {window}; su monto combinado es "
        f"{fmt_usd(s.combined_amount)} (monto informado en {s.n_with_amount} de ellas)."
    )


# --- audit (Contraloría) -----------------------------------------------------------------------

_AUD = "Informes de la Contraloría General del Estado referidos a la entidad compradora"


def _audit(pack: EvidencePack) -> AuditFacts | None:
    a = _inv(pack).audit
    return a if a is not None and a.outcome == "ok" else None


def _audit_text(pack: EvidencePack) -> str:
    a = _audit(pack)
    assert a is not None
    n = a.n_reports
    scope = (
        f"Se examinaron {fmt_count(a.rows_examined or 0, 'fila', 'filas')} de {a.files_examined} de los "
        f"{fmt_count(a.files_in_catalogue or 0, 'archivo', 'archivos')} de informes aprobados del catálogo; "
        "el servicio entrega solo una parte de las filas de cada archivo."
    )
    if a.conclusive:
        return f"{_AUD}: {n} (coincidencia por nombre de entidad normalizado; cobertura completa)."
    if not a.match_reliable:
        return (
            f"{_AUD}: no se pudo establecer, porque el nombre de la entidad no permite una comparación fiable "
            "con los nombres del catálogo."
        )
    if n:
        return (
            f"{_AUD}: se {'encontró' if n == 1 else 'encontraron'} al menos {n} entre las filas examinadas (coincidencia por nombre de "
            f"entidad normalizado). {scope} Pueden existir otros informes no examinados."
        )
    return f"{_AUD}: no se pudo establecer. {scope} Que no aparezcan en las filas examinadas no implica que no existan."


def _report_line(r: AuditReportRef) -> str:
    inside = [r.report_type] if r.report_type else []
    if r.approval_date:
        inside.append(f"aprobado el {fmt_date(r.approval_date)}")
    if r.period_from and r.period_to:
        inside.append(f"período examinado del {fmt_date(r.period_from)} al {fmt_date(r.period_to)}")
    parts = [r.report_id or "número de informe no disponible"]
    if inside:
        parts.append(f"({', '.join(inside)})")
    if r.title and not is_unsafe_text(r.title):
        parts.append(f"«{r.title}»")
    return "- " + " ".join(parts)


_AUDIT_GROUPS = (
    (True, "n_covering", "Informes identificados cuyo período examinado incluye la fecha del proceso"),
    (
        False,
        "n_not_covering",
        "Informes identificados cuyo período examinado no incluye la fecha del proceso",
    ),
    (None, "n_period_unknown", "Informes identificados con período examinado no disponible"),
)
_QUOTE_NOTE = "cita textual de la fuente"


def _has_audit_reports(pack: EvidencePack) -> bool:
    a = _audit(pack)
    return a is not None and bool(a.reports)


def _audit_reports_text(pack: EvidencePack) -> str:
    """Up to the cap, covering reports first then newest approval; the counts are over ALL matches."""
    a = _audit(pack)
    assert a is not None
    shown = a.n_listed if a.n_listed is not None else len(a.reports)
    total = a.n_reports if a.n_reports is not None and a.n_reports >= shown else shown
    blocks = [
        f"Se muestran {shown} de {total} informes identificados (primero los de período examinado que "
        "incluye la fecha del proceso, luego por fecha de aprobación, del más reciente al más antiguo)."
    ]
    for covers, count_field, header in _AUDIT_GROUPS:
        group = [r for r in a.reports if r.covers_process is covers]
        count = getattr(a, count_field)
        count = len(group) if count is None else count
        if count:
            note = f"{count} en total"
            if covers is False:
                note += "; se muestran por completitud"
            if not group:
                blocks.append(f"{header} ({note}; ninguno se muestra por el límite de informes listados).")
                continue
            blocks.append(f"{header} ({note}; {_QUOTE_NOTE}):\n" + "\n".join(_report_line(r) for r in group))
    return "\n".join(blocks)


# --- enquiries (question-and-answer stage) -----------------------------------------------------

_ENQ = "En la etapa de preguntas y respuestas"


def _enq(pack: EvidencePack) -> EnquiriesFacts | None:
    e = _inv(pack).enquiries
    return e if e is not None and e.outcome == "ok" else None


def _enquiries_count_text(pack: EvidencePack) -> str:
    e = _enq(pack)
    assert e is not None
    registered = fmt_count(e.n_registered, "pregunta", "preguntas") if e.n_registered is not None else NOT_AVAILABLE_ES
    return (
        f"{_ENQ}: preguntas de oferentes registradas en el proceso: {registered}; con texto publicado y "
        f"analizable: {e.n_with_text}; de ellas, con una respuesta de texto publicada: {e.n_answered}. Una "
        "respuesta que es solo una fórmula breve no se cuenta, de modo que las respuestas son una cifra mínima."
    )


def _has_timing(pack: EvidencePack) -> bool:
    e = _enq(pack)
    return e is not None and bool(e.n_dated_pairs) and e.median_days_to_answer is not None


def _enquiries_timing_text(pack: EvidencePack) -> str:
    e = _enq(pack)
    assert e is not None and e.median_days_to_answer is not None and e.max_days_to_answer is not None
    return (
        f"{_ENQ}: en las {e.n_dated_pairs} preguntas con fecha de pregunta y fecha de respuesta, los días entre "
        f"una y otra tuvieron mediana de {fmt_num(e.median_days_to_answer)} días y máximo de "
        f"{fmt_count(e.max_days_to_answer, 'día', 'días')}."
    )


def _has_late(pack: EvidencePack) -> bool:
    e = _enq(pack)
    return e is not None and e.n_late is not None and e.deadline is not None and e.late_window_days is not None


def _enquiries_late_text(pack: EvidencePack) -> str:
    e = _enq(pack)
    assert e is not None and e.deadline is not None and e.late_window_days is not None
    return (
        f"{_ENQ}: preguntas con fecha en los {e.late_window_days} días anteriores al cierre de ofertas "
        f"(cierre de ofertas: {fmt_date(e.deadline)}): {e.n_late}."
    )


def _has_topics(pack: EvidencePack) -> bool:
    e = _enq(pack)
    return e is not None and bool(e.n_with_text) and e.topic_deadlines is not None


def _enquiries_topics_text(pack: EvidencePack) -> str:
    e = _enq(pack)
    assert e is not None
    return (
        f"{_ENQ}: preguntas por tema, según la cercanía de su significado con una descripción fija de cada "
        f"tema (una pregunta puede no tener tema): plazos y fechas, {e.topic_deadlines}; especificaciones "
        f"técnicas, {e.topic_specifications}; precio, {e.topic_price}; requisitos para "
        f"participar, {e.topic_requirements}. Es una clasificación automática aproximada."
    )


# --- what was done -----------------------------------------------------------------------------


def _any_investigation(pack: EvidencePack) -> bool:
    return pack.investigation is not None


def _specialists_text(pack: EvidencePack) -> str:
    inv = _inv(pack)
    if not inv.specialists:
        return "No se ejecutó ningún especialista de consulta para este proceso."
    items = []
    for s in inv.specialists:
        calls = "una consulta" if s.n_tool_calls == 1 else f"{s.n_tool_calls} consultas"
        items.append(f"{SPECIALIST_LABEL_ES.get(s.specialist, s.specialist)} ({calls})")
    return "Especialistas ejecutados: " + "; ".join(items) + "."


def _lookups_text(pack: EvidencePack) -> str:
    lines = []
    for item in _inv(pack).lookups:
        reason = f" ({REASON_PHRASE_ES[item.reason]})" if item.reason in REASON_PHRASE_ES else ""
        calls = f"; {item.calls} consultas" if item.calls > 1 else ""
        retries = (
            ""
            if item.retries == 0
            else "; un reintento"
            if item.retries == 1
            else f"; {item.retries} reintentos"
        )
        label = SOURCE_LABEL_ES.get(item.source, item.source)
        lines.append(
            f"- {label}: {OUTCOME_PHRASE_ES.get(item.outcome, item.outcome)}{reason}{calls}{retries}."
        )
    return "Fuentes consultadas y resultado de cada consulta:\n" + "\n".join(lines)


NOTE_TEXT = (
    "Las consultas son de solo lectura. No se consultan registros de personas naturales y no se "
    "almacenan nombres de personas obtenidos de las fuentes."
)


def _has_lookups(pack: EvidencePack) -> bool:
    return bool(pack.investigation and pack.investigation.lookups)


def _group_failed(group: str) -> Callable[[EvidencePack], bool]:
    return lambda p: p.investigation is not None and _failed(getattr(p.investigation, group))


def _group_missing(group: str) -> Callable[[EvidencePack], bool]:
    return lambda p: p.investigation is not None and _missing_record(getattr(p.investigation, group))


FACT_SPECS: tuple[FactSpec, ...] = (
    # winner section ------------------------------------------------------------------------
    FactSpec("investigation.company.unavailable", SECTION_WINNER, "Registro de la compañía: sin datos",
             "supercias_company", _group_failed("company"), lambda p: _unavailable(_CO)),
    FactSpec("investigation.company.not_found", SECTION_WINNER, "Registro de la compañía: sin registro",
             "supercias_company", _group_missing("company"),
             lambda p: f"{_CO}: la fuente no tiene un registro para este RUC en la consulta realizada."),
    FactSpec("investigation.company.legal_status", SECTION_WINNER, "Situación legal", "supercias_company",
             _has_legal_status, _legal_status_text),
    FactSpec("investigation.company.incorporation", SECTION_WINNER, "Fecha de constitución", "supercias_company",
             lambda p: _co_has(p, "incorporation_date"), _incorporation_text),
    FactSpec("investigation.company.capital", SECTION_WINNER, "Capital suscrito", "supercias_company",
             lambda p: _co_has(p, "subscribed_capital"), _capital_text),
    FactSpec("investigation.company.filing", SECTION_WINNER, "Último balance presentado", "supercias_company",
             lambda p: _co_has(p, "last_balance_year"), _filing_text),
    FactSpec("investigation.financials.unavailable", SECTION_WINNER, "Estados financieros: sin datos",
             "supercias_financials", _group_failed("financials"), lambda p: _unavailable(_FIN)),
    FactSpec("investigation.financials.none", SECTION_WINNER, "Estados financieros: sin ejercicio anterior",
             "supercias_financials", _group_missing("financials"),
             lambda p: f"{_FIN}: no disponible para un ejercicio anterior al proceso."),
    FactSpec("investigation.financials.latest", SECTION_WINNER, "Últimos estados financieros",
             "supercias_financials", lambda p: _fin(p) is not None, _financials_text),
    FactSpec("investigation.tax.unavailable", SECTION_WINNER, "Consulta al SRI: sin datos", "sri_live",
             _group_failed("tax_registry"), lambda p: _unavailable(_SRI)),
    FactSpec("investigation.tax.not_found", SECTION_WINNER, "Consulta al SRI: sin registro", "sri_live",
             _group_missing("tax_registry"), lambda p: f"{_SRI}: la fuente no tiene un registro para este RUC."),
    FactSpec("investigation.tax.live", SECTION_WINNER, "Consulta en línea al SRI", "sri_live",
             lambda p: _tax(p) is not None, _tax_text),
    FactSpec("investigation.tax.matches_download", SECTION_WINNER, "Consulta en línea frente al listado",
             "sri_live", _has_tax_match, _tax_match_text),
    # relation section ----------------------------------------------------------------------
    FactSpec("investigation.pair.unavailable", SECTION_RELATION, "Otras adjudicaciones: sin datos",
             "sercop_pair_awards", _group_failed("pair_history"),
             lambda p: _unavailable("Otras adjudicaciones entre esta entidad y este proveedor")),
    FactSpec("investigation.pair.others", SECTION_RELATION, "Otras adjudicaciones entre la entidad y el proveedor",
             "sercop_pair_awards", lambda p: _pair(p) is not None, _pair_text),
    # context section -----------------------------------------------------------------------
    FactSpec("investigation.similar.unavailable", SECTION_CONTEXT, "Compras similares: sin datos", "vector_index",
             _group_failed("similar"), lambda p: _unavailable("Compras similares de la misma entidad")),
    FactSpec("investigation.similar.window", SECTION_CONTEXT, "Compras similares de la misma entidad",
             "vector_index", lambda p: _similar(p) is not None, _similar_text),
    FactSpec("investigation.audit.unavailable", SECTION_CONTEXT, "Informes de control: sin datos",
             "contraloria_reports", _group_failed("audit"), lambda p: _unavailable(_AUD)),
    FactSpec("investigation.audit.count", SECTION_CONTEXT, "Informes de la Contraloría sobre la entidad compradora",
             "contraloria_reports", lambda p: _audit(p) is not None, _audit_text),
    FactSpec("investigation.audit.reports", SECTION_CONTEXT, "Informes identificados", "contraloria_reports",
             _has_audit_reports, _audit_reports_text, untrusted_quote=True),
    # enquiries -----------------------------------------------------------------------------
    FactSpec("investigation.enquiries.unavailable", SECTION_CONTEXT, "Etapa de preguntas: sin datos",
             "sercop_enquiries", _group_failed("enquiries"), lambda p: _unavailable(_ENQ)),
    FactSpec("investigation.enquiries.count", SECTION_CONTEXT, "Preguntas y respuestas del proceso",
             "sercop_enquiries", lambda p: _enq(p) is not None, _enquiries_count_text),
    FactSpec("investigation.enquiries.timing", SECTION_CONTEXT, "Días entre pregunta y respuesta",
             "sercop_enquiries", _has_timing, _enquiries_timing_text),
    FactSpec("investigation.enquiries.late", SECTION_CONTEXT, "Preguntas cerca del cierre de ofertas",
             "sercop_enquiries", _has_late, _enquiries_late_text),
    FactSpec("investigation.enquiries.topics", SECTION_CONTEXT, "Preguntas por tema",
             "sercop_enquiries", _has_topics, _enquiries_topics_text),
    # what was done -------------------------------------------------------------------------
    FactSpec("investigation.run.specialists", SECTION_INVESTIGATION, "Especialistas ejecutados", None,
             _any_investigation, _specialists_text),
    FactSpec("investigation.run.lookups", SECTION_INVESTIGATION, "Fuentes consultadas", None,
             _has_lookups, _lookups_text),
    FactSpec("investigation.run.note", SECTION_INVESTIGATION, "Alcance de las consultas", None,
             _any_investigation, lambda p: NOTE_TEXT),
)  # fmt: skip

SPEC_BY_ID = {spec.id: spec for spec in FACT_SPECS}
UNTRUSTED_QUOTE_IDS = frozenset(spec.id for spec in FACT_SPECS if spec.untrusted_quote)


def applicable_specs(pack: EvidencePack) -> list[FactSpec]:
    return [spec for spec in FACT_SPECS if spec.applies(pack)]


def investigation_facts(pack: EvidencePack) -> list[tuple[str, str, str]]:
    """``(id, section, text)`` of every applicable investigation fact, in catalogue order."""
    if pack.investigation is None:
        return []
    return [(spec.id, spec.section, spec.render(pack)) for spec in applicable_specs(pack)]
