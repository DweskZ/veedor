"""Spanish wording for signal evidence: one label mapping and one human statement per signal.

Every key a signal can emit has an entry in `EVIDENCE_LABELS`; a key without an entry is never
printed (a test compares the mapping with the keys the marts builder emits). Statements are built
from the evidence of the fired signal only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from veedor.domain.dossier.allowed import CODE, ISO_DATE, LONG_DIGITS, MASKED_RUC, RUC
from veedor.domain.dossier.formatting import fmt_date, fmt_num, fmt_pct, fmt_times, fmt_usd, quote
from veedor.domain.dossier.models import SignalFact
from veedor.domain.dossier.safety import is_unsafe_text
from veedor.domain.dossier.text import norm

HIDDEN = "hidden"

# key -> (Spanish label, kind). kinds: text, id, usd, count, year, date, pct, times, days, hidden
EVIDENCE_LABELS: dict[str, tuple[str, str]] = {
    "method": ("procedimiento", "text"),
    "year": ("año", "year"),
    "n_tenderers": ("número de oferentes", "count"),
    "tender_start": ("inicio de ofertas", "date"),
    "tender_end": ("cierre de ofertas", "date"),
    "window_days": ("plazo de ofertas en días", "days"),
    "p05_days": ("umbral estadístico del plazo en días", "days"),
    "n_method_year": ("procesos comparados del mismo procedimiento y año", "count"),
    "budget": ("presupuesto referencial", "usd"),
    "award_total": ("monto adjudicado", "usd"),
    "award_to_budget": ("relación entre monto adjudicado y presupuesto", "pct"),
    "p95_ratio": ("valor estadístico de referencia de la relación", "pct"),
    "threshold": ("umbral de la relación", "pct"),
    "supplier_amount": ("monto recibido por el proveedor en el año", "usd"),
    "buyer_total": ("total adjudicado por la entidad en el año", "usd"),
    "share": ("participación del proveedor", "pct"),
    "n_awards_buyer_year": ("adjudicaciones de la entidad en el año", "count"),
    "cpc_prefix": ("prefijo CPC", "text"),
    "n_in_window": ("procesos dentro de la ventana", "count"),
    "window_start": ("inicio de la ventana", "date"),
    "window_end": ("fin de la ventana", "date"),
    "n_same_buyer_supplier_cpc": ("procesos de la entidad y el proveedor con ese CPC", "count"),
    "cobidder_name": ("oferente coincidente", "text"),
    "cobidder_ruc": ("RUC del oferente coincidente", "id"),
    "n_meetings": ("procesos en los que coinciden", "count"),
    "n_recurring_cobidders_in_process": ("oferentes recurrentes en este proceso", "count"),
    "activity_start_date": ("inicio de actividades", "date"),
    "first_award_date": ("fecha de la primera adjudicación", "date"),
    "days_between": ("días entre el inicio de actividades y la adjudicación", "count"),
    "sri_status": ("estado en el SRI", "text"),
    "suspension_date": ("fecha de suspensión", "date"),
    "restart_date": ("fecha de reinicio", "date"),
    "process_date": ("fecha de referencia del proceso", "date"),
    "resolution": ("resolución", "id"),
    "notification_date": ("fecha de notificación", "date"),
    "qualification_detail": ("calificación", "text"),
    "challenge_state": ("estado de la impugnación", "text"),
    "revenue": ("ingresos reportados", "usd"),
    "revenue_year": ("año de los ingresos", "year"),
    "ratio": ("relación entre monto adjudicado e ingresos", "times"),
    "factor": ("umbral de la relación entre monto e ingresos", "times"),
    # Shown elsewhere or internal flags: never printed as data.
    "supplier_awards": ("adjudicaciones del proveedor en el año", "count"),
    "largest_supplier_process_share": ("participación del mayor proceso en el total de la entidad", "pct"),
    "award_year": ("año de la adjudicación", "year"),
    "years_before_award": ("diferencia entre el año de los ingresos y el de la adjudicación", "count"),
    "comparison": ("", HIDDEN),
    "listed_after_process": ("", HIDDEN),
    "supplier_ruc": ("", HIDDEN),
    "supplier_name": ("", HIDDEN),
    "winner_ruc": ("", HIDDEN),
    "winner_name": ("", HIDDEN),
    "buyer_ruc": ("", HIDDEN),
    "status_is_current": ("", HIDDEN),
    "listed_after_award": ("", HIDDEN),
    "timing": ("", HIDDEN),
}

_PLAIN_ID = (RUC, MASKED_RUC, CODE, LONG_DIGITS)


def _text_value(value: str) -> str | None:
    text = value.strip()
    if not text or not norm(text):
        return None
    if ISO_DATE.match(text):
        return fmt_date(text)
    if any(p.match(text) for p in _PLAIN_ID):
        return text
    return None if is_unsafe_text(text) else quote(text, 120)


def _format(value: Any, kind: str) -> str | None:
    if value is None or isinstance(value, bool | list | dict):
        return None
    if kind == "text" or kind == "id":
        return _text_value(str(value))
    if kind == "date":
        return fmt_date(str(value)) if ISO_DATE.match(str(value)) else None
    if not isinstance(value, int | float):
        return None
    if kind == "usd":
        return fmt_usd(value)
    if kind == "pct":
        return fmt_pct(value, 1)
    if kind == "times":
        return fmt_times(value)
    if kind == "year":
        return str(int(value))
    if kind == "days":
        return f"{fmt_num(value, 2)} días"
    return fmt_num(value)


def evidence_line(evidence: dict[str, Any]) -> str:
    """Spanish `label value` pairs for every mapped, visible evidence key (unmapped keys are skipped)."""
    parts = []
    for key, value in evidence.items():
        label, kind = EVIDENCE_LABELS.get(key, ("", HIDDEN))
        rendered = None if kind == HIDDEN else _format(value, kind)
        if rendered:
            parts.append(f"{label} {rendered}")
    return "; ".join(parts)


def unmapped_keys(evidence: dict[str, Any]) -> list[str]:
    return [k for k in evidence if k not in EVIDENCE_LABELS]


# --- statements ----------------------------------------------------------------------------


def _q(value: Any) -> str | None:
    return _text_value(str(value)) if isinstance(value, str) else None


def _date(e: dict[str, Any], key: str) -> str | None:
    value = e.get(key)
    return fmt_date(value) if isinstance(value, str) and ISO_DATE.match(value) else None


def _single_bidder(e: dict[str, Any], s: SignalFact) -> str | None:
    return "El proceso recibió un solo oferente."


def _short_window(e: dict[str, Any], s: SignalFact) -> str | None:
    if e.get("window_days") is None or e.get("p05_days") is None:
        return None
    span = ""
    if _date(e, "tender_start") and _date(e, "tender_end"):
        span = f" (del {_date(e, 'tender_start')} al {_date(e, 'tender_end')})"
    return (
        f"El plazo de ofertas fue de {fmt_num(e['window_days'], 2)} días{span}; el umbral estadístico "
        f"para el mismo procedimiento y año es de {fmt_num(e['p05_days'], 2)} días."
    )


def _low_saving(e: dict[str, Any], s: SignalFact) -> str | None:
    if e.get("award_total") is None or e.get("budget") is None or e.get("award_to_budget") is None:
        return None
    text = (
        f"El monto adjudicado ({fmt_usd(e['award_total'])}) equivale a {fmt_pct(e['award_to_budget'])} del "
        f"presupuesto referencial ({fmt_usd(e['budget'])})"
    )
    if e.get("threshold") is not None:
        text += f"; el umbral estadístico para el mismo procedimiento y año es {fmt_pct(e['threshold'])}"
    return text + "."


def _new_supplier(e: dict[str, Any], s: SignalFact) -> str | None:
    if e.get("days_between") is None or not _date(e, "activity_start_date"):
        return None
    tail = f" ({_date(e, 'first_award_date')})" if _date(e, "first_award_date") else ""
    return (
        f"El proveedor inició actividades el {_date(e, 'activity_start_date')}, "
        f"{fmt_num(e['days_between'])} días antes de la primera adjudicación{tail}."
    )


def _not_active(e: dict[str, Any], s: SignalFact) -> str | None:
    status = _q(e.get("sri_status"))
    head = (
        f"El SRI registra al proveedor con estado {status}"
        if status
        else "El SRI registra al proveedor como no activo"
    )
    suspension = _date(e, "suspension_date")
    if e.get("timing") == "suspended_before_process" and suspension:
        process = f" ({_date(e, 'process_date')})" if _date(e, "process_date") else ""
        return (
            f"{head}; la suspensión del {suspension} es anterior a la fecha de referencia del "
            f"proceso{process}."
        )
    return f"{head}; no es posible establecer si el proveedor estaba activo al momento del proceso."


def _listed_later(e: dict[str, Any]) -> bool | None:
    """Compare the two dates when both exist; otherwise trust the flag; otherwise unknown."""
    notified, process = e.get("notification_date"), e.get("process_date")
    if (
        isinstance(notified, str)
        and isinstance(process, str)
        and ISO_DATE.match(notified)
        and ISO_DATE.match(process)
    ):
        return notified[:10] > process[:10]
    flag = e.get("listed_after_process", e.get("listed_after_award"))
    return (
        flag
        if isinstance(flag, bool) and not (flag is False and e.get("notification_date") is None)
        else None
    )


def _ghost(e: dict[str, Any], s: SignalFact) -> str | None:
    """The SRI's own wording stays an attributed quotation; a late listing is said in the same sentence."""
    text = "El RUC del proveedor figura en el listado de empresas fantasmas publicado por el SRI"
    resolution = _text_value(e["resolution"]) if isinstance(e.get("resolution"), str) else None
    qualification = _q(e.get("qualification_detail"))
    if resolution or qualification:
        text += ": calificación asignada por el SRI"
        if resolution:
            text += f" en la resolución n.º {resolution}"
            if _date(e, "notification_date"):
                text += f", notificada el {_date(e, 'notification_date')}"
        if qualification:
            text += f": {qualification}"
    later = _listed_later(e)
    if later is True:
        text += "; la notificación es posterior a la fecha de referencia del proceso"
        if _date(e, "process_date"):
            text += f" ({_date(e, 'process_date')})"
    elif later is False:
        text += "; la notificación no es posterior a la fecha de referencia del proceso"
    else:
        text += (
            "; no es posible establecer si el listado fue anterior o posterior al proceso porque falta una "
            "de las fechas"
        )
    return text + "."


def _concentration(e: dict[str, Any], s: SignalFact) -> str | None:
    needed = ("supplier_amount", "buyer_total", "share", "n_awards_buyer_year", "year")
    if any(e.get(k) is None for k in needed):
        return None
    return (
        f"En {int(e['year'])}, el proveedor recibió {fmt_usd(e['supplier_amount'])} de los "
        f"{fmt_usd(e['buyer_total'])} adjudicados por la entidad ({fmt_pct(e['share'])}), "
        f"en un total de {fmt_num(e['n_awards_buyer_year'])} adjudicaciones de la entidad ese año."
    )


def _repeated_direct(e: dict[str, Any], s: SignalFact) -> str | None:
    needed = ("n_in_window", "n_same_buyer_supplier_cpc", "window_days")
    if any(e.get(k) is None for k in needed) or not (_date(e, "window_start") and _date(e, "window_end")):
        return None
    cpc = f" ({_q(e.get('cpc_prefix'))})" if _q(e.get("cpc_prefix")) else ""
    return (
        f"La entidad adjudicó de forma directa {fmt_num(e['n_in_window'])} procesos al mismo proveedor "
        f"con el mismo prefijo CPC{cpc} entre el {_date(e, 'window_start')} y el {_date(e, 'window_end')} "
        f"({fmt_num(e['window_days'])} días); en total el par registra "
        f"{fmt_num(e['n_same_buyer_supplier_cpc'])} procesos con ese prefijo."
    )


def _cobidders(e: dict[str, Any], s: SignalFact) -> str | None:
    if e.get("n_meetings") is None:
        return None
    who = f" y el oferente {_q(e.get('cobidder_name'))}" if _q(e.get("cobidder_name")) else " y otro oferente"
    return (
        f"El proveedor adjudicado{who} coincidieron en {fmt_num(e['n_meetings'])} procesos "
        "competitivos de la misma entidad."
    )


def _contract_size(e: dict[str, Any], s: SignalFact) -> str | None:
    needed = ("award_total", "revenue", "ratio", "factor")
    if any(e.get(k) is None for k in needed):
        return None
    year = f" para {int(e['revenue_year'])}" if e.get("revenue_year") is not None else ""
    note = (
        " Es una referencia de contexto: los ingresos son del mismo año de la adjudicación."
        if e.get("comparison") == "same_year"
        else ""
    )
    return (
        f"El monto adjudicado ({fmt_usd(e['award_total'])}) equivale a {fmt_times(e['ratio'])} los "
        f"ingresos reportados por la empresa{year} ({fmt_usd(e['revenue'])}); el umbral de la señal es "
        f"{fmt_num(e['factor'])} veces.{note}"
    )


STATEMENTS: dict[str, Callable[[dict[str, Any], SignalFact], str | None]] = {
    "SINGLE_BIDDER": _single_bidder,
    "SHORT_TENDER_WINDOW": _short_window,
    "LOW_SAVING": _low_saving,
    "NEW_SUPPLIER": _new_supplier,
    "SUPPLIER_NOT_ACTIVE": _not_active,
    "GHOST_COMPANY_LIST": _ghost,
    "BUYER_CONCENTRATION": _concentration,
    "REPEATED_DIRECT_AWARDS": _repeated_direct,
    "RECURRING_COBIDDERS": _cobidders,
    "CONTRACT_VS_COMPANY_SIZE": _contract_size,
    "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR": _contract_size,
    "GHOST_COMPANY_LISTED_LATER": _ghost,
}


def signal_statement(signal: SignalFact) -> str:
    """One sentence a reader can understand, from the signal's own evidence."""
    builder = STATEMENTS.get(signal.code)
    text = builder(signal.evidence, signal) if builder else None
    return text or f"Se activó el indicador «{signal.label_es}»."
