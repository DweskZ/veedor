# ruff: noqa: E501
"""`GET /processes/{ocid}/provenance`: where each fact of the process page comes from.

Every fact the process detail endpoint returns has an entry in `domain.provenance.catalog`; this module
adds what only the process knows: the value (masked exactly as the detail endpoint masks it), the OCDS path
the budget really came from (`budget_source`), the signals that fired and the registry rows of the winner.
Every lake read is a single ``SELECT ... WHERE key = ?``.
"""

from __future__ import annotations

import re
from typing import Any

from veedor.domain.dossier import source_catalog as sc
from veedor.domain.masking import COMPANY, PUBLIC_ENTITY, is_masked_party, kind_from_ruc
from veedor.domain.provenance import catalog
from veedor.domain.signals import SIGNALS_BY_CODE
from veedor.schemas.processes import ProcessDetail
from veedor.use_cases.queries import processes as process_queries
from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort

MAX_LIST_VALUES = 25
MAX_SIGNAL_INPUTS = 8
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_FIRST_PLAUSIBLE_YEAR = 1900

BUDGET_PATHS: dict[str | None, tuple[str, bool, str]] = {
    "tender.value": (
        "tender.value.amount",
        False,
        "Se usa el valor del proceso (tender.value). Orden de prioridad: tender.value, suma de lotes, planning.budget.",
    ),
    "tender.lots": (
        "tender.lots[].value.amount",
        True,
        "El proceso no publica tender.value: Veedor suma los valores de sus lotes (tender.lots[].value.amount). "
        "Orden de prioridad: tender.value, suma de lotes, planning.budget.",
    ),
    "planning.budget": (
        "planning.budget.amount.amount",
        False,
        "El proceso no publica tender.value ni valores por lote: se usa el presupuesto de planificación "
        "(planning.budget.amount.amount). Orden de prioridad: tender.value, suma de lotes, planning.budget.",
    ),
    None: (
        "tender.value.amount; tender.lots[].value.amount; planning.budget.amount.amount",
        False,
        "El proceso no publica ninguno de los tres campos de presupuesto, por eso el valor no está disponible.",
    ),
}

_CACHE = VersionedCache(max_entries=1_024)


def get_process_provenance(lake: LakePort, ocid: str, investigation: Any | None = None) -> dict[str, Any]:
    """`investigation` is the stored record (or None); only its finished date and fact ids are read."""
    stamp = getattr(investigation, "finished_at", None) if investigation is not None else None
    key = (ocid, stamp, tuple(getattr(investigation, "facts_added", ()) or ()))
    return _CACHE.get_or_compute(key, lake.data_version(), lambda: _compute(lake, ocid, investigation))


class _Builder:
    def __init__(self, ocid: str, process_code: str | None, ruc: str | None) -> None:
        self.ocid = ocid
        self.process_code = process_code or "sin código publicado"
        self.ruc = ruc
        self.facts: list[dict[str, Any]] = []
        self.source_order: list[str] = []

    def _verify(self, text: str) -> str:
        text = text.replace("{process_code}", self.process_code).replace("{ocid}", self.ocid)
        return text.replace("{ruc}", self.ruc or "del adjudicatario")

    def add(
        self,
        key: str,
        spec: catalog.FactSpec,
        value: Any,
        *,
        source_field: str | None = None,
        derived: bool | None = None,
        derivation: str | None = None,
        label: str | None = None,
        verify: str | None = None,
    ) -> None:
        if spec.source_id not in self.source_order:
            self.source_order.append(spec.source_id)
        self.facts.append(
            {
                "key": key,
                "label_es": label or spec.label_es,
                "value": value,
                "source_id": spec.source_id,
                "source_field": source_field or spec.source_field,
                "derived": spec.derived if derived is None else derived,
                "derivation_es": derivation if derivation is not None else spec.derivation_es,
                "verify_es": self._verify(verify or spec.verify_es),
            }
        )


def _compute(lake: LakePort, ocid: str, investigation: Any | None) -> dict[str, Any]:
    raw = process_queries.get_process(lake, ocid)  # raises NotFoundError for an unknown process
    detail = ProcessDetail.model_validate(raw)  # the same masking as the detail endpoint
    raw_facts = raw.get("facts") or {}
    winner_raw = raw.get("winner") or {}
    registry_ruc = _registry_ruc(winner_raw)
    builder = _Builder(ocid, raw_facts.get("process_code"), registry_ruc)
    _process_facts(builder, detail, raw_facts)
    _score_facts(builder, detail)
    _signal_facts(builder, detail)
    _party_facts(builder, detail)
    if registry_ruc:
        _registry_facts(builder, lake, registry_ruc)
    if investigation is not None:
        _investigation_facts(builder, investigation)
    return {
        "ocid": ocid,
        "sources": _sources(builder.source_order, lake, investigation),
        "facts": builder.facts,
    }


def _process_facts(builder: _Builder, detail: ProcessDetail, raw_facts: dict[str, Any]) -> None:
    if detail.facts is None:
        return
    values = detail.facts.model_dump()
    for field, value in values.items():
        key = f"facts.{field}"
        spec = catalog.FACTS[key]
        if field == "budget":
            path, derived, derivation = BUDGET_PATHS.get(raw_facts.get("budget_source"), BUDGET_PATHS[None])
            builder.add(key, spec, value, source_field=path, derived=derived, derivation=derivation)
        else:
            builder.add(key, spec, value)


def _score_facts(builder: _Builder, detail: ProcessDetail) -> None:
    if detail.score is None:
        return
    for field, value in detail.score.model_dump().items():
        builder.add(f"score.{field}", catalog.FACTS[f"score.{field}"], value)


def _signal_inputs(evidence: dict[str, Any]) -> str:
    """Numbers, flags and dates of the evidence as ``name = value``; strings (names, RUCs) never."""
    parts = []
    for name, value in evidence.items():
        if not (isinstance(name, str) and _KEY.match(name)):
            continue
        if isinstance(value, bool) or isinstance(value, int | float):
            parts.append(f"{name} = {value}")
        elif isinstance(value, str) and _ISO_DAY.match(value):
            parts.append(f"{name} = {value[:10]}")
        if len(parts) == MAX_SIGNAL_INPUTS:
            break
    return "; ".join(parts)


def _signal_facts(builder: _Builder, detail: ProcessDetail) -> None:
    for signal in detail.signals:
        definition = SIGNALS_BY_CODE.get(signal.code)
        if definition is None:
            continue
        spec = catalog.FactSpec(
            definition.label_es,
            "veedor_indicators",
            catalog.signal_source_field(signal.code),
            True,
            None,
            catalog.signal_verify(signal.code),
        )
        observed = f"Valor observado: {signal.value}; umbral: {signal.threshold}."
        inputs = _signal_inputs(signal.evidence)
        derivation = f"Regla: {definition.threshold_rule_es} {observed}" + (
            f" Entradas: {inputs}." if inputs else ""
        )
        builder.add(f"signal.{signal.code}", spec, signal.value, derivation=derivation)


def _listed(values: list[Any]) -> list[Any]:
    return values[:MAX_LIST_VALUES]


def _party_facts(builder: _Builder, detail: ProcessDetail) -> None:
    if detail.winner is not None:
        for field, value in detail.winner.model_dump().items():
            builder.add(f"winner.{field}", catalog.FACTS[f"winner.{field}"], value)
    if detail.tenderers:
        for field in ("ruc", "name", "kind"):
            values = _listed([getattr(t, field) for t in detail.tenderers])
            builder.add(f"tenderers.{field}", catalog.FACTS[f"tenderers.{field}"], values)
    if detail.awards:
        for field in ("award_id", "award_date", "supplier_ruc", "supplier_name", "amount"):
            values = _listed([getattr(a, field) for a in detail.awards])
            builder.add(f"awards.{field}", catalog.FACTS[f"awards.{field}"], values)


def _registry_ruc(winner: dict[str, Any]) -> str | None:
    """The winner's RUC when it is a company or a public entity; natural persons are never looked up."""
    ruc, name, kind = winner.get("ruc"), winner.get("name"), winner.get("kind")
    if not isinstance(ruc, str) or kind_from_ruc(ruc) not in (COMPANY, PUBLIC_ENTITY) or len(ruc) != 13:
        return None
    return None if is_masked_party(ruc, name, kind) else ruc


def _first(lake: LakePort, table: str, sql: str, ruc: str) -> dict[str, Any] | None:
    if not lake.has_table(table):
        return None
    rows = lake.fetch(sql, [ruc], tables=(table,))
    return rows[0] if rows else None


def _plausible_day(value: Any) -> str | None:
    text = str(value)[:10] if value else ""
    return text if _ISO_DAY.match(text) and int(text[:4]) >= _FIRST_PLAUSIBLE_YEAR else None


def _registry_facts(builder: _Builder, lake: LakePort, ruc: str) -> None:
    sri = _first(
        lake,
        "suppliers_sri",
        "SELECT * FROM suppliers_sri WHERE ruc = ? LIMIT 1",
        ruc,
    )
    if sri is not None:
        file = sri.get("source_file") or "SRI_RUC_<provincia>.zip"
        for key, value in (
            ("registry.sri_status", sri.get("status")),
            ("registry.sri_activity_start", _plausible_day(sri.get("activity_start_date"))),
            ("registry.sri_taxpayer_type", sri.get("taxpayer_type")),
        ):
            _, spec = catalog.REGISTRY_FACTS[key]
            builder.add(key, spec, value, source_field=spec.source_field.replace("{sri_file}", str(file)))
    if lake.has_table("ghost_companies"):
        hit = _first(
            lake, "ghost_companies", "SELECT 1 AS hit FROM ghost_companies WHERE ruc = ? LIMIT 1", ruc
        )
        builder.add(
            "registry.sri_ghost_listed",
            catalog.REGISTRY_FACTS["registry.sri_ghost_listed"][1],
            hit is not None,
        )
    company = _first(
        lake, "companies_supercias", "SELECT company_type FROM companies_supercias WHERE ruc = ? LIMIT 1", ruc
    )
    if company is not None:
        builder.add(
            "registry.supercias_company_type",
            catalog.REGISTRY_FACTS["registry.supercias_company_type"][1],
            company.get("company_type"),
        )
    revenue = _first(
        lake,
        "company_financials",
        "SELECT year, revenue FROM company_financials WHERE ruc = ? AND revenue IS NOT NULL "
        "ORDER BY year DESC LIMIT 1",
        ruc,
    )
    if revenue is not None:
        builder.add(
            "registry.supercias_revenue_latest",
            catalog.REGISTRY_FACTS["registry.supercias_revenue_latest"][1],
            revenue.get("revenue"),
        )
        builder.add(
            "registry.supercias_revenue_year",
            catalog.REGISTRY_FACTS["registry.supercias_revenue_year"][1],
            revenue.get("year"),
        )


_INVESTIGATION_VERIFY = {
    "investigation.company": "Consulte el RUC {ruc} en el directorio de compañías de la Superintendencia de Compañías.",
    "investigation.financials": "Consulte el RUC {ruc} en los estados financieros de la Superintendencia de Compañías.",
    "investigation.tax": "Consulte el RUC {ruc} en la consulta pública de RUC del SRI.",
    "investigation.pair": "Busque en los datos abiertos de SERCOP las adjudicaciones de la entidad al RUC {ruc}.",
    "investigation.similar": "Compare con los procesos de la misma entidad listados en «Procesos similares».",
    "investigation.audit": "Busque a la entidad compradora en los informes aprobados de la Contraloría General del Estado.",
    "investigation.run": "La bitácora completa está en la sección «Investigación realizada» del expediente.",
}
_INVESTIGATION_DERIVED = frozenset({"pair", "similar", "audit", "run"})


def _investigation_facts(builder: _Builder, investigation: Any) -> None:
    known = catalog.investigation_catalogue()
    for fact_id in getattr(investigation, "facts_added", ()) or ():
        if fact_id not in known:
            continue
        source_key, label = known[fact_id]
        tool, field = catalog.investigation_tool(fact_id)
        prefix = ".".join(fact_id.split(".")[:2])
        spec = catalog.FactSpec(
            label,
            source_key if source_key in catalog.SOURCES else "veedor_indicators",
            f"{tool}: {field}",
            fact_id.split(".")[1] in _INVESTIGATION_DERIVED,
            "El valor figura en la sección «Investigación realizada» del expediente de este proceso; "
            "la consulta se hizo con herramientas de solo lectura.",
            _INVESTIGATION_VERIFY[prefix],
        )
        builder.add(fact_id, spec, None)


def _sources(order: list[str], lake: LakePort, investigation: Any | None) -> list[dict[str, Any]]:
    built = (lake.built_at() or "")[:10] or sc.RETRIEVED_AT
    finished = str(getattr(investigation, "finished_at", "") or "")[:10] or None
    out = []
    for source_id in order:
        info = catalog.SOURCES[source_id]
        if source_id in catalog.DERIVED_SOURCES:
            retrieved = built
        elif source_id in catalog.LIVE_SOURCES:
            retrieved = finished
        else:
            retrieved = sc.RETRIEVED_AT
        out.append(
            {
                "id": info.id,
                "name": info.name,
                "publisher": info.publisher,
                "licence": info.licence,
                "retrieved_at": retrieved,
                "url": info.url,
            }
        )
    return out
