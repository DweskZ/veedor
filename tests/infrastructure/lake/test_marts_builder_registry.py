"""Registry-dependent signals, score capping and the anomaly score, on synthetic lakes."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures" / "lake"))

from synthetic_lake import BASE_DAY, award, process, write_lake, write_table  # noqa: E402

from veedor.domain.signals import risk_score  # noqa: E402
from veedor.infrastructure.lake.marts_builder import build_marts  # noqa: E402

AWARD_DAY = BASE_DAY + timedelta(days=30)


def sri(
    ruc: str,
    status: str = "ACTIVO",
    start_offset: int = -1000,
    suspended: int | None = None,
    restarted: int | None = None,
) -> dict[str, Any]:
    start = AWARD_DAY + timedelta(days=start_offset)

    def shifted(offset: int | None) -> str | None:
        return None if offset is None else (AWARD_DAY + timedelta(days=offset)).isoformat()

    return {
        "ruc": ruc, "legal_name": f"Proveedor {ruc}", "status": status, "taxpayer_type": None,
        "activity_start_date": start.isoformat(), "suspension_date": shifted(suspended),
        "restart_date": shifted(restarted),
        "ciiu_code": None, "activity": None, "province": None, "source_file": "synthetic",
    }  # fmt: skip


def case(ocid: str, ruc: str, amount: float = 900.0, **fields: Any) -> tuple[dict, dict]:
    return process(ocid, award_total=amount, **fields), award(ocid, ruc, amount)


@pytest.fixture(scope="module")
def registry_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("registry")
    cases = [
        case("N-fire", "1790000000101"),
        case("N-old", "1790000000102"),
        case("N-179", "1790000000103"),
        case("N-180", "1790000000104"),
        case("N-after", "1790000000105"),
        case("N-catalogue", "1790000000106", method_group="catalogue", method="Catálogo electrónico - x"),
        case("A-susp", "1790000000107"),
        case("A-active", "1790000000108"),
        case("A-unknown", "1790000000109"),
        case("A-before", "1790000000118"),
        case("A-after", "1790000000119"),
        case("A-same-day", "1790000000120"),
        case("A-restart", "1790000000121"),
        case("G-cat", "1790000000110", method_group="catalogue", method="Catálogo electrónico - x"),
        case("S-fire", "1790000000111", 3500.0),
        case("S-equal", "1790000000112", 3000.0),
        case("S-zero", "1790000000113", 5000.0),
        case("S-latest", "1790000000114", 3500.0),
        case("S-later", "1790000000116", 3500.0),
        case("S-dup", "1790000000117", 2500.0),
        case("S-same", "1790000000122", 3500.0),
        case("S-prior", "1790000000123", 3500.0),
        case("G-nodate", "1790000000124"),
        case("NAT-1", "0102030405001", 3500.0),
        case("NAT-2", "12345", 3500.0),
        case("NAT-3", "0102030406001"),
        case("PUB-1", "1760001120001"),
    ]
    # A process stacking many signals, to prove the score is capped at 100.
    capb = "1760000000777"
    cases += [
        case("CAP-1", "1790000000115", 40_000.0, buyer_ruc=capb, n_tenderers=1),
        case("CAP-2", "1790000000115", 40_000.0, buyer_ruc=capb),
        case("CAP-3", "1790000000115", 40_000.0, buyer_ruc=capb),
        case("CAP-4", "1790000000125", 30_000.0, buyer_ruc=capb),
        case("CAP-5", "1790000000126", 30_000.0, buyer_ruc=capb),
    ]
    write_lake(root / "lake", [c[0] for c in cases], [c[1] for c in cases])
    lake = root / "lake"
    write_table(lake, "suppliers_sri", [
        sri("1790000000101", start_offset=-76),
        sri("1790000000102", start_offset=-400),
        sri("1790000000103", start_offset=-179),
        sri("1790000000104", start_offset=-180),
        sri("1790000000105", start_offset=+20),
        sri("1790000000106", start_offset=-10),
        sri("1790000000107", status="SUSPENDIDO"),
        sri("1790000000108", status="ACTIVO"),
        sri("0102030405001", status="SUSPENDIDO", start_offset=-50, suspended=-10),
        sri("1760001120001", start_offset=-1000),
        sri("1790000000118", status="SUSPENDIDO", suspended=-10),
        sri("1790000000119", status="SUSPENDIDO", suspended=+400),
        sri("1790000000120", status="PASIVO", suspended=0),
        sri("1790000000121", status="SUSPENDIDO", suspended=-50, restarted=-20),
        sri("1790000000115", status="SUSPENDIDO", start_offset=-20),
    ])  # fmt: skip
    ghost = lambda ruc, notified: {  # noqa: E731
        "ruc": ruc,
        "legal_name": "x",
        "resolution": "R-1",
        "notification_date": notified,
        "qualification_detail": "detalle",
        "challenge_state": "-",
        "publication_date": None,
    }
    write_table(
        lake,
        "ghost_companies",
        [
            ghost("1790000000110", "2021-01-01"),
            ghost("1790000000115", "2019-01-01"),
            ghost("1790000000124", None),
            ghost("0102030405001", "2019-01-01"),
            ghost("12345", "2019-01-01"),
            ghost("0102030406001", "2021-01-01"),
            ghost("1760001120001", "2019-01-01"),
        ],
    )
    fin = lambda ruc, year, revenue: {  # noqa: E731
        "ruc": ruc,
        "year": year,
        "revenue": revenue,
        "assets": None,
        "equity": None,
        "employees": None,
    }
    write_table(lake, "company_financials", [
        fin("1790000000111", 2019, 1000.0),
        fin("1790000000112", 2019, 1000.0),
        fin("1790000000113", 2019, 0.0),
        fin("1790000000114", 2019, 1000.0),
        fin("1790000000114", 2020, 0.0),
        fin("1790000000115", 2019, 100.0),
        fin("1790000000116", 2021, 1000.0),
        fin("1790000000117", 2019, 100.0),
        fin("1790000000122", 2020, 1000.0),
        fin("0102030405001", 2019, 100.0),
        fin("1790000000123", 2019, 5000.0),
        fin("1790000000123", 2020, 100.0),
        fin("1790000000117", 2019, 1000.0),
    ])  # fmt: skip
    summary = build_marts(lake, root / "marts")
    return root / "marts", summary


def fired(marts: Path, code: str) -> set[str]:
    path = str(marts / "process_signals.parquet")
    rows = duckdb.execute(f"SELECT ocid FROM read_parquet('{path}') WHERE signal_code = ?", [code]).fetchall()
    return {r[0] for r in rows}


def test_registry_signals_are_computed_when_tables_exist(registry_run):
    _, summary = registry_run
    assert summary["signals_skipped"] == {}
    assert all(s["status"] == "computed" for s in summary["signals"].values())


def test_new_supplier_window_is_zero_to_179_days_and_excludes_catalogue(registry_run):
    marts, _ = registry_run
    assert {"N-fire", "N-179"} <= fired(marts, "NEW_SUPPLIER")
    assert not {"N-old", "N-180", "N-after", "N-catalogue"} & fired(marts, "NEW_SUPPLIER")


def test_new_supplier_evidence(registry_run):
    marts, _ = registry_run
    path = str(marts / "process_signals.parquet")
    value, evidence = duckdb.execute(
        f"SELECT value, evidence_json FROM read_parquet('{path}') "
        "WHERE ocid = 'N-fire' AND signal_code = 'NEW_SUPPLIER'"
    ).fetchone()
    assert value == 76
    assert '"days_between":76' in evidence and '"activity_start_date":"2020-01-15"' in evidence


def test_supplier_not_active_respects_suspension_timing(registry_run):
    marts, _ = registry_run
    result = fired(marts, "SUPPLIER_NOT_ACTIVE")
    assert {"A-susp", "A-before", "A-same-day", "A-restart"} <= result
    assert "A-after" not in result  # suspended long after the award: it was active at award time
    assert not {"A-active", "A-unknown"} & result  # active or absent from the registry


def test_supplier_not_active_evidence_timing(registry_run):
    marts, _ = registry_run
    path = str(marts / "process_signals.parquet")

    def timing(ocid: str) -> str:
        return duckdb.execute(
            f"SELECT json_extract_string(evidence_json, '$.timing') FROM read_parquet('{path}') "
            f"WHERE ocid = '{ocid}' AND signal_code = 'SUPPLIER_NOT_ACTIVE'"
        ).fetchone()[0]

    assert timing("A-susp") == "unknown"  # no suspension_date: timing cannot be established
    assert timing("A-before") == "suspended_before_process"
    assert timing("A-same-day") == "suspended_before_process"
    assert timing("A-restart") == "suspended_before_process"  # restart_date is not used


def test_summary_breaks_down_not_active_and_small_revenue(registry_run):
    _, summary = registry_run
    details = summary["signal_details"]
    assert details["SUPPLIER_NOT_ACTIVE"]["by_timing"]["unknown"] >= 1
    assert details["CONTRACT_VS_COMPANY_SIZE"]["fired_with_revenue_under_usd"] == 1000.0
    small = details["CONTRACT_VS_COMPANY_SIZE"]["fired_with_revenue_under_threshold"]
    assert small == 3  # the three CAP processes (revenue 100)


def test_registry_signals_never_fire_for_natural_persons_or_unidentified_winners(registry_run):
    marts, summary = registry_run
    path = str(marts / "process_signals.parquet")
    codes = duckdb.execute(
        f"SELECT DISTINCT signal_code FROM read_parquet('{path}') WHERE ocid IN ('NAT-1', 'NAT-2', 'NAT-3')"
    ).fetchall()
    assert codes == []  # no registry signal of any kind, risk or context
    assert "PUB-1" in fired(marts, "GHOST_COMPANY_LIST")  # public entities are eligible
    details = summary["signal_details"]
    ghost = details["GHOST_COMPANY_LIST"]["excluded_natural_or_unidentified_winners"]
    assert ghost == {"would_be_risk": 2, "would_be_context": 1}
    assert details["SUPPLIER_NOT_ACTIVE"]["excluded_natural_or_unidentified_winners"] == 1
    assert details["NEW_SUPPLIER"]["excluded_natural_or_unidentified_winners"] == 1


def test_ghost_list_is_risk_only_when_listed_before_the_process(registry_run):
    marts, _ = registry_run
    assert fired(marts, "GHOST_COMPANY_LIST") == {"CAP-1", "CAP-2", "CAP-3", "PUB-1"}
    # listed after the process (G-cat, catalogue method) or without a date: context only
    assert fired(marts, "GHOST_COMPANY_LISTED_LATER") == {"G-cat", "G-nodate"}


def test_contract_vs_size_is_strictly_greater_than_three_times_latest_positive_revenue(registry_run):
    marts, _ = registry_run
    result = fired(marts, "CONTRACT_VS_COMPANY_SIZE")
    assert {"S-fire", "S-latest"} <= result
    assert not {"S-equal", "S-zero"} & result
    assert not {"S-same", "S-prior"} & result  # same-year revenue is context; prior year preferred
    assert fired(marts, "CONTRACT_VS_COMPANY_SIZE_SAME_YEAR") == {"S-same"}
    assert "S-later" not in result  # revenue only reported for a year after the award year
    assert "S-dup" not in result  # duplicated (ruc, year) keeps the largest revenue (1000), 2500 < 3000


def test_ghost_evidence_states_the_timing(registry_run):
    marts, _ = registry_run
    path = str(marts / "process_signals.parquet")

    def evidence(ocid: str, code: str) -> str:
        return duckdb.execute(
            f"SELECT evidence_json FROM read_parquet('{path}') "
            f"WHERE ocid = '{ocid}' AND signal_code = '{code}'"
        ).fetchone()[0]

    later = evidence("G-cat", "GHOST_COMPANY_LISTED_LATER")
    assert '"timing":"listed_after_process"' in later and '"notification_date":"2021-01-01"' in later
    assert '"qualification_detail":"detalle"' in later and '"challenge_state":"-"' in later
    assert '"timing":"notification_date_missing"' in evidence("G-nodate", "GHOST_COMPANY_LISTED_LATER")
    assert '"listed_after_process":false' in evidence("CAP-1", "GHOST_COMPANY_LIST")


def test_context_signals_are_marked_and_never_scored(registry_run):
    marts, _ = registry_run
    path = str(marts / "process_signals.parquet")
    kinds = dict(
        duckdb.execute(
            f"SELECT signal_code, any_value(kind) FROM read_parquet('{path}') GROUP BY 1"
        ).fetchall()
    )
    assert kinds["GHOST_COMPANY_LISTED_LATER"] == kinds["CONTRACT_VS_COMPANY_SIZE_SAME_YEAR"] == "context"
    assert kinds["SINGLE_BIDDER"] == "risk"
    scores = str(marts / "process_scores.parquet")
    row = duckdb.execute(
        f"SELECT risk_score, n_signals, signal_codes, n_context_signals, context_signal_codes "
        f"FROM read_parquet('{scores}') WHERE ocid = 'G-cat'"
    ).fetchone()
    assert row == (0.0, 0, [], 1, ["GHOST_COMPANY_LISTED_LATER"])


def test_score_is_capped_at_100_and_matches_domain(registry_run):
    marts, _ = registry_run
    path = str(marts / "process_scores.parquet")
    rows = duckdb.execute(f"SELECT ocid, risk_score, signal_codes FROM read_parquet('{path}')").fetchall()
    by_ocid = {r[0]: r for r in rows}
    capped = by_ocid["CAP-1"]
    assert {"SINGLE_BIDDER", "GHOST_COMPANY_LIST", "BUYER_CONCENTRATION"} <= set(capped[2])
    assert capped[1] == 100.0
    assert risk_score(capped[2]) == 100.0
    assert all(r[1] == risk_score(r[2]) for r in rows)


def test_supplier_profile_counts(registry_run):
    marts, _ = registry_run
    path = str(marts / "supplier_profiles.parquet")
    row = duckdb.execute(
        f"SELECT kind, n_wins, n_buyers, total_awarded, top_buyer_ruc, top_buyer_share, single_bidder_wins "
        f"FROM read_parquet('{path}') WHERE ruc = '1790000000115'"
    ).fetchone()
    assert row == ("company", 3, 1, 120_000.0, "1760000000777", 1.0, 1)


def test_anomaly_score_is_separate_and_only_for_large_competitive_methods(tmp_path):
    procs = [
        process(
            f"AN-{i}", method="M-ANOM", budget=1000.0 + (i % 40) * 10, award_total=900.0 + (i % 40) * 9,
            n_tenderers=2 + i % 3, n_enquiries=i % 2,
        )
        for i in range(600)
    ]  # fmt: skip
    procs.append(process("AN-outlier", method="M-ANOM", budget=5e8, award_total=5e8 * 1.5, n_tenderers=40))
    procs += [process(f"TINY-{i}", method="M-TINY") for i in range(20)]
    procs.append(process("DIR", method_group="direct", method="Bienes y Servicios únicos"))
    write_lake(tmp_path / "lake", procs)
    build_marts(tmp_path / "lake", tmp_path / "marts")
    path = str(tmp_path / "marts" / "process_scores.parquet")
    scores = dict(duckdb.execute(f"SELECT ocid, anomaly_score FROM read_parquet('{path}')").fetchall())
    typical = sorted(v for k, v in scores.items() if k.startswith("AN-") and k != "AN-outlier")
    assert 0 < typical[0] and typical[-1] < 1
    assert scores["AN-outlier"] > typical[len(typical) // 2]
    assert scores["AN-outlier"] >= typical[-1]
    assert scores["DIR"] is None and scores["TINY-0"] is None
    rows = duckdb.execute(f"SELECT risk_score, signal_codes FROM read_parquet('{path}')").fetchall()
    assert all(r[0] == risk_score(r[1]) for r in rows)  # the anomaly score never enters the risk score
