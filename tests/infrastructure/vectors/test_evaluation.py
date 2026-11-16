"""Statistics and rendering of the CPC-proxy evaluation (no database)."""

from __future__ import annotations

import numpy as np

from veedor.infrastructure.vectors import evaluation as ev


def test_agreement_counts_matching_codes_and_ignores_empty() -> None:
    assert ev.agreement("53210", ["53210", "53210", "35210", ""]) == 0.5
    assert ev.agreement("", ["53210"]) == 0.0
    assert ev.agreement("53210", []) == 0.0


def test_prefix_code() -> None:
    assert ev.prefix_code("532100111", 5) == "53210"
    assert ev.prefix_code("532100111", None) == "532100111"
    assert ev.prefix_code(None, 5) == ""


def test_bootstrap_is_seeded_and_brackets_the_mean() -> None:
    values = np.array([0.0, 0.5, 1.0, 1.0, 0.2, 0.8] * 20)
    a, b = ev.bootstrap(values), ev.bootstrap(values)
    assert a == b and a.low <= a.mean <= a.high
    assert a.mean == values.mean()
    assert ev.bootstrap(values, seed=1).low != a.low or ev.bootstrap(values, seed=1).high != a.high


def test_bootstrap_of_a_constant_is_degenerate() -> None:
    interval = ev.bootstrap(np.ones(30))
    assert (interval.mean, interval.low, interval.high) == (1.0, 1.0, 1.0)


def _sample_result() -> dict:
    def iv(m: float) -> dict:
        return {"mean": m, "ci95_low": m - 0.01, "ci95_high": m + 0.01}

    variant = {"with_cpc_text": iv(0.9), "without_cpc_text": iv(0.6),
               "paired_difference_with_minus_without": iv(0.3)}  # fmt: skip
    return {
        "generated_on": "2026-11-16", "seed": 42, "bootstrap_resamples": 2000, "model": "m", "dimension": 256,
        "index": {"rows": 1234},
        "full_index": {
            "queries": 1000, "k": 10,
            "agreement_at_10_cpc5": {"embedding": iv(0.8), "random_neighbour_baseline": iv(0.02),
                                     "exact_cpc_baseline": iv(1.0)},
            "embedding_neighbours_sharing_exact_cpc9": iv(0.5),
            "exact_cpc_baseline_queries_with_fewer_than_10_candidates": 7,
        },
        "pool_experiment": {
            "pool_size": 500, "queries": 100, "all_neighbours": variant,
            "identical_description_neighbours_removed": variant,
            "random_neighbour_baseline": iv(0.03), "exact_cpc_baseline": iv(1.0),
        },
        "latency": {"queries": 200, "p50_ms": 5.0, "p95_ms": 9.0, "max_ms": 20.0},
    }  # fmt: skip


def test_render_uses_only_numbers_from_the_result() -> None:
    text = ev.render_markdown(_sample_result())
    assert text.startswith(ev.DOC_BEGIN) and text.endswith(ev.DOC_END)
    assert "80.0 % [79.0, 81.0]" in text and "1,234 rows" in text and "p95 9.0 ms" in text


def test_update_docs_replaces_only_the_generated_block(tmp_path) -> None:
    doc = tmp_path / "VECTOR_SEARCH.md"
    doc.write_text(f"intro\n{ev.DOC_BEGIN}\nold\n{ev.DOC_END}\noutro\n", encoding="utf-8")
    assert ev.update_docs(doc, ev.render_markdown(_sample_result()))
    new = doc.read_text(encoding="utf-8")
    assert new.startswith("intro\n") and new.endswith("outro\n") and "old" not in new
    assert not ev.update_docs(tmp_path / "missing.md", "x")
    doc.write_text("no markers", encoding="utf-8")
    assert not ev.update_docs(doc, "x")
