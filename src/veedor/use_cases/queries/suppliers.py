"""Supplier profile, registry facts and recent processes."""

from __future__ import annotations

from typing import Any

from veedor.domain.masking import NATURAL_PERSON, kind_from_ruc
from veedor.use_cases.queries.ports import LakePort, NotFoundError, Row

RECENT_LIMIT = 10
FINANCIAL_YEARS = 10


def _rows(lake: LakePort, table: str, sql: str, ruc: str, limit: int | None = None) -> list[Row] | None:
    """Rows for `ruc`, or None when the dataset is not available."""
    if not lake.has_table(table):
        return None
    params = [ruc] if limit is None else [ruc, limit]
    return lake.fetch(sql, params, tables=(table,))


def get_supplier(lake: LakePort, ruc: str) -> dict[str, Any]:
    if kind_from_ruc(ruc) == NATURAL_PERSON:
        # Same answer as for an unknown RUC: no confirmation that a natural person exists in the data.
        raise NotFoundError("supplier", ruc)
    profiles = lake.fetch(
        "SELECT * FROM supplier_profiles WHERE ruc = ?", [ruc], tables=("supplier_profiles",)
    )
    sri = _rows(lake, "suppliers_sri", "SELECT * FROM suppliers_sri WHERE ruc = ? LIMIT 1", ruc)
    supercias = _rows(
        lake, "companies_supercias", "SELECT * FROM companies_supercias WHERE ruc = ? LIMIT 1", ruc
    )
    ghost = _rows(lake, "ghost_companies", "SELECT ruc FROM ghost_companies WHERE ruc = ? LIMIT 1", ruc)
    financials = _rows(
        lake,
        "company_financials",
        "SELECT * FROM company_financials WHERE ruc = ? ORDER BY year DESC LIMIT ?",
        ruc,
        FINANCIAL_YEARS,
    )
    if not profiles and not sri and not supercias:
        raise NotFoundError("supplier", ruc)
    recent = lake.fetch(
        "SELECT * FROM process_scores WHERE winner_ruc = ? "
        "ORDER BY year DESC NULLS LAST, risk_score DESC, ocid LIMIT ?",
        [ruc, RECENT_LIMIT],
        tables=("process_scores",),
    )
    if profiles:
        profile = profiles[0]
    else:
        fallback = (sri or supercias or [{}])[0]
        profile = {"ruc": ruc, "name": fallback.get("legal_name")}
    return {
        "profile": profile,
        "registry": {
            "sri": sri[0] if sri else None,
            "ghost_company_listed": None if ghost is None else bool(ghost),
            "supercias": supercias[0] if supercias else None,
            "financials": financials or [],
        },
        "recent_processes": recent,
    }
