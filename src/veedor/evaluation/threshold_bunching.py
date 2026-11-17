"""Bunching of budgets just below verified thresholds: yearly, pooled, by buyer type (docs/VALIDATION.md).

Aggregates only. A buyer type is a coarse keyword class of the buyer name; names are never output.
"""

# ruff: noqa: E501 - long Markdown table strings

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from veedor.domain import thresholds as th
from veedor.domain.bunching import BunchingSpec, estimate_bunching
from veedor.domain.text_match import fold
from veedor.infrastructure.lake import threshold_context as tc

BUYER_TYPES = (
    ("provincial_or_parish_government", ("PROVINCIAL", "PARROQUIAL", "PREFECTURA")),
    ("municipal_government", ("MUNICIPAL", "MUNICIPIO")),
    ("university", ("UNIVERSIDAD", "ESCUELA POLITECNICA")),
    ("health", ("HOSPITAL", "SALUD", "CLINICA")),
)
OTHER = "other"
POOLED_BOOT = 300
ROBUST_SPECS = {
    "degree_5": BunchingSpec(degree=5),
    "window_30": BunchingSpec(window=0.30),
}


def buyer_type(name: object) -> str:
    text = fold(str(name or "")).upper()
    for label, keywords in BUYER_TYPES:
        if any(k in text for k in keywords):
            return label
    return OTHER


def _pooled(
    data: dict[str, np.ndarray],
    rule: th.Threshold,
    years: list[int],
    seed: int,
    amount: str = "budget",
    types: str | None = None,
) -> dict[str, Any]:
    rel_parts, buyers, kinds = [], [], []
    for t in (x for x in th.all_thresholds() if x.code == rule.code and x.year in years):
        mask = tc.select(data, t)
        vals = data[amount][mask]
        keep = ~np.isnan(vals) & (vals > 0)
        rel_parts.append(vals[keep] / t.value_usd - 1.0)
        buyers.append(data["buyer"][mask][keep])
        kinds.append(np.asarray([buyer_type(n) for n in data["buyer_name"][mask][keep]]))
    if not rel_parts:
        return {"n_window": 0, "status": "insufficient_data"}
    rel, who, kind = np.concatenate(rel_parts), np.concatenate(buyers), np.concatenate(kinds)
    if types is not None:
        sel = kind == types
        rel, who = rel[sel], who[sel]
    out = estimate_bunching(rel, who, BunchingSpec(), POOLED_BOOT, seed)
    if out["status"] == "estimated" and types is None and amount == "budget":
        out["robustness"] = {
            name: {
                k: v
                for k, v in estimate_bunching(rel, who, spec, 100, seed).items()
                if k in ("n_window", "excess_bins", "excess_pct", "status")
            }
            for name, spec in ROBUST_SPECS.items()
        }
    return out


def run_bunching(lake_dir: Path, seed: int) -> dict[str, Any]:
    all_rules = th.all_thresholds()
    years = sorted({t.year for t in all_rules})
    data = tc.load_budgets(lake_dir, years)
    pie_years = [y for y in years if th.YEARS[y].regime == th.PIE_REGIME]
    yearly = tc.build_rows(lake_dir, n_boot=500, seed=seed)
    rules = [t for t in all_rules if t.year == pie_years[0] and t.analysable]
    pooled = []
    for rule in rules:
        entry: dict[str, Any] = {
            "threshold_code": rule.code,
            "category": rule.category,
            "years": pie_years,
            "budget": _pooled(data, rule, pie_years, seed),
            "award_amount": _pooled(data, rule, pie_years, seed, amount="award_total"),
            "by_buyer_type": {
                kind: _pooled(data, rule, pie_years, seed, types=kind)
                for kind, _ in (*BUYER_TYPES, (OTHER, ()))
            },
        }
        pooled.append(entry)
    n_proc = int(len(data["year"]))
    return {
        "spec": {
            "window": 0.20,
            "bin_width": 0.01,
            "zone": 0.05,
            "degree": 3,
            "min_window_count": 200,
            "n_boot_yearly": 500,
            "n_boot_pooled": POOLED_BOOT,
            "seed": seed,
        },
        "verified_years": years,
        "excluded_years": {str(y): why for y, why in th.EXCLUDED_YEARS.items()},
        "unverified_years": [y for y in range(2015, 2027) if y not in years and y not in th.EXCLUDED_YEARS],
        "n_competitive_processes_in_verified_years": n_proc,
        "yearly": yearly,
        "pooled": pooled,
        "data_notes": [
            "The amount that decides the procedure is the budget (presupuesto referencial), which the lake "
            "has for 100 % of competitive processes; award amounts are a secondary view.",
            "Ínfima cuantía procedures are not in the lake (no such method; competitive budgets start above "
            "it), so the lowest threshold cannot be analysed for bunching, only counted just above.",
            "From the 2025 reform the thresholds are fixed at USD 10,000 and the procedures below "
            "(ínfima cuantía) are absent from the lake: 2026 cannot be analysed for bunching.",
        ],
    }


def _fmt_est(e: dict[str, Any]) -> str:
    if e.get("status") != "estimated":
        return f"{e.get('n_window', 0):,} | {e.get('status', 'n/a').replace('_', ' ')} | n/a | n/a |"
    lo, hi = e["excess_bins_ci"]
    return (
        f"{e['n_window']:,} | {e['excess_bins']:+.2f} ({lo:+.2f} to {hi:+.2f}) | "
        f"{e['excess_pct']:+.1f} % | {e['missing_above_pct']:+.1f} % |"
    )


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "",
        "## Threshold bunching (generated)",
        "",
        "Budgets within 20 % of each verified threshold, bins of 1 % of the threshold, a degree-3 "
        "counterfactual fitted outside the 5 % zone on each side, buyer-cluster bootstrap. 'Excess (bins)' is "
        "the observed minus counterfactual mass in the 5 % just below the threshold, in units of one "
        "counterfactual bin; 'excess %' is relative to the counterfactual; 'missing above' is the "
        "same comparison in the 5 % just above (positive = fewer processes than the counterfactual). This "
        "describes the distribution of budgets; it does not say why purchases sit where they do.",
        "",
        f"Verified years analysed: {', '.join(map(str, result['verified_years']))}. "
        f"Excluded: {'; '.join(f'{y}: {w.rstrip(".")}' for y, w in result['excluded_years'].items())}. "
        f"Unverified: {result['unverified_years'] or 'none'}.",
        "",
        *[f"- {n}" for n in result["data_notes"]],
        "",
        "### Pooled over the years with coefficient thresholds (budget)",
        "",
        "| Threshold | n in window | Excess (bins), 95 % CI | Excess % | Missing above % | Degree 5: excess bins | Window 30 %: excess bins |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in result["pooled"]:
        b = p["budget"]
        rob = b.get("robustness", {})
        r5 = rob.get("degree_5", {}).get("excess_bins")
        r30 = rob.get("window_30", {}).get("excess_bins")
        lines.append(
            f"| `{p['threshold_code']}` | {_fmt_est(b)} {'n/a' if r5 is None else f'{r5:+.2f}'} | "
            f"{'n/a' if r30 is None else f'{r30:+.2f}'} |"
        )
    lines += [
        "",
        "Same, on the award amount (secondary view):",
        "",
        "| Threshold | n in window | Excess (bins), 95 % CI | Excess % | Missing above % |",
        "|---|---|---|---|---|",
    ]
    for p in result["pooled"]:
        lines.append(f"| `{p['threshold_code']}` | {_fmt_est(p['award_amount'])}")
    lines += [
        "",
        "### By buyer type (pooled, budget)",
        "",
        "| Threshold | Buyer type | n in window | Excess (bins), 95 % CI | Excess % | Missing above % |",
        "|---|---|---|---|---|---|",
    ]
    for p in result["pooled"]:
        for kind, e in p["by_buyer_type"].items():
            lines.append(f"| `{p['threshold_code']}` | {kind.replace('_', ' ')} | {_fmt_est(e)}")
    lines += [
        "",
        "### By year (budget)",
        "",
        "| Year | Threshold | USD | n in window | Excess (bins), 95 % CI | Excess % | Missing above % | Counts below / above (5 % bands) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in result["yearly"]:
        if r["status"] == "not_analysable":
            est = f"{r['n_window']:,} | not analysable | n/a | n/a |"
        elif r["status"] != "estimated":
            est = f"{r['n_window']:,} | {r['status'].replace('_', ' ')} | n/a | n/a |"
        else:
            est = (
                f"{r['n_window']:,} | {r['excess_bins']:+.2f} ({r['excess_bins_low']:+.2f} to "
                f"{r['excess_bins_high']:+.2f}) | {r['excess_pct']:+.1f} % | {r['missing_above_pct']:+.1f} % |"
            )
        lines.append(
            f"| {r['year']} | `{r['threshold_code']}` | {r['threshold_usd']:,.2f} | {est} "
            f"{r['n_band_below']:,} / {r['n_band_above']:,} |"
        )
    return "\n".join(lines) + "\n"
