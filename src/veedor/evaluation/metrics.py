"""Ranking metrics with ties, weights and supplier-level bootstrap.

All metrics are computed from per-unit weights so that one function serves both the point
estimate (all weights 1) and a bootstrap replicate (weights = how many times the unit was drawn).
Ties are handled explicitly: units with the same score are treated as one block.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import rankdata

LIFT_FRACTIONS = (0.01, 0.05, 0.10)
CI_LEVEL = 0.95


@dataclass(frozen=True, slots=True)
class Interval:
    estimate: float | None
    low: float | None
    high: float | None


class RankingProblem:
    """A fixed set of units with a score and a binary label."""

    def __init__(self, score: np.ndarray, label: np.ndarray) -> None:
        score = np.asarray(score, dtype=float)
        label = np.asarray(label, dtype=bool)
        if score.shape != label.shape or score.ndim != 1:
            raise ValueError("score and label must be 1-D arrays of the same length")
        if np.isnan(score).any():
            raise ValueError("score must not contain NaN")
        self.score = score
        self.label = label
        _, self._group = np.unique(score, return_inverse=True)
        self._n_groups = int(self._group.max()) + 1 if score.size else 0

    def metrics(self, weight: np.ndarray | None = None) -> dict[str, float]:
        """AUC, average precision and lift at the top 1/5/10 % under the given unit weights.

        Ties at a cut-off are split proportionally (the expected result of breaking ties at random).
        """
        w = np.ones(self.label.size) if weight is None else np.asarray(weight, dtype=float)
        tp = np.bincount(self._group, w * self.label, self._n_groups)
        fp = np.bincount(self._group, w * ~self.label, self._n_groups)
        n_pos, n_neg = tp.sum(), fp.sum()
        if n_pos == 0 or n_neg == 0:
            raise ValueError("both classes need positive weight")
        below_neg = np.cumsum(fp) - fp
        out = {"auc": float((tp * (below_neg + 0.5 * fp)).sum() / (n_pos * n_neg))}
        tp_d, fp_d = tp[::-1], fp[::-1]
        c_tp, c_all = np.cumsum(tp_d), np.cumsum(tp_d + fp_d)
        precision = np.divide(c_tp, c_all, out=np.zeros_like(c_tp), where=c_all > 0)
        out["average_precision"] = float((tp_d / n_pos * precision).sum())
        total = n_pos + n_neg
        for fraction in LIFT_FRACTIONS:
            k = fraction * total
            i = min(int(np.searchsorted(c_all, k, side="left")), self._n_groups - 1)
            before_all, before_tp = c_all[i] - (tp_d[i] + fp_d[i]), c_tp[i] - tp_d[i]
            share = (k - before_all) / (tp_d[i] + fp_d[i])
            expected_pos = before_tp + tp_d[i] * share
            out[f"lift_top_{round(fraction * 100)}"] = float((expected_pos / k) / (n_pos / total))
        return out


METRIC_NAMES = ("auc", "average_precision", "lift_top_1", "lift_top_5", "lift_top_10")


def percentile_interval(values: np.ndarray, estimate: float | None) -> Interval:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return Interval(estimate, None, None)
    alpha = (1 - CI_LEVEL) / 2 * 100
    low, high = np.percentile(finite, [alpha, 100 - alpha])
    return Interval(estimate, float(low), float(high))


def resample_weights(
    rng: np.random.Generator, n_pos: int, n_neg: int, size: int
) -> tuple[np.ndarray, np.ndarray]:
    """Bootstrap draws as multiplicity counts, positives and negatives resampled separately.

    Stratifying by label keeps the number of positives fixed in every replicate; with a handful of
    positives an unstratified draw would sometimes contain none.
    """
    pos = rng.multinomial(n_pos, np.full(n_pos, 1 / n_pos), size=size)
    neg = rng.multinomial(n_neg, np.full(n_neg, 1 / n_neg), size=size)
    return pos.astype(float), neg.astype(float)


def bootstrap_metrics(
    problems: dict[str, RankingProblem],
    n_boot: int,
    seed: int,
    *,
    paired: tuple[tuple[str, str], ...] = (),
    chunk: int = 100,
) -> dict[str, dict[str, Interval]]:
    """Point estimates and percentile CIs per score, resampling units (suppliers) with replacement.

    All scores share the same replicates, so `paired` differences (first minus second) are valid
    paired intervals. Differences are reported under the key "a - b".
    """
    first = next(iter(problems.values()))
    label = first.label
    pos_idx, neg_idx = np.flatnonzero(label), np.flatnonzero(~label)
    rng = np.random.default_rng(seed)
    draws: dict[str, dict[str, list[float]]] = {n: {m: [] for m in METRIC_NAMES} for n in problems}
    for start in range(0, n_boot, chunk):
        wp, wn = resample_weights(rng, pos_idx.size, neg_idx.size, min(chunk, n_boot - start))
        for row in range(wp.shape[0]):
            weight = np.zeros(label.size)
            weight[pos_idx], weight[neg_idx] = wp[row], wn[row]
            for name, problem in problems.items():
                for metric, value in problem.metrics(weight).items():
                    draws[name][metric].append(value)
    result: dict[str, dict[str, Interval]] = {}
    for name, problem in problems.items():
        point = problem.metrics()
        result[name] = {m: percentile_interval(np.array(draws[name][m]), point[m]) for m in METRIC_NAMES}
    for a, b in paired:
        key = f"{a} - {b}"
        point_a, point_b = problems[a].metrics(), problems[b].metrics()
        result[key] = {
            m: percentile_interval(np.array(draws[a][m]) - np.array(draws[b][m]), point_a[m] - point_b[m])
            for m in METRIC_NAMES
        }
    return result


def permutation_pvalues_auc(problems: dict[str, RankingProblem], n_perm: int, seed: int) -> dict[str, float]:
    """One-sided p-values: share of random labelings (same number of positives) with AUC >= observed.

    The same random labelings are used for every score. This is a null distribution for "the score
    is unrelated to the label", not a confidence interval.
    """
    first = next(iter(problems.values()))
    n, n_pos = first.label.size, int(first.label.sum())
    n_neg = n - n_pos
    ranks = {name: rankdata(p.score) for name, p in problems.items()}
    observed = {name: p.metrics()["auc"] for name, p in problems.items()}
    hits = dict.fromkeys(problems, 0)
    rng = np.random.default_rng(seed)
    for _ in range(n_perm):
        chosen = rng.choice(n, size=n_pos, replace=False)
        for name, r in ranks.items():
            auc = (r[chosen].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
            hits[name] += auc >= observed[name] - 1e-12
    return {name: (h + 1) / (n_perm + 1) for name, h in hits.items()}
