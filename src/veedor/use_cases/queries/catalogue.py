"""Signal catalogue lookups."""

from __future__ import annotations

from veedor.domain.signals import SIGNALS, SIGNALS_BY_CODE


def list_signal_catalogue() -> list[dict[str, object]]:
    return [
        {
            "code": s.code,
            "label_es": s.label_es,
            "description_es": s.description_es,
            "scope": s.scope,
            "fields": list(s.fields),
            "threshold_rule_es": s.threshold_rule_es,
            "statistical": s.statistical,
            "needs_registry": s.needs_registry,
            "kind": s.kind,
        }
        for s in SIGNALS
    ]


def signal_kind(code: str) -> str:
    definition = SIGNALS_BY_CODE.get(code)
    return definition.kind if definition else "risk"


def signal_label(code: str) -> str | None:
    definition = SIGNALS_BY_CODE.get(code)
    return definition.label_es if definition else None
