"""Threshold table arithmetic against published figures, and the bunching estimator on synthetic data."""

from __future__ import annotations

import numpy as np

from veedor.domain import thresholds as th
from veedor.domain.bunching import BunchingSpec, estimate_bunching


def _by_code(year: int) -> dict[str, float]:
    return {t.code: t.value_usd for t in th.thresholds_for(year)}


def test_pie_arithmetic_matches_the_published_figures() -> None:
    # Dollar figures printed by SERCOP (documented in docs/THRESHOLDS.md).
    assert _by_code(2024)["GS_INFIMA_SIE"] == 6659.36
    assert _by_code(2024)["GS_MENOR_COTIZACION"] == 66593.64
    assert _by_code(2024)["GS_COTIZACION_LICITACION"] == 499452.30
    assert _by_code(2024)["W_MENOR_COTIZACION"] == 233077.74
    assert _by_code(2023)["W_COTIZACION_LICITACION"] == 945085.97
    assert _by_code(2015)["GS_COTIZACION_LICITACION"] == 544756.76
    assert _by_code(2021)["W_MENOR_COTIZACION"] == 224562.54


def test_2026_is_fixed_and_2025_is_excluded_not_guessed() -> None:
    assert set(_by_code(2026).values()) == {10000.0}
    assert th.thresholds_for(2025) == [] and 2025 in th.EXCLUDED_YEARS
    assert th.thresholds_for(2014) == []


def test_every_threshold_has_an_official_source() -> None:
    for t in th.all_thresholds():
        assert t.source_url.startswith("https://portal.compraspublicas.gob.ec/sercop/")


def test_category_mapping() -> None:
    assert th.category_of("goods", "Menor Cuantía") == th.GOODS_SERVICES
    assert th.category_of("works", "Cotización") == th.WORKS
    assert th.category_of("services", "Lista corta") == th.CONSULTANCY
    assert th.category_of(None, "Licitación") is None


def _sample(excess: int, seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    smooth = rng.uniform(-0.2, 0.2, 6000)
    pile = rng.uniform(-0.04, 0.0, excess)
    rel = np.concatenate([smooth, pile])
    return rel, rng.integers(0, 400, rel.size)


def test_no_excess_gives_an_interval_around_zero() -> None:
    rel, buyers = _sample(0)
    out = estimate_bunching(rel, buyers, n_boot=200)
    low, high = out["excess_bins_ci"]
    assert out["status"] == "estimated" and low < 0 < high


def test_pile_below_the_threshold_is_detected() -> None:
    rel, buyers = _sample(600)
    out = estimate_bunching(rel, buyers, BunchingSpec(), n_boot=200)
    assert out["excess_bins_ci"][0] > 3 and out["excess_pct"] > 40


def test_amount_equal_to_threshold_counts_as_below() -> None:
    rel = np.concatenate([np.zeros(500), np.random.default_rng(0).uniform(-0.2, 0.2, 500)])
    out = estimate_bunching(rel, np.arange(rel.size), n_boot=50)
    assert out["observed_below"] >= 500


def test_small_windows_are_not_estimated() -> None:
    out = estimate_bunching(np.linspace(-0.1, 0.1, 50), np.arange(50))
    assert out["status"] == "insufficient_data" and "excess_bins" not in out
