"""Deterministic Spanish renderer built on a catalogue of facts.

Every sentence comes from `catalogue(pack)`: a list of `Fact(id, section, text)` built from
EvidencePack fields only. A missing fact renders as ``no disponible``. Free text from the data
(descriptions, activity, signal evidence strings) is only reproduced verbatim inside « » quotes after
the unsafe-text screen. Template mode renders every fact in default order; LLM mode renders the subset
and order that a validated `RenderPlan` selects, with the same sentences.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from veedor.domain.dossier.evidence_text import evidence_line, signal_statement
from veedor.domain.dossier.formatting import (
    CATEGORY_ES,
    STATUS_ES,
    fmt_date,
    fmt_num,
    fmt_pct,
    fmt_text,
    fmt_usd,
    fmt_year,
)
from veedor.domain.dossier.formatting import quote as _quote
from veedor.domain.dossier.investigation_facts import investigation_facts
from veedor.domain.dossier.models import EvidencePack, HistoryFacts, Section, SignalFact
from veedor.domain.dossier.plan import CONNECTIVES, REVIEWER_NOTES, PlanError, RenderPlan
from veedor.domain.dossier.safety import is_unsafe_text
from veedor.domain.dossier.signal_text import is_informational
from veedor.domain.dossier.vocabulary import (
    NOT_AVAILABLE,
    SECTION_CONTEXT,
    SECTION_INVESTIGATION,
    SECTION_LIMITS,
    SECTION_REGISTRAL,
    SECTION_RELATION,
    SECTION_SIGNALS,
    SECTION_TITLES,
    SECTION_WHAT,
    SECTION_WINNER,
)

DRAFT_NOTICE = "Este documento es un borrador para revisión humana."
OMITTED = "omitido por contener texto que el sistema no puede verificar; consulte el proceso original"
UNIDENTIFIED = "persona natural o sin identificar"


class Narrative(BaseModel):
    summary_es: str
    sections: list[Section]


@dataclass(frozen=True)
class Fact:
    id: str
    section: str
    text: str


def quote(value: str | None, limit: int = 280) -> str:
    if value and is_unsafe_text(value):
        return OMITTED
    return _quote(value, limit)


def _na(value: str | None) -> str:
    return fmt_text(value)


# --- signals ---------------------------------------------------------------------------------


def risk_signals(pack: EvidencePack) -> list[SignalFact]:
    return [s for s in pack.signals if not is_informational(s)]


def _signal_line(signal: SignalFact) -> str:
    parts = [f"- {signal.label_es}: {signal_statement(signal)}"]
    if signal.caveat:
        parts.append(signal.caveat)
    parts.append(
        f"Dato técnico: valor observado {fmt_num(signal.value, 2)}; umbral {fmt_num(signal.threshold, 2)}."
    )
    support = evidence_line(signal.evidence)
    if support:
        parts.append(f"Datos de respaldo: {support}.")
    return " ".join(parts)


# --- fact builders ---------------------------------------------------------------------------


ORIGIN_POINTER = "La descripción publicada por la entidad puede consultarse en el registro de origen."


def _object_line(pack: EvidencePack) -> str:
    """The free-text description is never quoted: the object comes from the CPC classification."""
    cpc = quote(pack.process.main_cpc_description)
    return f"Objeto según la clasificación CPC: {cpc}. {ORIGIN_POINTER}"


def _what_facts(pack: EvidencePack) -> list[Fact]:
    p = pack.process
    ratio = f" ({fmt_pct(p.award_budget_ratio)} del presupuesto)" if p.award_budget_ratio is not None else ""
    category = CATEGORY_ES.get(p.category or "", _na(p.category))
    status = STATUS_ES.get(p.status or "", _na(p.status))
    buyer = f"{_na(p.buyer_name)} (RUC {_na(p.buyer_ruc)})"
    rows = [
        ("process.object", _object_line(pack)),
        (
            "process.entity",
            f"Entidad contratante: {buyer}; región {_na(p.buyer_region)}, localidad {_na(p.buyer_locality)}.",
        ),
        (
            "process.procedure",
            f"Procedimiento: {_na(p.method)}; categoría: {category}; estado: {status}.",
        ),
        (
            "process.amounts",
            f"Presupuesto referencial: {fmt_usd(p.budget)}. "
            f"Monto adjudicado: {fmt_usd(p.award_total)}{ratio}.",
        ),
        (
            "process.tenderers",
            f"Número de oferentes: {fmt_num(p.n_tenderers)}. Inicio de ofertas: {fmt_date(p.tender_start)}; "
            f"cierre de ofertas: {fmt_date(p.tender_end)}.",
        ),
        (
            "process.award_dates",
            f"Fecha de adjudicación: {fmt_date(p.first_award_date)}; "
            f"fecha de firma: {fmt_date(p.date_signed)}.",
        ),
        (
            "process.cpc",
            f"Código CPC: {_na(p.main_cpc)}; descripción CPC: {quote(p.main_cpc_description)}.",
        ),
    ]
    return [Fact(i, SECTION_WHAT, t) for i, t in rows]


def _signal_facts(pack: EvidencePack) -> list[Fact]:
    if not pack.signals_available:
        return [Fact("signals.unavailable", SECTION_SIGNALS, "Señales de riesgo: no disponible.")]
    facts = [Fact(f"signal:{s.code}", SECTION_SIGNALS, _signal_line(s)) for s in risk_signals(pack)]
    if not facts:
        text = "No se detectaron señales de riesgo con los indicadores calculados."
        return [Fact("signals.none", SECTION_SIGNALS, text)]
    return facts


def _registral_facts(pack: EvidencePack) -> list[Fact]:
    if not pack.signals_available:
        return []
    return [
        Fact(f"signal:{s.code}", SECTION_REGISTRAL, _signal_line(s))
        for s in pack.signals
        if is_informational(s)
    ]


def _revenue_text(pack: EvidencePack) -> str:
    """Revenue lines. A reported zero is missing data, like everywhere else in the project."""
    r = pack.winner.registry if pack.winner else None
    if r is None:
        return ""
    in_year = r.revenue_award_year or None
    latest = r.latest_revenue or None
    lines = [f"Ingresos del año del proceso: {fmt_usd(in_year)} (año {fmt_year(r.award_year)})."]
    if latest is not None and r.latest_revenue_year != r.award_year:
        lines.append(
            f"Ingresos más recientes reportados: {fmt_usd(latest)} (año {fmt_year(r.latest_revenue_year)})."
        )
    return "\n".join(lines)


def _winner_facts(pack: EvidencePack) -> list[Fact]:
    w = pack.winner
    if w is None:
        return [Fact("winner.identity", SECTION_WINNER, "Proveedor adjudicado: no disponible.")]
    if w.kind == "natural_person" or not w.ruc or w.kind == "unknown":
        # Natural persons and suppliers without a RUC are never named, and nothing about them is listed.
        return [Fact("winner.identity", SECTION_WINNER, f"Proveedor adjudicado: {UNIDENTIFIED}.")]
    r = w.registry
    identity = f"Proveedor adjudicado: {_na(w.name)} (RUC {_na(w.ruc)})."
    if w.n_award_suppliers > 1:
        identity += (
            f"\nEl proceso tiene {w.n_award_suppliers} proveedores adjudicados; se detalla el principal."
        )
    ghost = {None: NOT_AVAILABLE, True: "figura", False: "no figura"}[r.ghost_listed]
    rows = [
        ("winner.identity", identity),
        (
            "winner.sri",
            f"Estado actual en el SRI: {_na(r.status)}; tipo de contribuyente: {_na(r.taxpayer_type)}. "
            "Es el estado a la fecha de los datos, no necesariamente el vigente al momento del proceso.\n"
            f"Inicio de actividades: {fmt_date(r.activity_start_date)}; provincia: {_na(r.province)}.\n"
            f"Actividad económica: {quote(r.activity)}; CIIU {quote(r.ciiu_code)}.",
        ),
        ("winner.ghost", f"Listado de empresas fantasmas publicado por el SRI: {ghost}."),
        (
            "winner.company",
            f"Tipo de compañía (Superintendencia de Compañías): {_na(r.company_type)}.",
        ),
        ("winner.revenue", _revenue_text(pack)),
    ]
    return [Fact(i, SECTION_WINNER, t) for i, t in rows if t]


def _pair_total(h: HistoryFacts) -> str:
    if h.n_pair_awards == 0:
        return (
            "En total, el conjunto de datos no registra otras adjudicaciones de esta entidad a este "
            "proveedor."
        )
    count = "una adjudicación" if h.n_pair_awards == 1 else f"{h.n_pair_awards} adjudicaciones"
    if h.pair_first_year is None:
        years = ""
    elif h.pair_first_year == h.pair_last_year:
        years = f" en {h.pair_first_year}"
    else:
        years = f" entre {h.pair_first_year} y {h.pair_last_year}"
    return (
        f"En total, el conjunto de datos registra {count} de esta entidad a este proveedor{years} "
        "(incluida la de este proceso)."
    )


def _relation_facts(pack: EvidencePack) -> list[Fact]:
    h = pack.history
    if h is None:
        text = "Historial entre la entidad y el proveedor: no disponible."
        return [Fact("relation.unavailable", SECTION_RELATION, text)]
    reference = f"{h.reference_date_kind}: {fmt_date(h.reference_date)}"
    if h.n_previous_awards == 0:
        previous = (
            "Sin adjudicaciones previas registradas entre esta entidad y este proveedor "
            f"(fecha de referencia utilizada, {reference})."
        )
    else:
        noun = "adjudicación previa" if h.n_previous_awards == 1 else "adjudicaciones previas"
        previous = (
            f"Antes de la fecha de referencia del proceso ({reference}), la entidad registra "
            f"{h.n_previous_awards} {noun} al mismo proveedor, con monto informado en {h.n_with_amount} de "
            f"ellas, por un total de {fmt_usd(h.total_previous_amount)}.\n"
            f"Primera adjudicación previa: {fmt_date(h.first_award_date)}; "
            f"última adjudicación previa: {fmt_date(h.last_award_date)}."
        )
    return [
        Fact("relation.previous", SECTION_RELATION, previous),
        Fact("relation.pair_total", SECTION_RELATION, _pair_total(h)),
    ]


def _context_facts(pack: EvidencePack) -> list[Fact]:
    c = pack.comparison
    if c is None:
        text = "Estadísticas comparativas del mismo procedimiento y año: no disponible."
        return [Fact("context.unavailable", SECTION_CONTEXT, text)]
    rows = [
        (
            "context.count",
            f"Procesos del mismo procedimiento ({_na(c.method)}) y año ({fmt_year(c.year)}): "
            f"{fmt_num(c.n_processes)}.",
        ),
        ("context.median_tenderers", f"Mediana de oferentes: {fmt_num(c.median_tenderers)}."),
        (
            "context.single_bidder_share",
            f"Proporción de procesos con un solo oferente: {fmt_pct(c.single_bidder_share)}.",
        ),
        (
            "context.median_ratio",
            "Mediana de la relación entre monto adjudicado y presupuesto: "
            f"{fmt_pct(c.median_award_budget_ratio)}.",
        ),
    ]
    return [Fact(i, SECTION_CONTEXT, t) for i, t in rows]


def catalogue(pack: EvidencePack) -> list[Fact]:
    """Every fact a dossier about this pack can state, in default order."""
    return [
        *_what_facts(pack),
        *_signal_facts(pack),
        *_registral_facts(pack),
        *_winner_facts(pack),
        *_relation_facts(pack),
        *_context_facts(pack),
        *[Fact(i, section, text) for i, section, text in investigation_facts(pack)],
    ]


def limitations(pack: EvidencePack, *, with_code: bool = True) -> str:
    code = f"el proceso {_na(pack.process.process_code)}" if with_code else "el proceso"
    return (
        "Estos resultados son indicadores de riesgo calculados con reglas estadísticas sobre datos "
        "abiertos; no constituyen una conclusión sobre la conducta de ninguna persona o entidad y "
        "requieren verificación humana. Los datos pueden tener errores de origen o estar incompletos; "
        "cuando un dato falta se indica como no disponible.\n"
        f"Para verificar, consulte {code} en el portal de "
        "compras públicas del SERCOP, revise los documentos del proceso y compare los datos del "
        "proveedor con las fuentes oficiales citadas. " + DRAFT_NOTICE
    )


# --- summary and rendering -------------------------------------------------------------------


def _summary(pack: EvidencePack, order: list[str] | None = None, note: str | None = None) -> str:
    p = pack.process
    head = (
        f"El proceso {_na(p.process_code)} ({_na(p.method)}) de la entidad {_na(p.buyer_name)}, "
        f"año {fmt_year(p.year)},"
    )
    signals = risk_signals(pack)
    if not pack.signals_available:
        verdict = "no tiene disponible el cálculo de señales de riesgo."
    elif not signals:
        verdict = "no presenta señales de riesgo entre los indicadores calculados."
    else:
        rank = {code: i for i, code in enumerate(order or [])}
        ordered = sorted(signals, key=lambda s: rank.get(s.code, len(rank)))
        labels = "; ".join(s.label_es for s in ordered)
        noun = "señal" if len(signals) == 1 else "señales"
        verdict = f"presenta {len(signals)} {noun} de riesgo: {labels}."
    score = (
        f" Puntaje de riesgo: {fmt_num(pack.risk_score)} sobre 100." if pack.risk_score is not None else ""
    )
    extra = f" {REVIEWER_NOTES[note].text}" if note else ""
    return f"{head} {verdict}{score}{extra} {DRAFT_NOTICE}"


def _assemble(pack: EvidencePack, bodies: dict[str, str], summary: str) -> Narrative:
    sections = [
        Section(title=title, body=bodies[title])
        for title in SECTION_TITLES
        if title in bodies and (bodies[title] or title == SECTION_LIMITS)
    ]
    return Narrative(summary_es=summary, sections=sections)


def render_template(pack: EvidencePack) -> Narrative:
    bodies = {title: "" for title in SECTION_TITLES}
    for fact in catalogue(pack):
        bodies[fact.section] = f"{bodies[fact.section]}\n{fact.text}".strip("\n")
    bodies[SECTION_LIMITS] = limitations(pack)
    return _assemble(pack, bodies, _summary(pack))


def validate_plan(plan: RenderPlan, pack: EvidencePack) -> None:
    """Raise `PlanError` unless every id exists in the catalogue (or the closed connective set)."""
    by_section: dict[str, set[str]] = {}
    for fact in catalogue(pack):
        by_section.setdefault(fact.section, set()).add(fact.id)
    known_signals = {s.code for s in risk_signals(pack)}
    for code in plan.summary_signal_order:
        if code not in known_signals:
            raise PlanError(f"unknown signal code in summary order: {code!r}")
    if plan.reviewer_note is not None:
        note = REVIEWER_NOTES.get(plan.reviewer_note)
        if note is None:
            raise PlanError(f"unknown reviewer note: {plan.reviewer_note!r}")
        if not note.applies(pack, None):
            raise PlanError(f"reviewer note not applicable to this process: {plan.reviewer_note!r}")
    for title, ids in plan.sections.items():
        if not ids:
            continue
        if title not in by_section and title != SECTION_LIMITS:
            raise PlanError(f"unknown or empty section: {title!r}")
        if title in (SECTION_LIMITS, SECTION_INVESTIGATION):
            raise PlanError(f"the section {title!r} is fixed")
        connectives = [i for i in ids if i in CONNECTIVES]
        if len(connectives) > 1:
            raise PlanError(f"more than one connective in {title!r}")
        for item in ids:
            if item in CONNECTIVES:
                if not CONNECTIVES[item].applies(pack, title):
                    raise PlanError(f"connective not applicable in {title!r}: {item!r}")
            elif item not in by_section[title]:
                raise PlanError(f"unknown fact id for {title!r}: {item!r}")


def render_plan(pack: EvidencePack, plan: RenderPlan) -> Narrative:
    """Render a validated plan with the template sentences. Signals are never dropped, only reordered."""
    validate_plan(plan, pack)
    facts = catalogue(pack)
    by_section: dict[str, list[Fact]] = {}
    for fact in facts:
        by_section.setdefault(fact.section, []).append(fact)
    bodies = {title: "" for title in SECTION_TITLES}
    for title, default in by_section.items():
        chosen = plan.sections.get(title) or []
        lines: list[str] = []
        by_id = {f.id: f for f in default}
        selected = [by_id[i] for i in dict.fromkeys(chosen) if i in by_id]
        if title in (SECTION_SIGNALS, SECTION_REGISTRAL):  # every signal stays, the model orders them
            selected += [f for f in default if f not in selected]
        elif not selected:
            selected = default
        else:  # investigation facts (including "no disponible" ones) are never hidden, only ordered
            selected += [f for f in default if f.id.startswith("investigation.") and f not in selected]
        connective = next((CONNECTIVES[i].text for i in chosen if i in CONNECTIVES), None)
        if connective:
            lines.append(connective)
        lines += [f.text for f in selected]
        bodies[title] = "\n".join(lines)
    bodies[SECTION_LIMITS] = limitations(pack)
    summary = _summary(pack, plan.summary_signal_order, plan.reviewer_note)
    return _assemble(pack, bodies, summary)


# --- minimal fallback ------------------------------------------------------------------------


def minimal_narrative(pack: EvidencePack) -> Narrative:
    """Facts table only, no prose, for when even the template cannot be verified."""
    p = pack.process
    table = "\n".join(
        [
            f"Código del proceso: {_na(p.process_code)}",
            f"Entidad contratante: {_na(p.buyer_name)}",
            f"Procedimiento: {_na(p.method)}",
            f"Presupuesto referencial: {fmt_usd(p.budget)}",
            f"Monto adjudicado: {fmt_usd(p.award_total)}",
        ]
    )
    summary = f"Dossier mínimo del proceso {_na(p.process_code)}. {DRAFT_NOTICE}"
    return _assemble(pack, {SECTION_WHAT: table, SECTION_LIMITS: limitations(pack)}, summary)


def ultra_minimal_narrative(pack: EvidencePack) -> Narrative:
    summary = f"Dossier mínimo del proceso {_na(pack.process.process_code)}. {DRAFT_NOTICE}"
    return _assemble(pack, {SECTION_LIMITS: limitations(pack)}, summary)


def bare_narrative(pack: EvidencePack) -> Narrative:
    """Constant text only: nothing from the data, so it cannot fail verification."""
    summary = f"Dossier mínimo. {DRAFT_NOTICE}"
    return _assemble(pack, {SECTION_LIMITS: limitations(pack, with_code=False)}, summary)
