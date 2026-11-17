"""Statistics for the price validation: fixed-effects OLS with clustered errors, bootstraps, corrections.

Pure numpy/scipy; no I/O. Every function is deterministic given its inputs and seed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm, rankdata
from scipy.stats import t as t_dist

Z_ALPHA = float(norm.ppf(0.975))
Z_POWER = float(norm.ppf(0.80))


@dataclass(frozen=True, slots=True)
class OlsResult:
    coef: float
    se: float
    ci_low: float
    ci_high: float
    p_value: float
    n: int
    n_clusters: int


def codes(values: Sequence[object] | np.ndarray) -> np.ndarray:
    """Integer codes 0..k-1 for a categorical column (missing values form their own level)."""
    arr = np.asarray(["<missing>" if v is None else str(v) for v in values])
    return np.unique(arr, return_inverse=True)[1]


def absorb(
    columns: np.ndarray, groups: Sequence[np.ndarray], tol: float = 1e-10, max_iter: int = 500
) -> np.ndarray:
    """Remove group means of every categorical factor from each column (alternating projections)."""
    out = np.array(columns, dtype=float, copy=True)
    if out.ndim == 1:
        out = out[:, None]
    sizes = [np.bincount(g) for g in groups]
    for _ in range(max_iter):
        worst = 0.0
        for g, size in zip(groups, sizes, strict=True):
            for j in range(out.shape[1]):
                mean = np.bincount(g, weights=out[:, j]) / size
                out[:, j] -= mean[g]
                worst = max(worst, float(np.abs(mean).max()))
        if worst < tol:
            break
    return out


def fe_cluster_ols(
    y: np.ndarray,
    x: np.ndarray,
    fixed_effects: Sequence[np.ndarray],
    cluster: np.ndarray,
    focus: int = 0,
) -> OlsResult:
    """OLS of y on x with absorbed fixed effects and CR1 cluster-robust errors; reports column `focus`."""
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    n, k = x.shape
    z = absorb(np.column_stack([y, x]), fixed_effects)
    yt, xt = z[:, 0], z[:, 1:]
    xtx = xt.T @ xt
    if np.linalg.matrix_rank(xtx) < k:
        raise ValueError("The design is rank deficient after absorbing the fixed effects.")
    inv = np.linalg.inv(xtx)
    beta = inv @ (xt.T @ yt)
    resid = yt - xt @ beta
    g_codes = np.unique(cluster, return_inverse=True)[1]
    n_clusters = int(g_codes.max()) + 1
    scores = np.zeros((n_clusters, k))
    for j in range(k):
        scores[:, j] = np.bincount(g_codes, weights=xt[:, j] * resid, minlength=n_clusters)
    meat = scores.T @ scores
    n_absorbed = sum(int(g.max()) + 1 for g in fixed_effects) - max(len(fixed_effects) - 1, 0)
    dof = max(n - k - n_absorbed, 1)
    scale = (n_clusters / max(n_clusters - 1, 1)) * ((n - 1) / dof)
    var = scale * inv @ meat @ inv
    se = float(np.sqrt(var[focus, focus]))
    coef = float(beta[focus])
    df = max(n_clusters - 1, 1)
    crit = float(t_dist.ppf(0.975, df))
    p = float(2 * t_dist.sf(abs(coef / se), df)) if se > 0 else float("nan")
    return OlsResult(coef, se, coef - crit * se, coef + crit * se, p, n, n_clusters)


def _weighted_median(sorted_values: np.ndarray, weights_sorted: np.ndarray) -> float:
    total = weights_sorted.sum()
    if total <= 0:
        return float("nan")
    cum = np.cumsum(weights_sorted)
    return float(sorted_values[int(np.searchsorted(cum, total / 2.0))])


def median_difference_cluster_bootstrap(
    y: np.ndarray, flag: np.ndarray, cluster: np.ndarray, n_boot: int, seed: int
) -> dict[str, float]:
    """Median(y | flag) - median(y | not flag) with a percentile interval resampling clusters."""
    flag = np.asarray(flag, dtype=bool)
    g_codes = np.unique(cluster, return_inverse=True)[1]
    n_clusters = int(g_codes.max()) + 1
    parts = []
    for mask in (flag, ~flag):
        order = np.argsort(y[mask], kind="stable")
        parts.append((y[mask][order], g_codes[mask][order]))
    point = [float(np.median(y[m])) if m.any() else float("nan") for m in (flag, ~flag)]
    diffs = np.empty(n_boot)
    rng = np.random.default_rng(seed)
    for b in range(n_boot):
        counts = np.bincount(rng.integers(0, n_clusters, n_clusters), minlength=n_clusters).astype(float)
        meds = [_weighted_median(v, counts[g]) for v, g in parts]
        diffs[b] = meds[0] - meds[1]
    low, high = np.nanpercentile(diffs, [2.5, 97.5])
    return {
        "median_with": point[0],
        "median_without": point[1],
        "difference": point[0] - point[1],
        "ci_low": float(low),
        "ci_high": float(high),
    }


def spearman_cluster_bootstrap(
    a: np.ndarray, b: np.ndarray, cluster: np.ndarray, n_boot: int, seed: int
) -> dict[str, float]:
    """Spearman correlation (average ranks) with a percentile interval resampling clusters."""

    def rho(u: np.ndarray, v: np.ndarray) -> float:
        ru, rv = rankdata(u), rankdata(v)
        if ru.std() == 0 or rv.std() == 0:
            return float("nan")
        return float(np.corrcoef(ru, rv)[0, 1])

    g_codes = np.unique(cluster, return_inverse=True)[1]
    n_clusters = int(g_codes.max()) + 1
    order = np.argsort(g_codes, kind="stable")
    bounds = np.concatenate([[0], np.cumsum(np.bincount(g_codes, minlength=n_clusters))])
    rng = np.random.default_rng(seed)
    reps = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, n_clusters, n_clusters)
        idx = order[np.concatenate([np.arange(bounds[c], bounds[c + 1]) for c in pick])]
        reps[i] = rho(a[idx], b[idx])
    low, high = np.nanpercentile(reps, [2.5, 97.5])
    return {"rho": rho(a, b), "ci_low": float(low), "ci_high": float(high)}


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (family-wise error control), in input order."""
    m = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted.tolist()


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg q-values (false discovery rate), in input order."""
    m = len(p_values)
    order = np.argsort(p_values)[::-1]
    q = np.empty(m)
    running = 1.0
    for rank, i in zip(range(m, 0, -1), order, strict=True):
        running = min(running, p_values[i] * m / rank)
        q[i] = running
    return q.tolist()


def minimum_detectable_effect(se: float, n_comparisons: int = 1) -> dict[str, float]:
    """Effect detectable with 80 % power, two-sided alpha 0.05, plain and Holm-conservative."""
    z_holm = float(norm.ppf(1 - 0.05 / (2 * max(n_comparisons, 1))))
    return {"mde": (Z_ALPHA + Z_POWER) * se, "mde_holm": (z_holm + Z_POWER) * se}


def auc_null_power(n_pos: int, n_neg: int) -> dict[str, float]:
    """Null standard error of the AUC and the approximate AUC detectable at 80 % power (alpha 0.05)."""
    if n_pos < 1 or n_neg < 1:
        return {"se_null": float("nan"), "detectable_auc": float("nan")}
    se = float(np.sqrt((n_pos + n_neg + 1) / (12.0 * n_pos * n_neg)))
    return {"se_null": se, "detectable_auc": min(1.0, 0.5 + (Z_ALPHA + Z_POWER) * se)}


def winsorise(values: np.ndarray, low: float = 0.01, high: float = 0.99) -> np.ndarray:
    lo, hi = np.quantile(values, [low, high])
    return np.clip(values, lo, hi)
