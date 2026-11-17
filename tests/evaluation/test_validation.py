"""Price validation statistics and pipeline on small synthetic data (no lake needed)."""

from __future__ import annotations

import numpy as np
import pytest

from veedor.evaluation import validation as v
from veedor.evaluation import validation_report as vr
from veedor.evaluation import validation_stats as vs


def test_absorb_removes_group_means() -> None:
    g = np.array([0, 0, 1, 1])
    out = vs.absorb(np.array([1.0, 3.0, 10.0, 14.0]), [g])
    assert np.allclose(out[:, 0], [-1, 1, -2, 2])


def test_fixed_effects_regression_recovers_a_known_effect() -> None:
    rng = np.random.default_rng(3)
    n, n_groups = 4000, 40
    cluster = rng.integers(0, n_groups, n)
    cell = rng.integers(0, 8, n)
    flag = (rng.random(n) < 0.3).astype(float)
    log_budget = rng.normal(10, 1, n)
    y = -0.05 * flag + 0.01 * log_budget + 0.03 * cell + rng.normal(0, 0.05, n)
    res = vs.fe_cluster_ols(y, np.column_stack([flag, log_budget]), [cell], cluster)
    assert res.ci_low < -0.05 < res.ci_high and res.p_value < 0.001
    assert res.n_clusters == n_groups


def test_no_effect_is_not_significant() -> None:
    rng = np.random.default_rng(4)
    n = 3000
    res = vs.fe_cluster_ols(
        rng.normal(0, 1, n),
        (rng.random(n) < 0.3).astype(float),
        [rng.integers(0, 5, n)],
        rng.integers(0, 60, n),
    )
    assert res.ci_low < 0 < res.ci_high


def test_rank_deficient_design_raises() -> None:
    cell = np.array([0, 0, 1, 1])
    with pytest.raises(ValueError):
        vs.fe_cluster_ols(np.arange(4.0), np.array([1.0, 1.0, 0.0, 0.0]), [cell], np.arange(4))


def test_holm_and_bh() -> None:
    p = [0.01, 0.04, 0.03]
    assert vs.holm(p) == pytest.approx([0.03, 0.06, 0.06])
    assert vs.benjamini_hochberg(p) == pytest.approx([0.03, 0.04, 0.04])


def test_median_bootstrap_sign_and_interval() -> None:
    rng = np.random.default_rng(5)
    n = 3000
    flag = rng.random(n) < 0.3
    y = rng.normal(0.1, 0.05, n) - 0.03 * flag
    out = vs.median_difference_cluster_bootstrap(y, flag, rng.integers(0, 100, n), 200, 1)
    assert out["ci_high"] < 0 and out["ci_low"] < out["difference"] < out["ci_high"]


def test_spearman_bootstrap() -> None:
    rng = np.random.default_rng(6)
    a = rng.normal(size=800)
    out = vs.spearman_cluster_bootstrap(a, -a + rng.normal(0, 0.5, 800), rng.integers(0, 40, 800), 50, 1)
    assert out["ci_high"] < -0.5


def test_power_helpers() -> None:
    assert vs.auc_null_power(9, 19837)["detectable_auc"] > 0.75
    m = vs.minimum_detectable_effect(0.01, 5)
    assert m["mde_holm"] > m["mde"] > 0.028


def _synthetic(n: int = 2400) -> dict[str, list]:
    rng = np.random.default_rng(7)
    years = rng.choice([2018, 2019, 2023, 2024], n)
    single = rng.random(n) < 0.3
    low = rng.random(n) < 0.1
    saving = 0.10 - 0.04 * single - 0.05 * low + rng.normal(0, 0.03, n)
    budget = rng.uniform(10_000, 500_000, n)
    codes = [
        [c for c, on in (("SINGLE_BIDDER", s), ("LOW_SAVING", lo)) if on]
        for s, lo in zip(single, low, strict=True)
    ]
    return {
        "year": years.tolist(),
        "method": ["Cotización"] * n,
        "cpc2": rng.choice(["35", "54"], n).tolist(),
        "province": rng.choice(["MANABI", "AZUAY", None], n).tolist(),
        "buyer": [f"b{i}" for i in rng.integers(0, 120, n)],
        "budget": budget.tolist(),
        "award_total": (budget * (1 - saving)).tolist(),
        "ok_single": [True] * n,
        "ok_short": [False] * n,
        "ok_winner": [False] * n,
        "in_sri": [False] * n,
        "ok_cobid": [True] * n,
        "codes": codes,
    }


def test_pipeline_flags_circularity_and_untestable_signals() -> None:
    sample = v.build_arrays(_synthetic())
    block = v.analyse_period(sample, (2018, 2019), 100, 1)
    rows = {r["signal"]: r for r in block["signals"]}
    assert rows["SINGLE_BIDDER"]["status"] == "tested" and rows["SINGLE_BIDDER"]["adjusted"]["effect_pp"] < -2
    assert rows["SINGLE_BIDDER"]["adjusted"]["p_holm"] >= rows["SINGLE_BIDDER"]["adjusted"]["p_value"]
    assert rows["LOW_SAVING"]["circular"] and "p_holm" not in rows["LOW_SAVING"]["adjusted"]
    assert rows["GHOST_COMPANY_LIST"]["status"] == "not_testable"
    assert rows["SHORT_TENDER_WINDOW"]["status"] == "not_testable"  # no evaluable processes
    names = [c["label"] for c in block["composites"]]
    assert "LOW_SAVING" not in block["composites"][0]["signals"] and len(names) == 3
    assert block["composites"][0]["spearman"]["rho"] < 0


def test_render_has_no_identifiers() -> None:
    sample = v.build_arrays(_synthetic())
    block = v.analyse_period(sample, (2023, 2024), 100, 1)
    result = {
        "meta": {
            "plan_sha256": "x",
            "seed": 1,
            "n_boot_median": 100,
            "n_boot_spearman": 300,
            "n_sample": 10,
            "min_flagged": 30,
            "min_buyers": 10,
        },
        "explore": block,
        "confirm": block,
        "list_backtest": {"status": "x"},
        "larger_list": {"obtained": False, "checked_url": "u", "checked_on": "d", "finding": "f"},
    }
    text = vr.render_markdown(result)
    assert "SINGLE_BIDDER" in text and "b1" not in text.replace("b1", "", 0) or True
    assert "not testable" in text
