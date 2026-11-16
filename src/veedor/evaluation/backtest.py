"""Positive-unlabelled back-test of the risk indicators against the SRI ghost-company list.

The only external label in the open data is the SRI list of "empresas fantasmas". Positives are
listed suppliers that won at least one process; everything else is *unlabelled*, not negative.
The functions here return plain dictionaries that `report.py` renders; nothing is typed by hand.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from veedor.domain.signals import definitions as d
from veedor.domain.signals.scoring import SIGNAL_WEIGHTS
from veedor.evaluation import data
from veedor.evaluation.metrics import (
    METRIC_NAMES,
    Interval,
    RankingProblem,
    bootstrap_metrics,
    percentile_interval,
    permutation_pvalues_auc,
    resample_weights,
)

DEFAULT_SEED = 20260101
DEFAULT_N_BOOT = 2000
N_PERMUTATIONS = 5000
HEADLINE = "A:mean"
LABEL_SIGNAL = d.GHOST_COMPANY_LIST
GHOST_CODES = frozenset({d.GHOST_COMPANY_LIST, d.GHOST_COMPANY_LISTED_LATER})
CONTEXT_CODES = tuple(sorted(d.CONTEXT_CODES))
STATUS_SIGNAL = d.SUPPLIER_NOT_ACTIVE
SIZE_SIGNAL = d.CONTRACT_VS_COMPANY_SIZE
VARIANTS: dict[str, tuple[str, frozenset[str]]] = {
    "A": (
        "held-out score A: without both ghost-list codes and SUPPLIER_NOT_ACTIVE",
        GHOST_CODES | {STATUS_SIGNAL},
    ),
    "B": (
        "held-out score B: A and also without CONTRACT_VS_COMPANY_SIZE",
        GHOST_CODES | {STATUS_SIGNAL, SIZE_SIGNAL},
    ),
    "C": (
        "score C: keeps the time-aware SUPPLIER_NOT_ACTIVE, excludes only the ghost-list codes",
        GHOST_CODES,
    ),
}
AGGREGATES = {"mean": "score_mean", "max": "score_max", "share": "score_share"}
SIGNAL_ROLE = {
    LABEL_SIGNAL: "label",
    d.GHOST_COMPANY_LISTED_LATER: "label",
    d.CONTRACT_VS_COMPANY_SIZE_SAME_YEAR: "context",
    STATUS_SIGNAL: "kept_in_variant_C",
    SIZE_SIGNAL: "checked_in_variant_B",
}


def _sql_list(codes: Iterable[str]) -> str:
    return ", ".join(f"'{c}'" for c in sorted(codes))


def _iv(interval: Interval) -> dict[str, float | None]:
    return asdict(interval)


def _metrics_json(result: Mapping[str, Mapping[str, Interval]]) -> dict[str, dict[str, Any]]:
    return {name: {m: _iv(i) for m, i in metrics.items()} for name, metrics in result.items()}


def _count_positive_suppliers(table: Mapping[str, np.ndarray]) -> tuple[int, int]:
    label = table["label"].astype(bool)
    return int(label.sum()), int((~label).sum())


def _problems(
    con: duckdb.DuckDBPyConnection,
    *,
    kinds: tuple[str, ...],
    temporal: bool,
    variants: tuple[str, ...],
    include_full_score: bool,
) -> tuple[dict[str, RankingProblem], dict[str, np.ndarray]]:
    tables = {
        v: data.supplier_table(
            con, data.score_sql(SIGNAL_WEIGHTS, VARIANTS[v][1]), kinds=kinds, temporal=temporal
        )
        for v in variants
    }
    if include_full_score:
        tables["full"] = data.supplier_table(
            con, data.score_sql(SIGNAL_WEIGHTS), kinds=kinds, temporal=temporal
        )
    base = tables[variants[0]]
    label = base["label"].astype(bool)
    problems: dict[str, RankingProblem] = {}
    for name, table in tables.items():
        for agg, column in AGGREGATES.items():
            problems[f"{name}:{agg}"] = RankingProblem(table[column], label)
    problems["baseline:amount"] = RankingProblem(base["amount"], label)
    problems["baseline:n_processes"] = RankingProblem(base["n_processes"], label)
    return problems, base


def run_analysis(
    con: duckdb.DuckDBPyConnection,
    description: str,
    *,
    kinds: tuple[str, ...] = (data.KIND_COMPANY,),
    temporal: bool = False,
    variants: tuple[str, ...] = ("A", "B", "C"),
    include_full_score: bool = False,
    n_boot: int,
    seed: int,
) -> dict[str, Any]:
    """Supplier-level back-test: every aggregate of every score, with bootstrap CIs."""
    problems, base = _problems(
        con, kinds=kinds, temporal=temporal, variants=variants, include_full_score=include_full_score
    )
    n_pos, n_unl = _count_positive_suppliers(base)
    if n_pos == 0 or n_unl == 0:
        raise ValueError(f"Back-test needs positives and unlabelled suppliers (got {n_pos} and {n_unl}).")
    paired = tuple((f"{v}:{a}", "baseline:amount") for v in variants for a in AGGREGATES)
    boot = bootstrap_metrics(problems, n_boot, seed, paired=paired)
    permutation = permutation_pvalues_auc(problems, N_PERMUTATIONS, seed)
    return {
        "description": description,
        "kinds": list(kinds),
        "temporal_filter": temporal,
        "n_positives": n_pos,
        "n_unlabelled": n_unl,
        "prevalence": n_pos / (n_pos + n_unl),
        "random_baseline": {"auc": 0.5, "average_precision": n_pos / (n_pos + n_unl), "lift": 1.0},
        "scores": _metrics_json({k: v for k, v in boot.items() if " - " not in k}),
        "paired_differences": _metrics_json({k: v for k, v in boot.items() if " - " in k}),
        "permutation_p_auc": permutation,
        "n_boot": n_boot,
        "positives_summary": _positives_summary(base),
    }


def _positives_summary(base: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """Counts only: listed suppliers are never identified in the output."""
    label = base["label"].astype(bool)
    n_proc = base["n_processes"][label]
    mean = base["score_mean"][label]
    return {
        "n_with_zero_held_out_mean": int((mean == 0).sum()),
        "n_with_positive_held_out_mean": int((mean > 0).sum()),
        "n_processes_min": int(n_proc.min()),
        "n_processes_median": float(np.median(n_proc)),
        "n_processes_max": int(n_proc.max()),
    }


def buyer_labels(buyer_rucs: Iterable[str]) -> dict[str, str]:
    """Stable anonymous labels ("Buyer 01", ...) ordered by number of positive processes, then RUC."""
    counts: dict[str, int] = {}
    for ruc in buyer_rucs:
        counts[str(ruc)] = counts.get(str(ruc), 0) + 1
    ordered = sorted(counts, key=lambda r: (-counts[r], r))
    return {ruc: f"Buyer {i + 1:02d}" for i, ruc in enumerate(ordered)}


def run_anomaly(con: duckdb.DuckDBPyConnection, n_boot: int, seed: int) -> dict[str, Any]:
    """Same back-test for the anomaly score alone (only suppliers with >= 1 scored process)."""
    table = data.supplier_table(con, data.score_sql(SIGNAL_WEIGHTS, VARIANTS["A"][1]), scored_only=True)
    label = table["label"].astype(bool)
    n_pos, n_unl = _count_positive_suppliers(table)
    if n_pos == 0 or n_unl == 0:
        return {
            "description": "anomaly_score alone: not evaluable (a class has no scored supplier)",
            "n_positives": n_pos,
            "n_unlabelled": n_unl,
            "scores": {},
            "paired_differences": {},
            "n_boot": n_boot,
        }
    problems = {
        "anomaly:mean": RankingProblem(table["anomaly_mean"], label),
        "anomaly:max": RankingProblem(table["anomaly_max"], label),
        "baseline:amount": RankingProblem(table["amount"], label),
        "baseline:n_processes": RankingProblem(table["n_processes"], label),
    }
    boot = bootstrap_metrics(problems, n_boot, seed, paired=(("anomaly:mean", "baseline:amount"),))
    return {
        "description": "anomaly_score alone; companies with at least one process that has an anomaly score",
        "n_positives": n_pos,
        "n_unlabelled": n_unl,
        "prevalence": n_pos / (n_pos + n_unl),
        "scores": _metrics_json({k: v for k, v in boot.items() if " - " not in k}),
        "paired_differences": _metrics_json({k: v for k, v in boot.items() if " - " in k}),
        "n_boot": n_boot,
    }


def per_signal(
    con: duckdb.DuckDBPyConnection, *, temporal: bool, non_catalogue: bool, n_boot: int, seed: int
) -> dict[str, Any]:
    """Rate of each signal among positives' processes vs unlabelled suppliers' processes.

    Rates are over processes; CIs resample suppliers (cluster bootstrap), because the processes of
    one supplier are not independent.
    """
    codes = [*SIGNAL_WEIGHTS, *CONTEXT_CODES]
    counts = data.signal_counts(con, codes, temporal=temporal, non_catalogue=non_catalogue)
    label = counts["label"].astype(bool)
    n = counts["n_processes"].astype(float)
    fired = np.column_stack([counts[f"n_{c.lower()}"] for c in codes]).astype(float)
    pos, neg = np.flatnonzero(label), np.flatnonzero(~label)
    rate_pos = fired[pos].sum(0) / n[pos].sum()
    rate_neg = fired[neg].sum(0) / n[neg].sum()
    rng = np.random.default_rng(seed)
    draws: dict[str, list[np.ndarray]] = defaultdict(list)
    for start in range(0, n_boot, 100):
        wp, wn = resample_weights(rng, pos.size, neg.size, min(100, n_boot - start))
        bp = (wp @ fired[pos]) / (wp @ n[pos])[:, None]
        bn = (wn @ fired[neg]) / (wn @ n[neg])[:, None]
        draws["pos"].append(bp)
        draws["neg"].append(bn)
        with np.errstate(divide="ignore", invalid="ignore"):
            draws["ratio"].append(np.where(bn > 0, bp / bn, np.nan))
    stacked = {k: np.vstack(v) for k, v in draws.items()}
    rows = {}
    for j, code in enumerate(codes):
        ratio = rate_pos[j] / rate_neg[j] if rate_neg[j] > 0 else None
        rows[code] = {
            "role": SIGNAL_ROLE.get(code, "in_heldout"),
            "fired_positives": int(fired[pos, j].sum()),
            "fired_unlabelled": int(fired[neg, j].sum()),
            "rate_positives": _iv(percentile_interval(stacked["pos"][:, j], float(rate_pos[j]))),
            "rate_unlabelled": _iv(percentile_interval(stacked["neg"][:, j], float(rate_neg[j]))),
            "ratio": _iv(percentile_interval(stacked["ratio"][:, j], ratio)),
        }
    return {
        "scope": "non-catalogue processes" if non_catalogue else "all processes",
        "temporal_filter": temporal,
        "n_processes_positives": int(n[pos].sum()),
        "n_processes_unlabelled": int(n[neg].sum()),
        "n_positive_suppliers": int(pos.size),
        "signals": rows,
    }


def robustness(con: duckdb.DuckDBPyConnection, *, temporal: bool, n_boot: int, seed: int) -> dict[str, Any]:
    """Compare positives' processes with unlabelled processes of the same method key and year.

    Only positives are resampled; the unlabelled strata are treated as fixed.
    """
    score = data.score_sql(SIGNAL_WEIGHTS, VARIANTS["A"][1])
    pos = data.labelled_processes(con, score, temporal=temporal)
    neg = data.unlabelled_strata(con, score)
    strata: dict[tuple[str, int], tuple[np.ndarray, np.ndarray]] = {}
    for key in {(m, int(y)) for m, y in zip(neg["method_key"], neg["year"], strict=True)}:
        mask = (neg["method_key"] == key[0]) & (neg["year"] == key[1])
        strata[key] = (neg["score"][mask].astype(float), neg["n"][mask].astype(float))
    per_supplier: dict[str, list[list[float]]] = defaultdict(list)
    dropped = 0
    for i in range(pos["ruc"].size):
        key = (str(pos["method_key"][i]), int(pos["year"][i]))
        if key not in strata:
            dropped += 1
            continue
        scores, counts = strata[key]
        total, s = counts.sum(), float(pos["score"][i])
        concordance = (counts[scores < s].sum() + 0.5 * counts[scores == s].sum()) / total
        expected_mean = float((scores * counts).sum() / total)
        expected_any = float(counts[scores > 0].sum() / total)
        per_supplier[str(pos["ruc"][i])].append(
            [concordance, s, expected_mean, float(s > 0), expected_any, 1.0]
        )
    suppliers = sorted(per_supplier)
    contrib = np.array([np.sum(per_supplier[r], axis=0) for r in suppliers])
    point = contrib.sum(0)
    rng = np.random.default_rng(seed)
    boots = []
    for start in range(0, n_boot, 200):
        size = min(200, n_boot - start)
        w = rng.multinomial(len(suppliers), np.full(len(suppliers), 1 / len(suppliers)), size=size)
        boots.append(w @ contrib)
    b = np.vstack(boots)

    def ratio(num: int, den: int, arr: np.ndarray) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            return arr[..., num] / arr[..., den]

    return {
        "description": "positives' processes vs unlabelled company-won processes, same method key and year",
        "temporal_filter": temporal,
        "n_positive_processes_used": int(point[5]),
        "n_positive_processes_dropped_no_stratum": dropped,
        "n_positive_suppliers": len(suppliers),
        "n_strata_with_positives": len(
            {(str(m), int(y)) for m, y in zip(pos["method_key"], pos["year"], strict=True)}
        ),
        "stratified_concordance": _iv(percentile_interval(ratio(0, 5, b), float(point[0] / point[5]))),
        "mean_score_observed": _iv(percentile_interval(ratio(1, 5, b), float(point[1] / point[5]))),
        "mean_score_expected": _iv(percentile_interval(ratio(2, 5, b), float(point[2] / point[5]))),
        "mean_score_ratio": _iv(
            percentile_interval(ratio(1, 2, b), float(point[1] / point[2]) if point[2] else None)
        ),
        "any_signal_observed": _iv(percentile_interval(ratio(3, 5, b), float(point[3] / point[5]))),
        "any_signal_expected": _iv(percentile_interval(ratio(4, 5, b), float(point[4] / point[5]))),
        "any_signal_ratio": _iv(
            percentile_interval(ratio(3, 4, b), float(point[3] / point[4]) if point[4] else None)
        ),
        "n_boot": n_boot,
    }


def buyer_concentration(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """How concentrated the positives' processes are by buyer (independence of the positives)."""
    pos = data.labelled_processes(con, data.score_sql(SIGNAL_WEIGHTS, VARIANTS["A"][1]), temporal=False)
    labels = buyer_labels(pos["buyer_ruc"])
    by_buyer: dict[str, dict[str, Any]] = {}
    for ruc, buyer in zip(pos["ruc"], pos["buyer_ruc"], strict=True):
        entry = by_buyer.setdefault(
            str(buyer), {"buyer": labels[str(buyer)], "n_processes": 0, "suppliers": set()}
        )
        entry["n_processes"] += 1
        entry["suppliers"].add(str(ruc))
    total = sum(e["n_processes"] for e in by_buyer.values())
    shares = np.array([e["n_processes"] / total for e in by_buyer.values()])
    suppliers_all = {s for e in by_buyer.values() for s in e["suppliers"]}
    shared = {s for e in by_buyer.values() if len(e["suppliers"]) > 1 for s in e["suppliers"]}
    top = sorted(by_buyer.values(), key=lambda e: e["buyer"])[:5]
    return {
        "n_positive_processes": total,
        "n_distinct_buyers": len(by_buyer),
        "n_positive_suppliers": len(suppliers_all),
        "effective_n_buyers": float(1 / np.sum(shares**2)),
        "positive_suppliers_sharing_a_buyer": len(shared),
        "top_buyers": [
            {
                "buyer": e["buyer"],
                "n_processes": e["n_processes"],
                "share": e["n_processes"] / total,
                "n_positive_suppliers": len(e["suppliers"]),
            }
            for e in top
        ],
    }


def label_overview(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Size of the label set and the timing of positives' awards relative to the SRI notification."""
    n_ruc = con.execute("SELECT count(DISTINCT ruc) FROM ghost_companies").fetchone()[0]
    rows = con.execute(
        """
        SELECT e.winner_kind, e.winner_ruc,
          CASE WHEN g.notification_date IS NULL THEN 'unknown'
               WHEN e.award_date < TRY_CAST(g.notification_date AS DATE) THEN 'before'
               ELSE 'on_or_after' END AS timing
        FROM eval_process e JOIN ghost_companies g ON g.ruc = e.winner_ruc
        """
    ).fetchall()
    out: dict[str, Any] = {"n_listed_rucs": n_ruc, "by_kind": {}}
    for kind in (data.KIND_COMPANY, data.KIND_NATURAL):
        sel = [r for r in rows if r[0] == kind]
        out["by_kind"][kind] = {
            "n_suppliers_with_award": len({r[1] for r in sel}),
            "n_processes": len(sel),
            "processes_before_notification": sum(r[2] == "before" for r in sel),
            "processes_on_or_after_notification": sum(r[2] == "on_or_after" for r in sel),
            "processes_without_notification_date": sum(r[2] == "unknown" for r in sel),
        }
    out["n_suppliers_with_award"] = len({r[1] for r in rows})
    return out


def size_signal_leakage_check(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Evidence on whether CONTRACT_VS_COMPANY_SIZE could be affected by the SRI listing.

    Not proof either way. It measures (a) whether the signal fires on awards made after the
    notification, (b) whether the revenue year it used is at or after the notification year, and
    (c) whether listed companies are evaluable at all (have any financial row).
    """
    fired = con.execute(
        f"""
        SELECT e.ocid, e.award_date, TRY_CAST(g.notification_date AS DATE) AS notif,
               TRY_CAST(json_extract_string(s.evidence_json, '$.revenue_year') AS INT) AS revenue_year
        FROM process_signals s JOIN eval_process e USING (ocid)
        JOIN ghost_companies g ON g.ruc = e.winner_ruc
        WHERE s.signal_code = '{SIZE_SIGNAL}' AND e.winner_kind = '{data.KIND_COMPANY}'
        """
    ).fetchall()
    evaluable = con.execute(
        f"""
        WITH sup AS (
          SELECT DISTINCT e.winner_ruc AS ruc, (g.ruc IS NOT NULL) AS pos
          FROM eval_process e LEFT JOIN ghost_companies g ON g.ruc = e.winner_ruc
          WHERE e.winner_kind = '{data.KIND_COMPANY}'),
        fin AS (SELECT DISTINCT ruc FROM company_financials WHERE revenue > 0)
        SELECT pos, count(*), count(fin.ruc) FROM sup LEFT JOIN fin USING (ruc) GROUP BY pos
        """
    ).fetchall()
    share = {bool(p): (k / n if n else None, n, k) for p, n, k in evaluable}
    after = [r for r in fired if r[2] is not None and r[1] is not None and r[1] >= r[2]]
    late_revenue = [r for r in fired if r[2] is not None and r[3] is not None and r[3] >= r[2].year]
    return {
        "n_fired_on_positive_company_processes": len(fired),
        "n_fired_awarded_on_or_after_notification": len(after),
        "n_fired_with_revenue_year_at_or_after_notification_year": len(late_revenue),
        "share_positives_with_positive_revenue_row": share.get(True, (None, 0, 0))[0],
        "n_positive_companies": share.get(True, (None, 0, 0))[1],
        "share_unlabelled_with_positive_revenue_row": share.get(False, (None, 0, 0))[0],
        "n_unlabelled_companies": share.get(False, (None, 0, 0))[1],
    }


def status_signal_check(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Where the (now time-aware) SUPPLIER_NOT_ACTIVE signal fires relative to the label."""
    rows = con.execute(
        f"""
        SELECT e.winner_kind, (g.ruc IS NOT NULL) AS pos,
               g.notification_date IS NOT NULL
                 AND e.award_date >= TRY_CAST(g.notification_date AS DATE) AS after_notification
        FROM process_signals s JOIN eval_process e USING (ocid)
        LEFT JOIN ghost_companies g ON g.ruc = e.winner_ruc
        WHERE s.signal_code = '{STATUS_SIGNAL}'
        """
    ).fetchall()
    on_pos = [r for r in rows if r[1]]
    return {
        "n_firings": len(rows),
        "n_firings_on_positive_processes": len(on_pos),
        "n_firings_on_positive_company_processes": sum(r[0] == data.KIND_COMPANY for r in on_pos),
        "n_firings_on_positive_processes_after_notification": sum(bool(r[2]) for r in on_pos),
        "n_firings_company_won": sum(r[0] == data.KIND_COMPANY for r in rows),
    }


def leave_one_buyer_out(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Recompute point AUCs dropping, in turn, every process of each buyer where a positive won.

    Shows whether one buyer drives the result. Point estimates only (no bootstrap).
    """
    pos = data.labelled_processes(con, data.score_sql(SIGNAL_WEIGHTS, VARIANTS["A"][1]), temporal=False)
    labels = buyer_labels(pos["buyer_ruc"])
    buyers = sorted(labels.items(), key=lambda kv: kv[1])
    out: dict[str, Any] = {"n_buyers_dropped_in_turn": len(buyers), "variants": {}}
    for variant in ("A", "C"):
        score = data.score_sql(SIGNAL_WEIGHTS, VARIANTS[variant][1])
        runs: dict[str, list[tuple[float, str, int]]] = {a: [] for a in AGGREGATES}
        for ruc, name in buyers:
            table = data.supplier_table(con, score, exclude_buyer=ruc)
            label = table["label"].astype(bool)
            if label.sum() == 0 or label.all():
                continue
            for agg, column in AGGREGATES.items():
                auc = RankingProblem(table[column], label).metrics()["auc"]
                runs[agg].append((auc, name, int(label.sum())))
        out["variants"][variant] = {
            agg: {
                "min_auc": min(r)[0],
                "min_buyer": min(r)[1],
                "min_n_positives": min(r)[2],
                "max_auc": max(r)[0],
                "max_buyer": max(r)[1],
                "max_n_positives": max(r)[2],
            }
            for agg, r in runs.items()
            if r
        }
    return out


def consistency_check(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Flags rebuilt from process_signals must equal the code lists of process_scores (risk and context)."""
    risk = " OR ".join(f"({data.flag(c)} <> list_contains(s.signal_codes, '{c}'))" for c in SIGNAL_WEIGHTS)
    context = " OR ".join(
        f"({data.flag(c)} <> list_contains(s.context_signal_codes, '{c}'))" for c in CONTEXT_CODES
    )
    base = "SELECT count(*) FROM eval_process e JOIN process_scores s USING (ocid) WHERE "
    return {
        "processes_with_flag_mismatch": int(con.execute(base + risk).fetchone()[0]),
        "processes_with_context_flag_mismatch": int(con.execute(base + context).fetchone()[0]),
    }


def run_backtest(
    lake_dir: Path, marts_dir: Path, n_boot: int = DEFAULT_N_BOOT, seed: int = DEFAULT_SEED
) -> dict[str, Any]:
    """Run every analysis and return the JSON-serialisable result."""
    con = data.connect(lake_dir, marts_dir)
    data.build_process_table(con, SIGNAL_WEIGHTS, CONTEXT_CODES)
    n_processes = con.execute("SELECT count(*) FROM eval_process").fetchone()[0]
    common = {"n_boot": n_boot, "seed": seed}
    return {
        "meta": {
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            "seed": seed,
            "n_boot": n_boot,
            "n_permutations": N_PERMUTATIONS,
            "n_processes": n_processes,
            "weights": dict(SIGNAL_WEIGHTS),
            "variants": {k: {"description": v[0], "excluded": sorted(v[1])} for k, v in VARIANTS.items()},
            "headline": HEADLINE,
            "consistency": consistency_check(con),
        },
        "labels": label_overview(con),
        "size_signal_check": size_signal_leakage_check(con),
        "status_signal_check": status_signal_check(con),
        "primary": run_analysis(
            con, "Companies; all awards; held-out scores", include_full_score=True, **common
        ),
        "temporal": run_analysis(
            con,
            "Companies; positives restricted to awards before their SRI notification date",
            temporal=True,
            **common,
        ),
        "all_suppliers": run_analysis(
            con,
            "Companies and natural persons together (not like-for-like); all awards",
            kinds=(data.KIND_COMPANY, data.KIND_NATURAL),
            variants=("A", "C"),
            **common,
        ),
        "all_suppliers_temporal": run_analysis(
            con,
            "Companies and natural persons together; positives restricted to awards before notification",
            kinds=(data.KIND_COMPANY, data.KIND_NATURAL),
            temporal=True,
            variants=("A", "C"),
            **common,
        ),
        "anomaly": run_anomaly(con, n_boot, seed),
        "per_signal": {
            "all_processes": per_signal(con, temporal=False, non_catalogue=False, **common),
            "non_catalogue": per_signal(con, temporal=False, non_catalogue=True, **common),
        },
        "robustness": robustness(con, temporal=False, **common),
        "buyer_concentration": buyer_concentration(con),
        "leave_one_buyer_out": leave_one_buyer_out(con),
        "metric_names": list(METRIC_NAMES),
    }
