"""Price validation of the risk signals: saving ratio against signal flags (see docs/VALIDATION.md).

The analysis plan lives in docs/VALIDATION.md and is frozen; this module implements it. Outputs are
aggregate numbers only: no process, company or entity identifiers.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import duckdb
import numpy as np

from veedor.domain.signals import definitions as d
from veedor.domain.signals.parameters import (
    MIN_GROUP_SIZE,
    SINGLE_BIDDER_BY_DESIGN_SHARE,
)
from veedor.domain.signals.scoring import SIGNAL_WEIGHTS
from veedor.evaluation import validation_stats as vs

DEFAULT_SEED = 20260101
EXPLORE_YEARS = (2015, 2021)
CONFIRM_YEARS = (2022, 2026)
MIN_FLAGGED = 30
MIN_BUYERS = 10
N_BOOT_MEDIAN = 1000
N_BOOT_SPEARMAN = 300

PRIMARY_FAMILY = (
    d.SINGLE_BIDDER,
    d.SHORT_TENDER_WINDOW,
    d.NEW_SUPPLIER,
    d.SUPPLIER_NOT_ACTIVE,
    d.GHOST_COMPANY_LIST,
    d.RECURRING_COBIDDERS,
)
POST_AWARD = frozenset({d.NEW_SUPPLIER, d.SUPPLIER_NOT_ACTIVE, d.GHOST_COMPANY_LIST, d.RECURRING_COBIDDERS})
CIRCULAR = (d.LOW_SAVING, d.CONTRACT_VS_COMPANY_SIZE, d.BUYER_CONCENTRATION)
PRE_AWARD_COMPOSITE = (d.SINGLE_BIDDER, d.SHORT_TENDER_WINDOW)
ALL_SIGNALS = PRIMARY_FAMILY + CIRCULAR

SAMPLE_SQL = """
WITH comp AS (
  SELECT ocid, year, method, category, budget, award_total, n_tenderers, buyer_ruc, buyer_region,
         main_cpc, TRY_CAST(tender_start AS TIMESTAMPTZ) AS t_start,
         TRY_CAST(tender_end AS TIMESTAMPTZ) AS t_end
  FROM processes WHERE method_group = 'competitive'
),
exempt AS (
  SELECT method, category FROM comp WHERE n_tenderers IS NOT NULL AND method IS NOT NULL
  GROUP BY method, category
  HAVING count(*) >= $min_group AND avg((n_tenderers = 1)::DOUBLE) >= $by_design
),
win_ok AS (
  SELECT method, year FROM comp
  WHERE t_start IS NOT NULL AND t_end IS NOT NULL AND t_end > t_start AND year IS NOT NULL
    AND method IS NOT NULL
  GROUP BY method, year HAVING count(*) >= $min_group
),
others AS (
  SELECT DISTINCT t.ocid FROM tenderers t JOIN process_scores s ON s.ocid = t.ocid
  WHERE t.supplier_ruc IS NOT NULL AND s.winner_ruc IS NOT NULL AND t.supplier_ruc <> s.winner_ruc
),
sig AS (
  SELECT ocid, list(DISTINCT signal_code) AS codes FROM process_signals WHERE kind = 'risk' GROUP BY ocid
)
SELECT c.ocid, c.year, c.method, left(c.main_cpc, 2) AS cpc2, c.buyer_region AS province,
       coalesce(c.buyer_ruc, '<missing>') AS buyer, c.budget, c.award_total,
       (e.method IS NULL AND c.n_tenderers IS NOT NULL) AS ok_single,
       (w.method IS NOT NULL AND c.t_start IS NOT NULL AND c.t_end IS NOT NULL
        AND c.t_end > c.t_start) AS ok_short,
       (s.winner_ruc IS NOT NULL AND length(s.winner_ruc) = 13 AND substr(s.winner_ruc, 3, 1) IN ('9', '6'))
         AS ok_winner,
       (sri.ruc IS NOT NULL) AS in_sri,
       (o.ocid IS NOT NULL) AS ok_cobid,
       coalesce(g.codes, []::VARCHAR[]) AS codes
FROM comp c
JOIN process_scores s USING (ocid)
LEFT JOIN exempt e ON e.method = c.method AND e.category IS NOT DISTINCT FROM c.category
LEFT JOIN win_ok w ON w.method = c.method AND w.year = c.year
LEFT JOIN others o ON o.ocid = c.ocid
LEFT JOIN suppliers_sri sri ON sri.ruc = s.winner_ruc
LEFT JOIN sig g ON g.ocid = c.ocid
WHERE c.budget > 0 AND c.award_total > 0 AND c.year IS NOT NULL AND c.method IS NOT NULL
"""


def plan_sha256(doc_path: Path) -> str | None:
    """Hash of the frozen plan block, so a reader can see it was not edited after the fact."""
    if not doc_path.exists():
        return None
    match = re.search(r"<!-- PLAN:BEGIN -->(.*?)<!-- PLAN:END -->", doc_path.read_text(), re.S)
    return hashlib.sha256(match.group(1).encode()).hexdigest() if match else None


def load_sample(lake_dir: Path, marts_dir: Path) -> dict[str, np.ndarray]:
    """One row per competitive process with budget and award; flags per signal and evaluability."""
    con = duckdb.connect()
    tables = [
        (lake_dir, "processes"),
        (lake_dir, "tenderers"),
        (lake_dir, "suppliers_sri"),
        (marts_dir, "process_scores"),
        (marts_dir, "process_signals"),
    ]
    for directory, name in tables:
        path = directory / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}. Build the lake and the marts first.")
        con.execute(f"CREATE TEMP TABLE {name} AS SELECT * FROM read_parquet($p)", {"p": str(path)})
    rel = con.execute(SAMPLE_SQL, {"min_group": MIN_GROUP_SIZE, "by_design": SINGLE_BIDDER_BY_DESIGN_SHARE})
    cols = [c[0] for c in rel.description]
    rows = rel.fetchall()
    data = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
    return build_arrays(data)


def build_arrays(data: dict[str, list]) -> dict[str, np.ndarray]:
    """Turn query columns into the arrays the analysis uses (also the entry point for tests)."""
    budget = np.asarray(data["budget"], dtype=float)
    award = np.asarray(data["award_total"], dtype=float)
    codes = data["codes"]
    out: dict[str, np.ndarray] = {
        "year": np.asarray(data["year"], dtype=int),
        "saving": 1.0 - award / budget,
        "log_budget": np.log(budget),
        "buyer": np.asarray(data["buyer"]),
        "method_year": vs.codes([f"{m}|{y}" for m, y in zip(data["method"], data["year"], strict=True)]),
        "cpc2": vs.codes(data["cpc2"]),
        "province": vs.codes(data["province"]),
    }
    flags = {c: np.fromiter((c in cs for cs in codes), dtype=bool, count=len(codes)) for c in ALL_SIGNALS}
    ok_winner = np.asarray(data["ok_winner"], dtype=bool)
    in_sri = np.asarray(data["in_sri"], dtype=bool)
    everyone = np.ones(len(budget), dtype=bool)
    evaluable = {
        d.SINGLE_BIDDER: np.asarray(data["ok_single"], dtype=bool),
        d.SHORT_TENDER_WINDOW: np.asarray(data["ok_short"], dtype=bool),
        d.NEW_SUPPLIER: ok_winner & in_sri,
        d.SUPPLIER_NOT_ACTIVE: ok_winner & in_sri,
        d.GHOST_COMPANY_LIST: ok_winner,
        d.RECURRING_COBIDDERS: np.asarray(data["ok_cobid"], dtype=bool),
        d.LOW_SAVING: everyone,
        d.CONTRACT_VS_COMPANY_SIZE: everyone,
        d.BUYER_CONCENTRATION: everyone,
    }
    for code in ALL_SIGNALS:
        out[f"flag_{code}"] = flags[code]
        out[f"eval_{code}"] = evaluable[code]
    return out


def composite(sample: dict[str, np.ndarray], codes: tuple[str, ...]) -> np.ndarray:
    total = np.zeros(len(sample["year"]))
    for code in codes:
        # REPEATED_DIRECT_AWARDS applies to direct procedures only and cannot fire on this sample.
        if f"flag_{code}" in sample:
            total += SIGNAL_WEIGHTS[code] * sample[f"flag_{code}"]
    return np.minimum(total, 100.0)


def period_mask(sample: dict[str, np.ndarray], years: tuple[int, int]) -> np.ndarray:
    return (sample["year"] >= years[0]) & (sample["year"] <= years[1])


def _fe(sample: dict[str, np.ndarray], mask: np.ndarray) -> list[np.ndarray]:
    return [np.unique(sample[k][mask], return_inverse=True)[1] for k in ("method_year", "cpc2", "province")]


def _signal_row(
    sample: dict[str, np.ndarray],
    saving_w: np.ndarray,
    code: str,
    period: np.ndarray,
    n_boot: int,
    seed: int,
) -> dict:
    mask = period & sample[f"eval_{code}"]
    flag = sample[f"flag_{code}"][mask]
    buyers = sample["buyer"][mask]
    row: dict = {
        "signal": code,
        "n_with": int(flag.sum()),
        "n_without": int((~flag).sum()),
        "n_buyers_with": int(len(set(buyers[flag]))),
        "post_award_information": code in POST_AWARD,
        "circular": code in CIRCULAR,
    }
    if row["n_with"] < MIN_FLAGGED or row["n_buyers_with"] < MIN_BUYERS:
        row["status"] = "not_testable"
        return row
    y = sample["saving"][mask]
    row["status"] = "tested"
    row["raw"] = vs.median_difference_cluster_bootstrap(y, flag, buyers, n_boot, seed)
    x = np.column_stack([flag.astype(float), sample["log_budget"][mask]])
    res = vs.fe_cluster_ols(saving_w[mask], x, _fe(sample, mask), buyers, focus=0)
    row["adjusted"] = {
        "effect_pp": 100 * res.coef,
        "ci_low_pp": 100 * res.ci_low,
        "ci_high_pp": 100 * res.ci_high,
        "p_value": res.p_value,
        "n": res.n,
        "n_clusters": res.n_clusters,
    }
    mde = vs.minimum_detectable_effect(res.se)
    row["mde_pp"] = 100 * mde["mde"]
    row["_se"] = res.se
    return row


def _correct(rows: list[dict]) -> None:
    """Holm and BH across the tested members of the primary family; fills the power columns."""
    tested = [r for r in rows if r["status"] == "tested" and r["signal"] in PRIMARY_FAMILY]
    if not tested:
        return
    p = [r["adjusted"]["p_value"] for r in tested]
    for r, h, q in zip(tested, vs.holm(p), vs.benjamini_hochberg(p), strict=True):
        r["adjusted"]["p_holm"] = h
        r["adjusted"]["q_bh"] = q
        r["mde_holm_pp"] = 100 * vs.minimum_detectable_effect(r.pop("_se"), len(tested))["mde_holm"]
    for r in rows:
        r.pop("_se", None)


def _composite_block(
    sample: dict[str, np.ndarray],
    saving_w: np.ndarray,
    period: np.ndarray,
    label: str,
    codes: tuple[str, ...],
    seed: int,
) -> dict:
    score = composite(sample, codes)[period]
    buyers = sample["buyer"][period]
    y = sample["saving"][period]
    block: dict = {
        "label": label,
        "signals": list(codes),
        "n": int(period.sum()),
        "share_with_score_above_zero": float((score > 0).mean()),
    }
    if (score > 0).sum() < MIN_FLAGGED:
        block["status"] = "not_testable"
        return block
    block["status"] = "tested"
    block["spearman"] = vs.spearman_cluster_bootstrap(score, y, buyers, N_BOOT_SPEARMAN, seed)
    x = np.column_stack([score / 10.0, sample["log_budget"][period]])
    res = vs.fe_cluster_ols(saving_w[period], x, _fe(sample, period), buyers, focus=0)
    block["effect_per_10_points_pp"] = {
        "effect_pp": 100 * res.coef,
        "ci_low_pp": 100 * res.ci_low,
        "ci_high_pp": 100 * res.ci_high,
        "p_value": res.p_value,
    }
    return block


def analyse_period(sample: dict[str, np.ndarray], years: tuple[int, int], n_boot: int, seed: int) -> dict:
    period = period_mask(sample, years)
    saving_w = np.zeros(len(period))
    saving_w[period] = vs.winsorise(sample["saving"][period])
    rows = [_signal_row(sample, saving_w, c, period, n_boot, seed) for c in ALL_SIGNALS]
    _correct(rows)
    non_circular = tuple(c for c in SIGNAL_WEIGHTS if c not in CIRCULAR)
    composites = [
        _composite_block(
            sample, saving_w, period, "production weights without the circular signals", non_circular, seed
        ),
        _composite_block(
            sample, saving_w, period, "signals observable before the award only", PRE_AWARD_COMPOSITE, seed
        ),
        _composite_block(
            sample,
            saving_w,
            period,
            "full production score (contains circular signals; reference only)",
            tuple(SIGNAL_WEIGHTS),
            seed,
        ),
    ]
    return {
        "years": list(years),
        "n_processes": int(period.sum()),
        "n_buyers": int(len(set(sample["buyer"][period]))),
        "median_saving": float(np.median(sample["saving"][period])),
        "signals": rows,
        "composites": composites,
    }


def list_backtest_summary(backtest_path: Path) -> dict:
    """Headline of the existing SRI-list back-test plus what so few positives can detect."""
    import orjson

    if not backtest_path.exists():
        return {"status": "backtest_json_missing"}
    prim = orjson.loads(backtest_path.read_bytes())["primary"]
    n_pos, n_unl = prim["n_positives"], prim["n_unlabelled"]
    head = prim["scores"]["A:mean"]
    return {
        "status": "carried_over_from_eval/backtest.json",
        "n_positives": n_pos,
        "n_unlabelled": n_unl,
        "auc": head["auc"],
        "lift_top_1": head["lift_top_1"],
        "lift_top_5": head["lift_top_5"],
        "lift_top_10": head["lift_top_10"],
        "prevalence": prim["prevalence"],
        "power": vs.auc_null_power(n_pos, n_unl),
    }


def run_validation(
    lake_dir: Path,
    marts_dir: Path,
    backtest_path: Path,
    doc_path: Path,
    n_boot: int = N_BOOT_MEDIAN,
    seed: int = DEFAULT_SEED,
) -> dict:
    sample = load_sample(lake_dir, marts_dir)
    return {
        "meta": {
            "seed": seed,
            "n_boot_median": n_boot,
            "n_boot_spearman": N_BOOT_SPEARMAN,
            "plan_sha256": plan_sha256(doc_path),
            "n_sample": int(len(sample["year"])),
            "min_flagged": MIN_FLAGGED,
            "min_buyers": MIN_BUYERS,
        },
        "explore": analyse_period(sample, EXPLORE_YEARS, n_boot, seed),
        "confirm": analyse_period(sample, CONFIRM_YEARS, n_boot, seed),
        "list_backtest": list_backtest_summary(backtest_path),
        "larger_list": {
            "obtained": False,
            "checked_url": "https://www.sri.gob.ec/empresas-fantasma",
            "checked_on": "2026-11-16",
            "finding": "The official XLSX and PDF (Catastro Fantasma) hold 1,112 distinct RUCs, all in "
            "the CSV-based list used (1,113 in the lake); no larger official set was found.",
        },
    }
