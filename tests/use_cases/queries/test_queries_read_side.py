from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures" / "api"))
import api_fixture_data as fx  # noqa: E402

from veedor.infrastructure.lake.reader import LakeReader  # noqa: E402
from veedor.use_cases.queries import buyers, processes, stats, suppliers  # noqa: E402
from veedor.use_cases.queries.ports import LakeUnavailableError, NotFoundError  # noqa: E402


def _list(lake, sort="-risk_score", page=1, page_size=25, **filters):
    return processes.list_processes(
        lake, processes.ProcessFilters(**filters), page=page, page_size=page_size, sort=sort
    )


def test_list_sorted_by_risk_desc(lake: LakeReader) -> None:
    result = _list(lake)
    assert [r["ocid"] for r in result["items"]] == [
        fx.OCID_COMPANY,
        fx.OCID_NATURAL,
        fx.OCID_NORUC,
        "ocds-5wno2w-test-0005",
        fx.OCID_DIRECT,
    ]
    assert result["total"] == 5


def test_pagination_slices_and_reports_total(lake: LakeReader) -> None:
    result = _list(lake, page=2, page_size=3)
    assert len(result["items"]) == 2 and result["total"] == 5 and result["page"] == 2


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"year": 2022}, 2),
        ({"method": "Cotización"}, 2),
        ({"buyer_ruc": fx.OTHER_BUYER_RUC}, 1),
        ({"signal": "SINGLE_BIDDER"}, 3),
        ({"min_score": 40}, 2),
        ({"q": "Hospital"}, 1),
        ({"q": "aceras"}, 1),  # matched through the CPC description
        ({"q": "LICS-006"}, 1),  # process code
    ],
)
def test_filters(lake: LakeReader, filters: dict, expected: int) -> None:
    assert _list(lake, **filters)["total"] == expected


@pytest.mark.parametrize("text", [fx.NATURAL_NAME, "MENDEZ", fx.CEDULA, fx.DOCTOR_NAME, "Persona"])
def test_q_never_matches_descriptions_or_party_names(lake: LakeReader, text: str) -> None:
    """Search must not let a caller find a process through a person named in free text or parties."""
    assert _list(lake, q=text)["total"] == 0


def test_like_wildcards_in_q_are_literal(lake: LakeReader) -> None:
    assert _list(lake, q="%")["total"] == 0
    assert _list(lake, q="_")["total"] == 0


@pytest.mark.parametrize("sort", ["risk_score; DROP TABLE x", "nope", "--risk_score", "risk_score,ocid", ""])
def test_invalid_sort_is_rejected(lake: LakeReader, sort: str) -> None:
    with pytest.raises(processes.InvalidSortError):
        _list(lake, sort=sort)


def test_ascending_sort(lake: LakeReader) -> None:
    assert _list(lake, sort="risk_score")["items"][0]["ocid"] == fx.OCID_DIRECT


def test_process_detail_combines_sources(lake: LakeReader) -> None:
    detail = processes.get_process(lake, fx.OCID_NATURAL)
    assert detail["facts"]["process_code"] == "COT-002"
    assert [s["code"] for s in detail["signals"]] == ["SINGLE_BIDDER"]
    assert detail["signals"][0]["label_es"] == "Oferente único"
    assert len(detail["tenderers"]) == 2 and len(detail["awards"]) == 1
    assert detail["winner"]["ruc"] == fx.NATURAL_RUC


def test_process_only_in_lake_has_no_score(lake: LakeReader) -> None:
    detail = processes.get_process(lake, fx.OCID_LAKE_ONLY)
    assert detail["score"] is None and detail["signals"] == [] and detail["winner"] is None


def test_unknown_process_is_not_found(lake: LakeReader) -> None:
    with pytest.raises(NotFoundError):
        processes.get_process(lake, "ocds-5wno2w-missing")


def test_supplier_with_registry(lake: LakeReader) -> None:
    result = suppliers.get_supplier(lake, fx.COMPANY_RUC)
    assert result["profile"]["n_wins"] == 2
    assert result["registry"]["sri"]["status"] == "ACTIVO"
    assert result["registry"]["ghost_company_listed"] is None  # dataset not present in the fixture
    assert len(result["recent_processes"]) == 2


def test_unknown_supplier_and_buyer(lake: LakeReader) -> None:
    with pytest.raises(NotFoundError):
        suppliers.get_supplier(lake, "1790000000001")
    with pytest.raises(NotFoundError):
        buyers.get_buyer(lake, "1760000000001")


def test_buyer_summary(lake: LakeReader) -> None:
    result = buyers.get_buyer(lake, fx.BUYER_RUC)
    assert result["n_processes"] == 3 and result["n_flagged"] == 3
    assert result["top_suppliers"][0]["ruc"] == fx.COMPANY_RUC
    assert result["top_suppliers"][0]["share_of_awarded"] == pytest.approx(1000 / 1590)
    assert {m["code"]: m["count"] for m in result["signal_mix"]} == {"SINGLE_BIDDER": 3, "LOW_SAVING": 1}


def test_stats(lake: LakeReader) -> None:
    result = stats.get_stats(lake)
    assert result["processes_scored"] == 5 and result["processes_with_signals"] == 4
    assert result["processes_total"] == 5 and result["last_data_date"] == "2024-01-10"
    assert result["processes_by_method_group"]["competitive"] == 3
    assert sum(b["count"] for b in result["score_distribution"]) == 5
    assert result["signal_counts"][0]["count"] == 2


def test_missing_marts_raise_unavailable(tmp_path: Path) -> None:
    empty = LakeReader(tmp_path / "lake", tmp_path / "marts")
    with pytest.raises(LakeUnavailableError):
        stats.get_stats(empty)


def test_reader_blocks_files_outside_the_lake(lake: LakeReader) -> None:
    import duckdb

    with pytest.raises(duckdb.Error):
        lake.fetch("SELECT * FROM read_text('/etc/hosts')", tables=("process_scores",))
    with pytest.raises(duckdb.Error):
        lake.fetch("SELECT * FROM read_csv('/etc/passwd')", tables=("process_scores",))
    with pytest.raises(ValueError):
        lake.fetch("DROP VIEW process_scores", tables=("process_scores",))
