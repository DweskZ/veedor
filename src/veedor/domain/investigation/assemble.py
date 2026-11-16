"""Fold specialist findings and the tool log into the evidence pack (pure)."""

from __future__ import annotations

from datetime import date
from typing import Any

from veedor.domain.dossier import source_catalog as catalog
from veedor.domain.dossier.investigation_facts import applicable_specs
from veedor.domain.dossier.models import (
    EvidencePack,
    InvestigationFacts,
    LookupSummary,
    SpecialistSummary,
)
from veedor.domain.investigation.models import SpecialistRun, ToolCall
from veedor.domain.investigation.vocab import SOURCE_BY_TOOL

FINDING_KEYS = ("company", "financials", "tax_registry", "pair_history", "similar", "audit", "enquiries")
_SPECIALIST_OF_FACT = (
    ("investigation.company", "company"),
    ("investigation.financials", "company"),
    ("investigation.tax", "tax_registry"),
    ("investigation.pair", "history"),
    ("investigation.similar", "history"),
    ("investigation.audit", "audit"),
    ("investigation.enquiries", "enquiries"),
)


def specialist_of_fact(fact_id: str) -> str | None:
    return next((name for prefix, name in _SPECIALIST_OF_FACT if fact_id.startswith(prefix)), None)


def summarise_lookups(log: list[ToolCall]) -> list[LookupSummary]:
    """One line per consulted source: ok if any call succeeded, else the last outcome; attempts summed."""
    grouped: dict[str, list[ToolCall]] = {}
    for call in log:
        source = SOURCE_BY_TOOL.get(call.tool)
        if source is not None:
            grouped.setdefault(source, []).append(call)
    out = []
    for source, calls in grouped.items():
        ok = [c for c in calls if c.outcome == "ok"]
        chosen = ok[-1] if ok else calls[-1]
        executed = [c for c in calls if c.outcome != "skipped"]
        out.append(
            LookupSummary(
                source=source,
                outcome=chosen.outcome,
                reason=next((c.reason for c in reversed(calls) if c.reason == "out_of_range"), chosen.reason),
                calls=max(1, len(executed)),
                retries=sum(max(0, c.attempts - 1) for c in executed),
            )
        )
    return out


def summarise_specialists(runs: list[SpecialistRun]) -> list[SpecialistSummary]:
    order: dict[str, SpecialistSummary] = {}
    for run in runs:
        item = order.setdefault(
            run.specialist, SpecialistSummary(specialist=run.specialist, n_tool_calls=0, dispatches=0)
        )
        item.n_tool_calls += run.n_tool_calls
        item.dispatches += 1
    return list(order.values())


def assemble(
    pack: EvidencePack,
    findings: dict[str, Any],
    log: list[ToolCall],
    runs: list[SpecialistRun],
    today: date,
) -> EvidencePack:
    """The pack with its `investigation` block and the sources of every fact that now applies."""
    facts = InvestigationFacts(
        **{key: findings[key] for key in FINDING_KEYS if key in findings},
        specialists=summarise_specialists(runs),
        lookups=summarise_lookups(log),
    )
    with_facts = pack.model_copy(update={"investigation": facts})
    # A source is cited only for facts that carry its data, not for "no disponible" placeholders.
    placeholders = {"unavailable", "not_found", "none"}
    wanted = {
        spec.source_key
        for spec in applicable_specs(with_facts)
        if spec.source_key and spec.id.rsplit(".", 1)[-1] not in placeholders
    }
    record_ids = {
        "supercias_company": pack.winner.ruc if pack.winner else None,
        "supercias_financials": pack.winner.ruc if pack.winner else None,
        "sri_live": pack.winner.ruc if pack.winner else None,
        "sercop_pair_awards": pack.process.ocid,
        "vector_index": pack.process.ocid,
        "contraloria_reports": None,
        "sercop_enquiries": pack.process.ocid,
    }
    sources = list(pack.sources)
    for key in catalog.INVESTIGATION_SOURCES:
        if key in wanted:
            source = catalog.INVESTIGATION_SOURCES[key](record_ids[key])
            sources.append(
                source.model_copy(update={"retrieved_at": source.retrieved_at or today.isoformat()})
            )
    return with_facts.model_copy(update={"sources": sources})


def facts_added(pack: EvidencePack) -> dict[str, list[str]]:
    """Catalogue fact ids contributed by each specialist (the "what was done" facts are not counted)."""
    out: dict[str, list[str]] = {}
    for spec in applicable_specs(pack):
        name = specialist_of_fact(spec.id)
        if name is not None:
            out.setdefault(name, []).append(spec.id)
    return out
