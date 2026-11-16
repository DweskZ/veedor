"""Catalogue of Signals v1: code, Spanish label and description, scope, fields, threshold rule."""

from __future__ import annotations

from dataclasses import dataclass

SINGLE_BIDDER = "SINGLE_BIDDER"
SHORT_TENDER_WINDOW = "SHORT_TENDER_WINDOW"
LOW_SAVING = "LOW_SAVING"
NEW_SUPPLIER = "NEW_SUPPLIER"
SUPPLIER_NOT_ACTIVE = "SUPPLIER_NOT_ACTIVE"
GHOST_COMPANY_LIST = "GHOST_COMPANY_LIST"
BUYER_CONCENTRATION = "BUYER_CONCENTRATION"
REPEATED_DIRECT_AWARDS = "REPEATED_DIRECT_AWARDS"
RECURRING_COBIDDERS = "RECURRING_COBIDDERS"
CONTRACT_VS_COMPANY_SIZE = "CONTRACT_VS_COMPANY_SIZE"
# Context signals: informational, weight 0, never part of risk_score or n_signals.
GHOST_COMPANY_LISTED_LATER = "GHOST_COMPANY_LISTED_LATER"
CONTRACT_VS_COMPANY_SIZE_SAME_YEAR = "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR"

KIND_RISK = "risk"
KIND_CONTEXT = "context"


@dataclass(frozen=True, slots=True)
class SignalDefinition:
    code: str
    label_es: str
    description_es: str
    scope: str
    fields: tuple[str, ...]
    threshold_rule_es: str
    required_tables: tuple[str, ...] = ()
    statistical: bool = False
    kind: str = KIND_RISK

    @property
    def is_context(self) -> bool:
        return self.kind == KIND_CONTEXT

    @property
    def needs_registry(self) -> bool:
        return bool(self.required_tables)


SIGNALS: tuple[SignalDefinition, ...] = (
    SignalDefinition(
        code=SINGLE_BIDDER,
        label_es="Oferente único",
        description_es=(
            "El proceso competitivo recibió una sola oferta. Es un indicador de riesgo, no una "
            "conclusión: algunos proveedores son distribuidores exclusivos legítimos."
        ),
        scope=(
            "Procesos competitivos con número de oferentes informado; se excluyen los métodos y "
            "categorías donde todos los procesos tienen un solo oferente por diseño"
        ),
        fields=("processes.method_group", "processes.n_tenderers"),
        threshold_rule_es="Número de oferentes igual a 1.",
    ),
    SignalDefinition(
        code=SHORT_TENDER_WINDOW,
        label_es="Plazo de ofertas atípicamente corto",
        description_es=(
            "El plazo entre la apertura y el cierre de ofertas es menor al percentil 5 de los "
            "procesos del mismo método y año."
        ),
        scope="Procesos competitivos con fecha de inicio y de cierre de ofertas",
        fields=("processes.tender_start", "processes.tender_end", "processes.method", "processes.year"),
        threshold_rule_es="Plazo en días menor al percentil 5 del método y año (mínimo 30 procesos).",
        statistical=True,
    ),
    SignalDefinition(
        code=LOW_SAVING,
        label_es="Ahorro atípicamente bajo",
        description_es=(
            "El monto adjudicado es casi igual al presupuesto referencial, en el extremo superior "
            "de la distribución del mismo método y año."
        ),
        scope="Procesos competitivos con presupuesto y monto adjudicado",
        fields=("processes.award_total", "processes.budget", "processes.method", "processes.year"),
        threshold_rule_es=(
            "Adjudicado / presupuesto mayor o igual al percentil 95 del método y año, y al menos "
            "0,99. No se evalúa en métodos y años donde más del 10 % de los procesos ya está en ese nivel."
        ),
        statistical=True,
    ),
    SignalDefinition(
        code=NEW_SUPPLIER,
        label_es="Proveedor de reciente creación",
        description_es=(
            "El proveedor adjudicado inició actividades en el SRI menos de 180 días antes de la "
            "primera adjudicación."
        ),
        scope=(
            "Procesos no de catálogo cuyo ganador es una empresa o entidad pública "
            "y figura en el registro del SRI"
        ),
        fields=("suppliers_sri.activity_start_date", "processes.first_award_date", "awards.supplier_ruc"),
        threshold_rule_es=(
            "Entre 0 y 179 días entre el inicio de actividades (desde 1900) y la primera adjudicación."
        ),
        required_tables=("suppliers_sri",),
    ),
    SignalDefinition(
        code=SUPPLIER_NOT_ACTIVE,
        label_es="Proveedor no activo en el SRI",
        description_es=(
            "El estado actual del proveedor en el SRI no es activo. Es el estado vigente, no el que "
            "tenía al momento de la adjudicación."
        ),
        scope=(
            "Procesos no de catálogo cuyo ganador es una empresa o entidad pública "
            "y figura en el registro del SRI"
        ),
        fields=("suppliers_sri.status", "awards.supplier_ruc"),
        threshold_rule_es="Estado del SRI distinto de ACTIVO.",
        required_tables=("suppliers_sri",),
    ),
    SignalDefinition(
        code=GHOST_COMPANY_LIST,
        label_es="Proveedor ya incluido en el listado del SRI al momento del proceso",
        description_es=(
            "El RUC del proveedor adjudicado aparece en el listado publicado por el SRI (catastro de "
            "contribuyentes calificados con transacciones inexistentes) y la fecha de notificación es "
            "anterior o igual a la fecha del proceso. Un listado es un hecho de registro, no una "
            "conclusión sobre el contrato; la calificación puede haber sido impugnada."
        ),
        scope=(
            "Procesos cuyo proveedor adjudicado es una empresa o entidad pública "
            "(no se publica información de listados sobre personas naturales)"
        ),
        fields=("ghost_companies.ruc", "ghost_companies.notification_date", "awards.supplier_ruc"),
        threshold_rule_es=(
            "El RUC del ganador está en el listado y la notificación es anterior o igual al proceso."
        ),
        required_tables=("ghost_companies",),
    ),
    SignalDefinition(
        code=GHOST_COMPANY_LISTED_LATER,
        label_es="Proveedor que aparece en el listado del SRI con fecha posterior o sin fecha",
        description_es=(
            "El RUC del proveedor adjudicado aparece en el listado publicado por el SRI, pero la "
            "notificación es posterior a la fecha del proceso o no tiene fecha. Es información de "
            "contexto: la entidad contratante no pudo conocer el listado al momento del proceso. No "
            "suma puntos al puntaje de riesgo."
        ),
        scope=(
            "Procesos cuyo proveedor adjudicado es una empresa o entidad pública "
            "(no se publica información de listados sobre personas naturales)"
        ),
        fields=("ghost_companies.ruc", "ghost_companies.notification_date", "awards.supplier_ruc"),
        threshold_rule_es=(
            "El RUC del ganador está en el listado y la notificación es posterior "
            "al proceso o no tiene fecha."
        ),
        required_tables=("ghost_companies",),
        kind=KIND_CONTEXT,
    ),
    SignalDefinition(
        code=BUYER_CONCENTRATION,
        label_es="Concentración de adjudicaciones en un proveedor",
        description_es=(
            "El proveedor recibió al menos el 30 % del monto adjudicado por la entidad contratante en el "
            "año, acumulado en varios procesos (ningún proceso por sí solo alcanza ese 30 %)."
        ),
        scope="Procesos no de catálogo con monto adjudicado por proveedor",
        fields=("awards.amount", "awards.supplier_ruc", "processes.buyer_ruc", "processes.year"),
        threshold_rule_es=(
            "Participación del proveedor mayor o igual a 30 % del total adjudicado de la entidad en el "
            "año, con total de la entidad-año de al menos USD 100.000, al menos 3 procesos adjudicados y "
            "ningún proceso individual del proveedor igual o mayor al 30 % del total."
        ),
    ),
    SignalDefinition(
        code=REPEATED_DIRECT_AWARDS,
        label_es="Adjudicaciones directas repetidas",
        description_es=(
            "La misma entidad adjudicó de forma directa al mismo proveedor, en el mismo tipo de bien o "
            "servicio, tres o más veces en un lapso de 90 días."
        ),
        scope="Procesos de contratación directa",
        fields=(
            "processes.buyer_ruc",
            "processes.main_cpc",
            "processes.first_award_date",
            "awards.supplier_ruc",
        ),
        threshold_rule_es=(
            "Al menos 3 procesos directos de la misma entidad, el mismo proveedor y el mismo prefijo "
            "CPC de 5 dígitos dentro de una ventana de 90 días."
        ),
    ),
    SignalDefinition(
        code=RECURRING_COBIDDERS,
        label_es="Oferentes que coinciden repetidamente",
        description_es=(
            "El ganador y un mismo oferente perdedor coincidieron en al menos 5 procesos competitivos "
            "de la misma entidad."
        ),
        scope="Procesos competitivos con oferentes registrados",
        fields=("tenderers.supplier_ruc", "awards.supplier_ruc", "processes.buyer_ruc"),
        threshold_rule_es=(
            "5 o más procesos competitivos de la misma entidad con el mismo par ganador-perdedor."
        ),
    ),
    SignalDefinition(
        code=CONTRACT_VS_COMPANY_SIZE,
        label_es="Contrato desproporcionado frente a los ingresos del año anterior de la empresa",
        description_es=(
            "El monto adjudicado supera tres veces los ingresos por ventas del último año reportado "
            "a la Superintendencia de Compañías anterior al año de la adjudicación."
        ),
        scope="Procesos no de catálogo cuyo ganador tiene ingresos reportados de un año anterior",
        fields=("company_financials.revenue", "company_financials.year", "processes.award_total"),
        threshold_rule_es=(
            "Monto adjudicado mayor a 3 veces los ingresos por ventas positivos del último año "
            "anterior al año de la adjudicación."
        ),
        required_tables=("company_financials",),
    ),
    SignalDefinition(
        code=CONTRACT_VS_COMPANY_SIZE_SAME_YEAR,
        label_es="Contrato desproporcionado frente a los ingresos del mismo año (menor confianza)",
        description_es=(
            "El monto adjudicado supera tres veces los ingresos por ventas del año de la adjudicación, "
            "sin que exista un año anterior reportado. Es información de contexto de menor confianza: "
            "los ingresos del mismo año pueden incluir el propio contrato. No suma puntos."
        ),
        scope=(
            "Procesos no de catálogo cuyo ganador solo tiene ingresos reportados del año de la adjudicación"
        ),
        fields=("company_financials.revenue", "company_financials.year", "processes.award_total"),
        threshold_rule_es=(
            "Monto adjudicado mayor a 3 veces los ingresos positivos del año de la adjudicación."
        ),
        required_tables=("company_financials",),
        kind=KIND_CONTEXT,
    ),
)

SIGNALS_BY_CODE: dict[str, SignalDefinition] = {s.code: s for s in SIGNALS}


def get_signal(code: str) -> SignalDefinition:
    try:
        return SIGNALS_BY_CODE[code]
    except KeyError as exc:
        raise KeyError(f"Unknown signal code: {code}") from exc


CONTEXT_CODES: frozenset[str] = frozenset(s.code for s in SIGNALS if s.is_context)
RISK_CODES: tuple[str, ...] = tuple(s.code for s in SIGNALS if not s.is_context)
