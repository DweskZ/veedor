from __future__ import annotations

import copy

import pytest

from veedor.domain.signals.scoring import SIGNAL_WEIGHTS
from veedor.evaluation import backtest, coverage, data, history, report

A_EXCLUDED = {"GHOST_COMPANY_LIST", "SUPPLIER_NOT_ACTIVE"}


@pytest.fixture(scope="module")
def con(synthetic_dirs):
    connection = data.connect(*synthetic_dirs)
    data.build_process_table(connection, SIGNAL_WEIGHTS, backtest.CONTEXT_CODES)
    return connection


@pytest.fixture(scope="module")
def result(synthetic_dirs):
    run = backtest.run_backtest(*synthetic_dirs, n_boot=100, seed=1)
    run["history"] = [history.entry_from(run, "synthetic run")]
    return run


def test_score_sql_excludes_signals_and_caps():
    sql = data.score_sql(SIGNAL_WEIGHTS, A_EXCLUDED)
    assert "f_ghost_company_list" not in sql and "f_supplier_not_active" not in sql
    assert "f_single_bidder" in sql
    assert "least(100.0" in data.score_sql({"A": 80.0, "B": 80.0})


def test_held_out_score_drops_the_label_and_the_status_signal(con):
    full = data.score_sql(SIGNAL_WEIGHTS)
    held = data.score_sql(SIGNAL_WEIGHTS, A_EXCLUDED)
    rows = con.execute(
        f"SELECT ({full}), ({held}) FROM eval_process WHERE winner_name = 'POSITIVE ONE' AND f_single_bidder"
    ).fetchall()
    assert rows == [(65.0, 20.0)]  # 30 + 15 + 20 with the label, only 20 once excluded


def test_flags_agree_with_signal_codes_list(result):
    assert result["meta"]["consistency"]["processes_with_flag_mismatch"] == 0


def test_label_universe_is_companies_and_counts(result):
    primary = result["primary"]
    assert primary["n_positives"] == 4  # four companies on the list; the natural person is excluded
    assert primary["n_unlabelled"] == 40
    summary = primary["positives_summary"]
    assert summary["n_with_zero_held_out_mean"] + summary["n_with_positive_held_out_mean"] == 4
    both = result["all_suppliers"]
    assert both["n_positives"] == 5 and both["n_unlabelled"] == 45
    by_kind = result["labels"]["by_kind"]
    assert by_kind["company"]["n_suppliers_with_award"] == 4
    assert by_kind["natural_person"]["n_suppliers_with_award"] == 1


def test_leakage_full_score_separates_but_held_out_does_not(result):
    scores = result["primary"]["scores"]
    assert scores["full:mean"]["auc"]["estimate"] == pytest.approx(1.0)
    assert scores["A:mean"]["auc"]["estimate"] < 0.9
    assert "GHOST_COMPANY_LIST" in result["meta"]["variants"]["A"]["excluded"]
    assert "CONTRACT_VS_COMPANY_SIZE" in result["meta"]["variants"]["B"]["excluded"]


def test_temporal_filter_counts_survivors(result):
    # POSITIVE THREE (all awards after notification) and POSITIVE FOUR (no date) are dropped
    assert result["primary"]["n_positives"] == 4
    assert result["temporal"]["n_positives"] == 2
    assert result["all_suppliers_temporal"]["n_positives"] == 3
    assert result["labels"]["by_kind"]["company"]["processes_without_notification_date"] == 1


def test_temporal_filter_removes_post_listing_processes(con):
    score = data.score_sql(SIGNAL_WEIGHTS, A_EXCLUDED)
    kept = data.supplier_table(con, score, temporal=True)
    counts = dict(zip(kept["ruc"], kept["n_processes"], strict=True))
    assert counts["0992000002001"] == 1  # the 2020 award is after the 2019 notification
    assert counts["0992000001001"] == 3
    assert "0992000003001" not in counts and "0992000004001" not in counts
    assert counts["0993000000001"] == 3  # unlabelled suppliers are untouched


def test_per_signal_rates_and_roles(result):
    block = result["per_signal"]["all_processes"]["signals"]
    assert block["GHOST_COMPANY_LIST"]["role"] == "label"
    assert block["GHOST_COMPANY_LIST"]["rate_unlabelled"]["estimate"] == 0.0
    single = block["SINGLE_BIDDER"]
    assert single["fired_positives"] == 2
    assert single["fired_unlabelled"] == 10
    assert single["rate_positives"]["estimate"] == pytest.approx(2 / 7)
    assert single["ratio"]["estimate"] == pytest.approx((2 / 7) / (10 / 120))


def test_baselines_and_anomaly_present(result):
    assert result["primary"]["scores"]["baseline:amount"]["auc"]["estimate"] is not None
    assert result["primary"]["random_baseline"]["auc"] == 0.5
    assert "anomaly:mean" in result["anomaly"]["scores"]


def test_buyer_concentration(result):
    buyers = result["buyer_concentration"]
    assert buyers["n_distinct_buyers"] == 2
    assert buyers["positive_suppliers_sharing_a_buyer"] == 3  # three positives won at the main buyer
    assert [b["buyer"] for b in buyers["top_buyers"]] == ["Buyer 01", "Buyer 02"]
    assert buyers["top_buyers"][0]["n_processes"] > buyers["top_buyers"][1]["n_processes"]


def test_coverage_counts(synthetic_dirs):
    cov = coverage.run_coverage(*synthetic_dirs)
    assert cov["n_processes"] == sum(r["n_processes"] for r in cov["by_year"])
    assert cov["signals_fired"]["SINGLE_BIDDER"] == 12
    counts = cov["cooccurrence"]["counts"]
    pair = counts.get(
        "GHOST_COMPANY_LIST|SUPPLIER_NOT_ACTIVE", counts.get("SUPPLIER_NOT_ACTIVE|GHOST_COMPANY_LIST")
    )
    assert pair == cov["signals_fired"]["GHOST_COMPANY_LIST"]
    assert "Share of processes at 0" in report.coverage_sections(cov)


def test_report_is_generated_from_json_only(synthetic_dirs, result):
    cov = coverage.run_coverage(*synthetic_dirs)
    text = report.render(result, cov)
    headline_auc = report.ci(result["primary"]["scores"]["A:mean"]["auc"])
    assert headline_auc in text
    changed = copy.deepcopy(result)
    changed["primary"]["scores"]["A:mean"]["auc"] = {"estimate": 0.123456, "low": 0.1, "high": 0.2}
    assert "0.123 (0.100 to 0.200)" in report.render(changed, cov)
    assert "0.123 (0.100 to 0.200)" not in text


def test_variant_c_keeps_status_signal_and_status_check(result):
    assert result["meta"]["variants"]["C"]["excluded"] == [
        "GHOST_COMPANY_LIST",
        "GHOST_COMPANY_LISTED_LATER",
    ]
    assert "C:mean" in result["primary"]["scores"]
    check = result["status_signal_check"]
    assert check["n_firings"] == 7  # one per synthetic positive process with the signal
    assert check["n_firings_on_positive_processes"] == 7


def test_leave_one_buyer_out_and_summary(result):
    loo = result["leave_one_buyer_out"]
    assert loo["n_buyers_dropped_in_turn"] == 2
    row = loo["variants"]["A"]["mean"]
    assert {row["min_buyer"], row["max_buyer"]} <= {"Buyer 01", "Buyer 02"}
    assert {row["min_n_positives"], row["max_n_positives"]} <= {1, 3}
    text = report.summary_section(result)
    assert "Summary for non-specialists" in text
    assert report.ci(result["primary"]["scores"]["A:mean"]["auc"]) in text


def test_context_signals_do_not_score_and_are_reported_separately(con, synthetic_dirs, result):
    # context flags exist but the weights (hence every score) contain only risk signals
    assert "GHOST_COMPANY_LISTED_LATER" not in SIGNAL_WEIGHTS
    n_later = con.execute("SELECT sum(f_ghost_company_listed_later::INT) FROM eval_process").fetchone()[0]
    assert n_later == 7
    assert result["meta"]["consistency"]["processes_with_context_flag_mismatch"] == 0
    cov = coverage.run_coverage(*synthetic_dirs)
    assert cov["context_signals"]["fired"]["GHOST_COMPANY_LISTED_LATER"] == 7
    assert cov["context_signals"]["fired"]["CONTRACT_VS_COMPANY_SIZE_SAME_YEAR"] == 1
    assert cov["context_signals"]["n_with_context_and_risk"] == 7
    assert result["per_signal"]["all_processes"]["signals"]["GHOST_COMPANY_LISTED_LATER"]["role"] == "label"


def test_history_is_rendered_and_conclusion_comparison(synthetic_dirs, result):
    first = {"estimate": 0.4, "low": 0.3, "high": 0.6}
    entries = [
        {
            "generated_at": "t1",
            "note": "first rules",
            "headline_auc": first,
            "n_positives": 4,
            "n_unlabelled": 40,
        },
        {
            "generated_at": "t2",
            "note": "fix",
            "headline_auc": {"estimate": 0.7, "low": 0.6, "high": 0.8},
            "n_positives": 4,
            "n_unlabelled": 40,
        },
    ]
    text = report.history_section({**result, "history": entries})
    assert "first rules" in text and "0.400 (0.300 to 0.600)" in text
    assert "qualitative conclusion changed" in text
    assert "source of optimism" in text
