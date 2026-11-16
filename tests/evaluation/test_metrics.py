from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import average_precision_score, roc_auc_score

from veedor.evaluation.metrics import (
    RankingProblem,
    bootstrap_metrics,
    permutation_pvalues_auc,
)


def test_auc_and_ap_known_values():
    problem = RankingProblem(np.array([0.9, 0.8, 0.7, 0.1]), np.array([1, 0, 1, 0]))
    m = problem.metrics()
    assert m["auc"] == pytest.approx(0.75)  # 3 of 4 positive-negative pairs ordered correctly
    assert m["average_precision"] == pytest.approx((1 + 2 / 3) / 2)


def test_perfect_reversed_and_constant_scores():
    label = np.array([1, 1, 0, 0, 0, 0])
    assert RankingProblem(np.array([9, 8, 3, 2, 1, 0.0]), label).metrics()["auc"] == 1.0
    assert RankingProblem(np.array([0, 1, 3, 2, 5, 4.0]), label).metrics()["auc"] == 0.0
    constant = RankingProblem(np.zeros(6), label).metrics()
    assert constant["auc"] == pytest.approx(0.5)
    assert constant["average_precision"] == pytest.approx(label.mean())
    assert constant["lift_top_10"] == pytest.approx(1.0)


def test_matches_scikit_learn_with_many_ties():
    rng = np.random.default_rng(0)
    score = rng.integers(0, 5, 500).astype(float)
    label = rng.random(500) < 0.1
    m = RankingProblem(score, label).metrics()
    assert m["auc"] == pytest.approx(roc_auc_score(label, score))
    assert m["average_precision"] == pytest.approx(average_precision_score(label, score))


def test_lift_top_fraction_and_tie_splitting():
    # 100 units, 10 positives all ranked in the top 10 -> precision 1 in top 10 %, base rate 0.1
    score = np.arange(100, 0, -1).astype(float)
    label = np.zeros(100, dtype=bool)
    label[:10] = True
    m = RankingProblem(score, label).metrics()
    assert m["lift_top_10"] == pytest.approx(10.0)
    assert m["lift_top_5"] == pytest.approx(10.0)
    assert m["lift_top_1"] == pytest.approx(10.0)
    # one big tie: positives are spread proportionally, lift 1 at every cut-off
    flat = RankingProblem(np.zeros(100), label).metrics()
    assert flat["lift_top_1"] == pytest.approx(1.0)


def test_weights_equal_repetition():
    score = np.array([0.9, 0.8, 0.7, 0.1, 0.4])
    label = np.array([1, 0, 1, 0, 0])
    weighted = RankingProblem(score, label).metrics(np.array([2.0, 1, 1, 1, 3]))
    repeated = RankingProblem(np.repeat(score, [2, 1, 1, 1, 3]), np.repeat(label, [2, 1, 1, 1, 3])).metrics()
    assert weighted == pytest.approx(repeated)


def _separated(n_pos: int = 8, n_neg: int = 200) -> RankingProblem:
    rng = np.random.default_rng(1)
    score = np.concatenate([rng.normal(3, 1, n_pos), rng.normal(0, 1, n_neg)])
    return RankingProblem(score, np.arange(n_pos + n_neg) < n_pos)


def test_bootstrap_is_seeded_and_brackets_the_estimate():
    problems = {"s": _separated()}
    first = bootstrap_metrics(problems, 200, seed=7)["s"]["auc"]
    again = bootstrap_metrics(problems, 200, seed=7)["s"]["auc"]
    other = bootstrap_metrics(problems, 200, seed=8)["s"]["auc"]
    assert first == again
    assert first != other
    assert first.low <= first.estimate <= first.high
    assert first.low > 0.5  # clearly separated scores


def test_bootstrap_interval_covers_chance_for_noise_and_paired_difference():
    rng = np.random.default_rng(2)
    label = np.arange(300) < 10
    problems = {
        "noise": RankingProblem(rng.random(300), label),
        "noise2": RankingProblem(rng.random(300), label),
    }
    result = bootstrap_metrics(problems, 300, seed=3, paired=(("noise", "noise2"),))
    assert result["noise"]["auc"].low < 0.5 < result["noise"]["auc"].high
    diff = result["noise - noise2"]["auc"]
    assert diff.estimate == pytest.approx(result["noise"]["auc"].estimate - result["noise2"]["auc"].estimate)


def test_permutation_pvalue_small_for_signal_large_for_noise():
    rng = np.random.default_rng(4)
    label = np.arange(200) < 8
    signal = RankingProblem(label * 3.0 + rng.normal(size=200), label)
    noise = RankingProblem(rng.normal(size=200), label)
    p = permutation_pvalues_auc({"signal": signal, "noise": noise}, 500, seed=5)
    assert p["signal"] < 0.01
    assert p["noise"] > 0.05


def test_rejects_nan_and_single_class():
    with pytest.raises(ValueError):
        RankingProblem(np.array([np.nan, 1.0]), np.array([True, False]))
    with pytest.raises(ValueError):
        RankingProblem(np.array([1.0, 2.0]), np.array([True, True])).metrics()
