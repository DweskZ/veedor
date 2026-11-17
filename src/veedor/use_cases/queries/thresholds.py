"""Threshold context: verified procedure-amount thresholds, bunching counts and per-process distance.

Context only; never a signal and never part of a score. Reads ``threshold_context`` (built by
``veedor signals thresholds``) and ``processes``. The distance of a budget to the next threshold above
is ``(threshold - budget) / threshold * 100``; ``just_below`` is true when the budget is at or below that
threshold and within ``JUST_BELOW_PCT`` percent of it.
"""

from __future__ import annotations

from typing import Any

from veedor.domain import thresholds as th
from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.ports import LakePort, NotFoundError

JUST_BELOW_PCT = 2.0
BAND_PCT = 5.0
_CACHE = VersionedCache(max_entries=4)

NOTES = [
    "Es contexto, no una señal de riesgo: no cambia ningún puntaje.",
    "Que haya más procesos justo debajo de un umbral describe cómo se distribuyen los presupuestos; no "
    "indica el motivo ni que alguna entidad o proveedor haya hecho algo indebido. Puede deberse a "
    "fraccionamiento o a necesidades reales de compra, y estos datos no permiten distinguirlos.",
    "Los umbrales provienen de publicaciones oficiales del SERCOP; los años que no se pudieron verificar "
    "no se incluyen.",
]
REASONS = {
    "not_competitive_procedure": "El proceso no es de un procedimiento competitivo con umbral por monto.",
    "no_budget": "El proceso no tiene presupuesto referencial en los datos.",
    "year_not_verified": "No hay umbrales verificados para el año del proceso.",
    "category_unknown": "No se puede determinar la categoría (bienes y servicios, obras o consultoría).",
    "no_threshold_for_procedure": "Ningún umbral verificado del año separa el procedimiento de este proceso.",
    "budget_above_all_thresholds": "El presupuesto supera los umbrales verificados del procedimiento.",
}
MART_SQL = (
    "SELECT year, category, threshold_code, procedure_below, procedure_above, coefficient, threshold_usd, "
    "regime, source_url, source_note, verification, analysed, applies_to_methods, n_band_below, "
    "n_band_above, n_window, status, excess_bins, excess_bins_low, excess_bins_high, excess_pct, "
    "missing_above_pct FROM threshold_context ORDER BY year, category, threshold_usd"
)
PROCESS_SQL = "SELECT ocid, year, method, method_group, category, budget FROM processes WHERE ocid = ?"


def _rows(lake: LakePort) -> list[dict[str, Any]]:
    return _CACHE.get_or_compute(
        "rows", lake.data_version(), lambda: lake.fetch(MART_SQL, tables=("threshold_context",))
    )


def get_threshold_stats(lake: LakePort) -> dict[str, Any]:
    items = []
    for r in _rows(lake):
        items.append(
            {
                "year": int(r["year"]),
                "category": r["category"],
                "threshold_code": r["threshold_code"],
                "procedure_below": r["procedure_below"],
                "procedure_above": r["procedure_above"],
                "coefficient": r["coefficient"],
                "threshold_usd": r["threshold_usd"],
                "source_url": r["source_url"],
                "source_note": r["source_note"],
                "verification": r["verification"],
                "n_band_below": int(r["n_band_below"]),
                "n_band_above": int(r["n_band_above"]),
                "bunching": {
                    "status": r["status"],
                    "n_window": int(r["n_window"]),
                    "excess_bins": r["excess_bins"],
                    "excess_bins_ci_low": r["excess_bins_low"],
                    "excess_bins_ci_high": r["excess_bins_high"],
                    "excess_pct": r["excess_pct"],
                    "missing_above_pct": r["missing_above_pct"],
                },
                "caveats": _caveats(r),
            }
        )
    return {
        "items": items,
        "band_pct": BAND_PCT,
        "excluded_years": {str(y): why for y, why in th.EXCLUDED_YEARS.items()},
        "notes": NOTES,
        "data_built_at": lake.built_at(),
    }


def _caveats(row: dict[str, Any]) -> list[str]:
    out = []
    if not row["analysed"]:
        out.append(
            "Los procesos de ínfima cuantía no están en los datos abiertos usados: solo se cuentan los "
            "procesos justo por encima del umbral y no se estima concentración."
        )
    elif row["status"] == "insufficient_data":
        out.append("Datos insuficientes en la ventana (menos de 200 procesos) para estimar.")
    return out


def get_process_threshold(lake: LakePort, ocid: str) -> dict[str, Any]:
    rows = lake.fetch(PROCESS_SQL, [ocid], tables=("processes",))
    if not rows:
        raise NotFoundError("process", ocid)
    p = rows[0]
    base = {
        "ocid": p["ocid"],
        "year": p["year"],
        "budget": p["budget"],
        "band_pct": JUST_BELOW_PCT,
        "applicable": False,
        "reason": None,
        "threshold": None,
        "distance_to_threshold_pct": None,
        "just_below": None,
        "notes": NOTES[:2],
    }
    reason, chosen = _choose(lake, p)
    if chosen is None:
        return base | {"reason": REASONS[reason], "reason_code": reason}
    t, budget = chosen, float(p["budget"])
    distance = (t["threshold_usd"] - budget) / t["threshold_usd"] * 100
    return base | {
        "applicable": True,
        "reason_code": None,
        "threshold": {
            "code": t["threshold_code"],
            "category": t["category"],
            "threshold_usd": t["threshold_usd"],
            "procedure_below": t["procedure_below"],
            "procedure_above": t["procedure_above"],
            "coefficient": t["coefficient"],
            "source_url": t["source_url"],
            "verification": t["verification"],
        },
        "distance_to_threshold_pct": round(distance, 2),
        "just_below": distance <= JUST_BELOW_PCT,
    }


def _choose(lake: LakePort, p: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    if p["method_group"] != "competitive":
        return "not_competitive_procedure", None
    if not p["budget"] or p["budget"] <= 0:
        return "no_budget", None
    category = th.category_of(p["category"], p["method"])
    if category is None:
        return "category_unknown", None
    year_rows = [r for r in _rows(lake) if r["year"] == p["year"]]
    if not year_rows:
        return "year_not_verified", None
    governing = [
        r
        for r in year_rows
        if r["category"] == category and p["method"] in r["applies_to_methods"].split("|")
    ]
    if not governing:
        return "no_threshold_for_procedure", None
    above = sorted(
        (r for r in governing if r["threshold_usd"] >= p["budget"]), key=lambda r: r["threshold_usd"]
    )
    if not above:
        return "budget_above_all_thresholds", None
    return "", above[0]
