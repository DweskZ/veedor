from __future__ import annotations

import zipfile
from pathlib import Path

import duckdb
import pytest

from veedor.infrastructure.registries.common import detect_encoding, parse_date_sql
from veedor.infrastructure.registries.download import RemoteFile, download_file, parse_sri_page
from veedor.infrastructure.registries.sri import (
    build_ghost_companies,
    build_suppliers_sri,
    excel_serial_to_iso,
)
from veedor.infrastructure.registries.supercias import build_supercias

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "registries"


def _query(path: Path, sql: str) -> list[tuple]:
    return duckdb.connect().execute(sql.replace("$T", f"read_parquet('{path}')")).fetchall()


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    lake_dir = tmp_path / "lake"
    lake_dir.mkdir()
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM (VALUES ('0991111111001'), ('0102222222001'), ('1703333333001'), "
        f"('0105555555001')) t(supplier_ruc)) TO '{lake_dir / 'awards.parquet'}' (FORMAT parquet)"
    )
    con.execute(
        f"COPY (SELECT * FROM (VALUES ('0992222222001'), (NULL)) t(supplier_ruc)) "
        f"TO '{lake_dir / 'tenderers.parquet'}' (FORMAT parquet)"
    )
    return lake_dir


def _zip_fixture(dest_dir: Path, encoding: str) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    text = (FIXTURES / "sri_province.csv").read_text(encoding="utf-8")
    with zipfile.ZipFile(dest_dir / "SRI_RUC_Test.zip", "w") as bundle:
        bundle.writestr("SRI_RUC_Test.csv", text.encode(encoding))


@pytest.mark.parametrize("encoding", ["utf-8", "latin-1"])
def test_suppliers_sri_maps_columns_and_filters_to_lake_rucs(
    tmp_path: Path, lake: Path, encoding: str
) -> None:
    raw = tmp_path / "raw"
    _zip_fixture(raw, encoding)
    result = build_suppliers_sri(raw, lake)

    rows = _query(
        lake / "suppliers_sri.parquet",
        "SELECT ruc, legal_name, status, taxpayer_type, activity_start_date, suspension_date, restart_date,"
        " ciiu_code, activity, province, source_file FROM $T ORDER BY ruc",
    )
    by_ruc = {r[0]: r for r in rows}
    assert set(by_ruc) == {"0102222222001", "0991111111001", "1703333333001"}  # 0999... is not in the lake
    assert (result.rows, result.wanted_rucs, result.matched_rucs) == (3, 5, 3)

    company = by_ruc["0991111111001"]
    assert company[1] == "CONSTRUCTORA ÑANDÚ S.A."  # accents survive both encodings
    assert company[4] == "2015-03-02"
    assert company[9] == "GUAYAS"  # head establishment (number 1), not the Manabi branch
    assert company[10] == "SRI_RUC_Test.zip"

    foundation = by_ruc["0102222222001"]
    assert foundation[1] == 'FUNDACION "LA ESPERANZA | SUR"'  # quoted pipe and doubled quotes
    assert foundation[4] == "2010-05-12"  # day-first date
    assert foundation[5] == "2020-06-30"
    assert foundation[6] == "2021-01-04"

    person = by_ruc["1703333333001"]
    assert person[4] == "2001-05-28"  # timestamp truncated to date
    assert person[5] is None and person[7] is None  # empty strings become NULL


def test_suppliers_sri_rejects_unexpected_header(tmp_path: Path, lake: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    with zipfile.ZipFile(raw / "SRI_RUC_Bad.zip", "w") as bundle:
        bundle.writestr("bad.csv", "RUC|NOMBRE\n1|X\n")
    with pytest.raises(ValueError, match="unexpected header"):
        build_suppliers_sri(raw, lake)


def test_detect_encoding(tmp_path: Path) -> None:
    utf8, latin = tmp_path / "u.csv", tmp_path / "l.csv"
    utf8.write_bytes("Ñandú".encode())
    latin.write_bytes("Ñandú".encode("latin-1"))
    assert detect_encoding(utf8) == "utf-8"
    assert detect_encoding(latin) == "latin-1"


def test_parse_date_sql_formats() -> None:
    con = duckdb.connect()
    values = "('2001-05-28 12:08:55'), ('28/05/2001'), (''), ('n/a')"
    sql = f"SELECT {parse_date_sql('x')} FROM (VALUES {values}) t(x)"
    assert [r[0] for r in con.execute(sql).fetchall()] == ["2001-05-28", "2001-05-28", None, None]


def test_excel_serial_to_iso() -> None:
    assert excel_serial_to_iso("43003") == "2017-09-25"
    assert excel_serial_to_iso("") is None
    assert excel_serial_to_iso("abc") is None
    assert excel_serial_to_iso(None) is None


def test_ghost_companies_handles_wrapped_and_short_rows(tmp_path: Path) -> None:
    raw, lake_dir = tmp_path / "raw", tmp_path / "lake"
    raw.mkdir()
    (raw / "SRI_Catastro_Empresas_Fantasmas.csv").write_bytes((FIXTURES / "ghost_sample.csv").read_bytes())
    assert build_ghost_companies(raw, lake_dir) == 3
    rows = _query(
        lake_dir / "ghost_companies.parquet",
        "SELECT ruc, legal_name, resolution, notification_date, publication_date, ruc_status, challenge_state"
        " FROM $T ORDER BY ruc",
    )
    assert rows[0] == ("0102222222001", "SOLO SEIS CAMPOS", "RES-3", None, None, None, None)
    assert rows[1][:4] == ("0991111111001", "CONSTRUCTORA ÑANDÚ S.A.", "RES-1", "2017-11-08")
    assert rows[1][5] == "SUSPENDIDO"
    assert rows[2][0] == "1703333333001"  # record wrapped in an extra pair of quotes
    assert rows[2][5:] == ("ACTIVO", 'Sentencia con "comillas"')


def test_supercias_directory_and_financials(tmp_path: Path, lake: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("compania", "ranking"):
        (raw / f"bi_{name}.csv").write_bytes((FIXTURES / f"supercias_{name}.csv").read_bytes())
    result = build_supercias(raw, lake)

    companies = _query(
        lake / "companies_supercias.parquet",
        "SELECT expediente, ruc, legal_name, company_type, province FROM $T ORDER BY expediente",
    )
    assert companies[0] == (1, "0991111111001", "CONSTRUCTORA ÑANDÚ S.A.", "ANÓNIMA", "GUAYAS")
    assert companies[1][2] == "EMPRESA, CON COMA S.A."
    assert companies[2][1] is None  # blank RUC stays NULL
    assert (result.companies, result.wanted_rucs, result.matched_rucs) == (3, 5, 2)

    fin = _query(
        lake / "company_financials.parquet",
        "SELECT ruc, year, revenue, total_income, assets, equity, employees FROM $T ORDER BY ruc, year",
    )
    assert len(fin) == 3  # expediente 3 (no RUC) and 99 (unknown) are dropped
    assert fin[0] == ("0991111111001", 2023, 1500000.5, 1600000.0, 900000.0, 400000.0, 25.0)
    assert fin[1] == ("0991111111001", 2024, None, None, 950000.0, -5.0, None)  # blanks stay NULL


def test_parse_sri_page_discovers_links_and_quotes_non_ascii() -> None:
    html = (
        '<a href="https://descargas.sri.gob.ec/download/datosAbiertos/SRI_RUC_Cañar.zip">x</a>'
        '<a href="https://descargas.sri.gob.ec/download/datosAbiertos/SRI_RUC_Azuay.zip">x</a>'
        '<a href="https://descargas.sri.gob.ec/download/datosAbiertos/COMPROBANTES_CEL_2024.zip">x</a>'
        '<a href="https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/'
        '909ad236-f46c-488f-8661-f2f4e5faf1c4/SRI_Catastro_Empresas_Fantasmas.csv">x</a>'
    )
    rucs, ghost = parse_sri_page(html)
    assert [f.name for f in rucs] == ["SRI_RUC_Azuay.zip", "SRI_RUC_Cañar.zip"]
    assert rucs[1].url.endswith("SRI_RUC_Ca%C3%B1ar.zip")
    assert ghost is not None and ghost.name == "SRI_Catastro_Empresas_Fantasmas.csv"


def test_parse_sri_page_without_ghost_link() -> None:
    assert parse_sri_page("<html></html>") == ([], None)


def test_download_refuses_unofficial_host(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-official host"):
        download_file(None, RemoteFile("https://example.com/SRI_RUC_X.zip", "SRI_RUC_X.zip"), tmp_path)  # type: ignore[arg-type]
