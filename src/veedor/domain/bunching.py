"""Excess mass just below a threshold, against a smooth counterfactual (a description, not a verdict).

Amounts are expressed relative to the threshold, ``x = amount / T - 1``. They are counted in bins of
``bin_width`` over ``[-window, +window]`` (a bin is open on the left and closed on the right, so an
amount equal to the threshold counts as "at or below"). A polynomial is fitted to the bins outside the
zone ``[-zone, +zone]``; its prediction inside the zone is the counterfactual. The excess below is the
observed minus predicted count in the zone's lower half, the missing mass above the same in its upper
half. The interval resamples clusters (buyers), because one buyer's purchases are not independent.

Bunching can come from contract splitting or from real purchasing distortion; neither is identified.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MIN_WINDOW_COUNT = 200


@dataclass(frozen=True, slots=True)
class BunchingSpec:
    window: float = 0.20
    bin_width: float = 0.01
    zone: float = 0.05
    degree: int = 3


def _bin_index(x: np.ndarray, spec: BunchingSpec) -> np.ndarray:
    n_bins = round(2 * spec.window / spec.bin_width)
    idx = np.ceil((x + spec.window) / spec.bin_width - 1e-9).astype(int) - 1
    keep = (idx >= 0) & (idx < n_bins)
    return np.where(keep, idx, -1)


def _estimate_from_counts(counts: np.ndarray, spec: BunchingSpec) -> dict[str, float]:
    n_bins = counts.size
    centers = -spec.window + spec.bin_width * (np.arange(n_bins) + 0.5)
    in_zone = np.abs(centers) <= spec.zone
    fit_x = centers[~in_zone] / spec.window
    coef = np.polyfit(fit_x, counts[~in_zone], spec.degree)
    predicted = np.maximum(np.polyval(coef, centers / spec.window), 0.0)
    below = in_zone & (centers < 0)
    above = in_zone & (centers > 0)
    mean_pred_below = predicted[below].mean()
    return {
        "observed_below": float(counts[below].sum()),
        "expected_below": float(predicted[below].sum()),
        "excess_bins": float((counts[below] - predicted[below]).sum() / mean_pred_below)
        if mean_pred_below > 0
        else float("nan"),
        "excess_pct": float((counts[below].sum() - predicted[below].sum()) / predicted[below].sum() * 100)
        if predicted[below].sum() > 0
        else float("nan"),
        "observed_above": float(counts[above].sum()),
        "expected_above": float(predicted[above].sum()),
        "missing_above_pct": float(
            (predicted[above].sum() - counts[above].sum()) / predicted[above].sum() * 100
        )
        if predicted[above].sum() > 0
        else float("nan"),
    }


def estimate_bunching(
    relative: np.ndarray,
    clusters: np.ndarray,
    spec: BunchingSpec = BunchingSpec(),  # noqa: B008 - frozen dataclass
    n_boot: int = 500,
    seed: int = 20260101,
) -> dict:
    """Bunching estimate with a cluster-bootstrap interval; ``status`` says when it is not reported."""
    relative = np.asarray(relative, dtype=float)
    idx = _bin_index(relative, spec)
    inside = idx >= 0
    n_window = int(inside.sum())
    result: dict = {"n_window": n_window}
    if n_window < MIN_WINDOW_COUNT:
        result["status"] = "insufficient_data"
        return result
    n_bins = round(2 * spec.window / spec.bin_width)
    counts = np.bincount(idx[inside], minlength=n_bins).astype(float)
    try:
        point = _estimate_from_counts(counts, spec)
    except (np.linalg.LinAlgError, ValueError):
        result["status"] = "fit_failed"
        return result
    codes = np.unique(np.asarray(clusters)[inside], return_inverse=True)[1]
    n_clusters = int(codes.max()) + 1
    matrix = np.zeros((n_clusters, n_bins))
    np.add.at(matrix, (codes, idx[inside]), 1.0)
    rng = np.random.default_rng(seed)
    reps = {"excess_bins": [], "excess_pct": [], "missing_above_pct": []}
    for _ in range(n_boot):
        picked = rng.integers(0, n_clusters, n_clusters)
        try:
            est = _estimate_from_counts(matrix[picked].sum(axis=0), spec)
        except (np.linalg.LinAlgError, ValueError):
            continue
        for key in reps:
            reps[key].append(est[key])
    result.update(point)
    for key, values in reps.items():
        low, high = np.nanpercentile(values, [2.5, 97.5]) if values else (float("nan"), float("nan"))
        result[f"{key}_ci"] = [float(low), float(high)]
    result["status"] = "estimated"
    return result
