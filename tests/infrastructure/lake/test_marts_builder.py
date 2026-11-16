"""Signals v1 on a tiny synthetic lake: each rule fires and stays quiet in the right cases."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures" / "lake"))

from synthetic_lake import BASE_DAY, award, process, stamp, tenderer, write_lake  # noqa: E402

from veedor.domain.signals import SIGNAL_WEIGHTS, risk_score  # noqa: E402
from veedor.infrastructure.lake.marts_builder import LakeNotFoundError, build_marts  # noqa: E402

REGISTRY_CODES = {
    "NEW_SUPPLIER",
    "SUPPLIER_NOT_ACTIVE",
    "GHOST_COMPANY_LIST",
    "GHOST_COMPANY_LISTED_LATER",
    "CONTRACT_VS_COMPANY_SIZE",
    "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR",
}
COMPANY = "1790000000001"
NATURAL = "0102030405001"
PUBLIC = "1760001120001"


def day(offset: int) -> str:
    return stamp(BASE_DAY + timedelta(days=offset))


def windowed(ocid: str, method: str, days: int | None, **fields: Any) -> dict[str, Any]:
    end = stamp(BASE_DAY + timedelta(days=days)) if days is not None else None
    return process(ocid, method=method, tender_start=stamp(BASE_DAY), tender_end=end, **fields)


def single_bidder_rows() -> list[dict[str, Any]]:
    by_design = [process(f"DES-g{i}", method="M-DESIGN", category="goods", n_tenderers=1) for i in range(35)]
    mixed = [
        process(f"DES-w{i}", method="M-DESIGN", category="works", n_tenderers=1 if i < 10 else 3)
        for i in range(35)
    ]
    return (
        by_design
        + mixed
        + [
            process("SB-1", n_tenderers=1),
            process("SB-2", n_tenderers=2),
            process("SB-DIRECT", n_tenderers=1, method_group="direct", method="Bienes y Servicios únicos"),
            process("SB-CAT", n_tenderers=None, method_group="catalogue", method="Catálogo electrónico - x"),
            process("SB-NULL", n_tenderers=None),
        ]
    )


def short_window_rows() -> list[dict[str, Any]]:
    rows = [windowed(f"SW-{i}", "M-SHORT", i + 3) for i in range(40)]
    rows += [windowed(f"SMALL-{i}", "M-SMALL", i + 1) for i in range(10)]
    rows += [windowed(f"NOEND-{i}", "M-NOEND", None) for i in range(40)]
    return rows


def low_saving_rows() -> list[dict[str, Any]]:
    ratios = [0.5 + 0.01 * i for i in range(37)] + [0.985, 0.995, 0.995]
    rows = [process(f"LS-{i}", method="M-SAVE", award_total=1000 * r) for i, r in enumerate(ratios)]
    rows += [process(f"MASS-{i}", method="M-MASS", award_total=1000.0) for i in range(40)]
    return rows


def concentration_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plan = [  # (ocid, buyer, supplier, amount, method_group)
        ("BC1-a", "BC1", "1790000000011", 25_000, "competitive"),
        ("BC1-b", "BC1", "1790000000011", 25_000, "competitive"),
        ("BC1-c", "BC1", "1790000000012", 25_000, "competitive"),
        ("BC1-d", "BC1", "1790000000013", 25_000, "competitive"),
        ("BC2-a", "BC2", "1790000000011", 50_000, "competitive"),
        ("BC2-b", "BC2", "1790000000012", 20_000, "competitive"),
        ("BC2-c", "BC2", "1790000000013", 20_000, "competitive"),
        ("BC3-a", "BC3", "1790000000011", 150_000, "competitive"),
        ("BC3-b", "BC3", "1790000000012", 50_000, "competitive"),
        ("BC5-a", "BC5", "1790000000011", 90_000, "competitive"),
        ("BC5-b", "BC5", "1790000000012", 10_000, "competitive"),
        ("BC5-c", "BC5", "1790000000013", 10_000, "competitive"),
        ("BC5-d", "BC5", "1790000000014", 10_000, "competitive"),
        *[(f"BC4-{i}", "BC4", "1790000000011", 100_000, "catalogue") for i in range(4)],
    ]
    procs = [
        process(o, buyer_ruc=f"17{b[2:]}00000000"[:13], method="M-BC", method_group=g, award_total=a)
        for o, b, _, a, g in plan
    ]
    awards = [award(o, s, float(a)) for o, _, s, a, _ in plan]
    return procs, awards


def direct_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plan = [  # (ocid, supplier, cpc, day offset)
        *[(f"RD1-{i}", "1790000000021", "53290111", d) for i, d in enumerate((0, 40, 80, 300))],
        *[(f"RD2-{i}", "1790000000022", "53290111", d) for i, d in enumerate((0, 10))],
        ("RD1-other-cpc", "1790000000021", "99999111", 5),
        *[(f"RD3-{i}", "1790000000023", "53290111", d) for i, d in enumerate((0, 45, 90, 135))],
        *[(f"RD4-{i}", "1790000000024", "53290111", d) for i, d in enumerate((0, 60, 120, 180))],
    ]
    procs = [
        process(
            o,
            buyer_ruc="1760000000099",
            method="Bienes y Servicios únicos",
            method_group="direct",
            n_tenderers=1,
            main_cpc=c,
            first_award_date=day(d),
        )
        for o, _, c, d in plan
    ]
    return procs, [award(o, s, 100.0, day(d)) for o, s, _, d in plan]


def cobidder_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    procs, awards, tenderers = [], [], []
    for buyer, winner, loser, meetings in (
        ("1760000000031", "1790000000031", "1790000000032", 5),
        ("1760000000033", "1790000000034", "1790000000035", 4),
    ):
        for i in range(meetings):
            ocid = f"RC-{buyer[-2:]}-{i}"
            procs.append(process(ocid, buyer_ruc=buyer, method="M-RC"))
            awards.append(award(ocid, winner))
            tenderers += [tenderer(ocid, winner), tenderer(ocid, loser), tenderer(ocid, "1790000000039")]
    return procs, awards, tenderers


def winner_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    procs = [process("W-1", award_total=900.0), process("W-2"), process("W-3")]
    awards = [
        award("W-1", COMPANY, 800.0),
        award("W-1", NATURAL, 100.0),
        award("W-2", NATURAL, 500.0),
        award("W-3", PUBLIC, 500.0),
    ]
    return procs, awards


@pytest.fixture(scope="module")
def core(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("core")
    bc_procs, bc_awards = concentration_rows()
    rd_procs, rd_awards = direct_rows()
    rc_procs, rc_awards, rc_tenderers = cobidder_rows()
    w_procs, w_awards = winner_rows()
    processes = (
        single_bidder_rows() + short_window_rows() + low_saving_rows() + bc_procs + rd_procs
        + rc_procs + w_procs
    )  # fmt: skip
    write_lake(
        root / "lake",
        processes,
        bc_awards + rd_awards + rc_awards + w_awards,
        rc_tenderers,
    )
    summary = build_marts(root / "lake", root / "marts")
    return root / "marts", summary


def fired(marts: Path, code: str) -> set[str]:
    path = str(marts / "process_signals.parquet")
    rows = duckdb.execute(f"SELECT ocid FROM read_parquet('{path}') WHERE signal_code = ?", [code]).fetchall()
    return {r[0] for r in rows}


def scores(marts: Path) -> dict[str, dict[str, Any]]:
    path = str(marts / "process_scores.parquet")
    cursor = duckdb.execute(f"SELECT * FROM read_parquet('{path}')")
    names = [c[0] for c in cursor.description]
    return {row[0]: dict(zip(names, row, strict=True)) for row in cursor.fetchall()}


def test_single_bidder_only_in_competitive_scope(core):
    marts, _ = core
    assert fired(marts, "SINGLE_BIDDER") == {"SB-1"} | {f"DES-w{i}" for i in range(10)}


def test_single_bidder_skips_cells_that_are_single_bidder_by_design(core):
    marts, summary = core
    assert not {o for o in fired(marts, "SINGLE_BIDDER") if o.startswith("DES-g")}
    excluded = summary["signal_details"]["SINGLE_BIDDER"]["excluded_by_design"]
    assert excluded == [{"method": "M-DESIGN", "category": "goods", "processes": 35}]


def test_short_tender_window_uses_method_year_percentile(core):
    marts, summary = core
    days = np.arange(3, 43, dtype=float)
    p05 = float(np.percentile(days, 5))
    expected = {f"SW-{i}" for i in range(40) if days[i] < p05}
    assert fired(marts, "SHORT_TENDER_WINDOW") == expected == {"SW-0", "SW-1"}
    row = next(
        t
        for t in summary["thresholds"]
        if t["signal_code"] == "SHORT_TENDER_WINDOW" and t["method"] == "M-SHORT"
    )
    assert row["threshold"] == pytest.approx(p05)
    assert row["n"] == 40 and row["status"] == "used"


def test_short_window_not_evaluated_without_dates_or_in_small_groups(core):
    marts, summary = core
    fired_ids = fired(marts, "SHORT_TENDER_WINDOW")
    assert not {o for o in fired_ids if o.startswith(("NOEND", "SMALL"))}
    small = next(t for t in summary["thresholds"] if t["method"] == "M-SMALL")
    assert small["status"] == "skipped_small_group"
    short = [t for t in summary["thresholds"] if t["signal_code"] == "SHORT_TENDER_WINDOW"]
    assert not [t for t in short if t["method"] == "M-NOEND"]


def test_low_saving_needs_percentile_and_floor(core):
    marts, summary = core
    assert fired(marts, "LOW_SAVING") == {"LS-38", "LS-39"}  # 0.985 stays below the 0.99 floor
    row = next(
        t for t in summary["thresholds"] if t["signal_code"] == "LOW_SAVING" and t["method"] == "M-SAVE"
    )
    assert row["threshold"] == pytest.approx(0.99) and row["status"] == "used"


def test_low_saving_skipped_when_percentile_is_a_mass_point(core):
    marts, summary = core
    row = next(
        t for t in summary["thresholds"] if t["signal_code"] == "LOW_SAVING" and t["method"] == "M-MASS"
    )
    assert row["status"] == "skipped_mass_point" and row["share_flagged"] == 1.0
    assert not {o for o in fired(marts, "LOW_SAVING") if o.startswith("MASS")}


def test_buyer_concentration_ignores_a_single_dominant_process(core):
    marts, _ = core
    assert not {o for o in fired(marts, "BUYER_CONCENTRATION") if o.startswith("BC5")}  # 75 % in one award


def test_buyer_concentration_thresholds(core):
    marts, _ = core
    assert fired(marts, "BUYER_CONCENTRATION") == {"BC1-a", "BC1-b"}


def test_buyer_concentration_evidence_has_the_facts(core):
    marts, _ = core
    path = str(marts / "process_signals.parquet")
    value, threshold, evidence = duckdb.execute(
        f"SELECT value, threshold, evidence_json FROM read_parquet('{path}') WHERE ocid = 'BC1-a' "
        "AND signal_code = 'BUYER_CONCENTRATION'"
    ).fetchone()
    assert value == pytest.approx(0.5) and threshold == 0.3
    facts = (
        '"supplier_amount":50000', '"buyer_total":100000', '"year":2020', '"n_awards_buyer_year":4',
        '"supplier_awards":2', '"largest_supplier_process_share":0.25',
    )  # fmt: skip
    for fact in facts:
        assert fact in evidence


def test_repeated_direct_awards_window_logic(core):
    marts, _ = core
    expected = {"RD1-0", "RD1-1", "RD1-2"} | {f"RD3-{i}" for i in range(4)}
    assert fired(marts, "REPEATED_DIRECT_AWARDS") == expected


def test_recurring_cobidders_needs_five_meetings(core):
    marts, _ = core
    assert fired(marts, "RECURRING_COBIDDERS") == {f"RC-31-{i}" for i in range(5)}


def test_winner_is_largest_award_and_kind_follows_ruc(core):
    marts, _ = core
    by_ocid = scores(marts)
    assert (by_ocid["W-1"]["winner_ruc"], by_ocid["W-1"]["winner_kind"]) == (COMPANY, "company")
    assert by_ocid["W-2"]["winner_kind"] == "natural_person"
    assert by_ocid["W-3"]["winner_kind"] == "public_entity"
    assert by_ocid["SB-1"]["winner_ruc"] is None and by_ocid["SB-1"]["winner_kind"] == "unknown"


def test_risk_score_matches_domain_function_for_every_process(core):
    marts, _ = core
    rows = scores(marts)
    for row in rows.values():
        assert row["risk_score"] == risk_score(row["signal_codes"])
        assert row["n_signals"] == len(row["signal_codes"])
    assert rows["SB-1"]["risk_score"] == SIGNAL_WEIGHTS["SINGLE_BIDDER"]
    assert rows["SB-2"]["risk_score"] == 0.0 and rows["SB-2"]["signal_codes"] == []


def test_signal_rows_are_unique_per_process_and_code(core):
    marts, _ = core
    path = str(marts / "process_signals.parquet")
    total, distinct = duckdb.execute(
        f"SELECT count(*), count(DISTINCT (ocid, signal_code)) FROM read_parquet('{path}')"
    ).fetchone()
    assert total == distinct > 0


def test_context_columns_exist_and_are_empty_without_registries(core):
    marts, _ = core
    rows = scores(marts)
    assert all(r["n_context_signals"] == 0 and r["context_signal_codes"] == [] for r in rows.values())
    path = str(marts / "process_signals.parquet")
    kinds = duckdb.execute(f"SELECT DISTINCT kind FROM read_parquet('{path}')").fetchall()
    assert kinds == [("risk",)]


def test_summary_reports_rows_fired_counts_and_missing_registries(core):
    marts, summary = core
    assert summary["marts_rows"]["process_signals"] == sum(
        s["fired"] for s in summary["signals"].values() if s["status"] == "computed"
    )
    assert summary["lake_rows"]["processes"] == summary["marts_rows"]["process_scores"]
    assert set(summary["signals_skipped"]) == REGISTRY_CODES
    for code in REGISTRY_CODES:
        assert summary["signals"][code]["status"] == "not_computed"
        assert summary["signals"][code]["reason"].startswith("not computed: source table missing")
        assert fired(marts, code) == set()
    assert (marts / "build_summary.json").is_file()


def test_missing_core_table_raises(tmp_path):
    with pytest.raises(LakeNotFoundError):
        build_marts(tmp_path / "lake", tmp_path / "marts")
