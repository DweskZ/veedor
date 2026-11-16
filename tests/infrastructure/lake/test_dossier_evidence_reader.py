"""EvidenceReader against tiny synthetic Parquet files (no real lake)."""

import json

import duckdb
import pytest

from veedor.infrastructure.lake import evidence_reader
from veedor.infrastructure.lake.evidence_reader import EvidenceReader

BUYER = "1760001040001"
COMPANY = "1790012345001"
PERSON = "0912345678001"
PROCESS_COLUMNS = [
    "ocid", "process_code", "year", "buyer_ruc", "buyer_name", "method", "description", "budget",
    "award_total", "n_tenderers", "first_award_date", "date_signed", "tender_start", "release_date",
]  # fmt: skip


def _write(directory, name, create_sql, rows):
    con = duckdb.connect()
    con.execute(create_sql)
    for row in rows:
        con.execute(f"INSERT INTO t VALUES ({', '.join('?' * len(row))})", row)
    con.execute(f"COPY t TO '{directory / (name + '.parquet')}' (FORMAT parquet)")


def _process(ocid, year, **kw):
    base = dict.fromkeys(PROCESS_COLUMNS)
    base.update(ocid=ocid, process_code=f"A-{ocid}-{year}-1", year=year, buyer_ruc=BUYER,
                buyer_name="ENTIDAD UNO", method="Menor", description="OBRA")  # fmt: skip
    base.update(kw)
    return tuple(base[c] for c in PROCESS_COLUMNS)


@pytest.fixture
def dirs(tmp_path):
    lake, marts = tmp_path / "lake", tmp_path / "marts"
    lake.mkdir()
    marts.mkdir()
    _write(
        lake,
        "processes",
        "CREATE TABLE t(ocid VARCHAR, process_code VARCHAR, year INT, buyer_ruc VARCHAR, buyer_name VARCHAR,"
        " method VARCHAR, description VARCHAR, budget DOUBLE, award_total DOUBLE, n_tenderers INT,"
        " first_award_date VARCHAR, date_signed VARCHAR, tender_start VARCHAR, release_date VARCHAR)",
        [
            _process("o1", 2023, budget=100.0, award_total=90.0, n_tenderers=1,
                     first_award_date="2023-05-10T10:00:00-05:00"),
            _process("o0", 2022, budget=50.0, award_total=50.0, n_tenderers=3,
                     first_award_date="2022-01-05T10:00:00-05:00"),
            _process("o2", 2023, budget=80.0, award_total=40.0, n_tenderers=3,
                     first_award_date="2023-06-01T10:00:00-05:00"),
            _process("o3", 2023, budget=80.0, award_total=80.0, n_tenderers=5,
                     first_award_date="2023-07-01T10:00:00-05:00"),
            _process("o4", 2023),  # no date at all
            _process("o5", 2023, date_signed="2023-08-01T00:00:00-05:00"),  # only a signature date
            _process("o6", 2024, tender_start="2024-02-01T10:00:00-05:00"),  # only tender start
            _process("o7", 2021, release_date="2021-03-01T10:00:00-05:00", 
                     description="SERVICIO A FAVOR DE JUAN PEREZ"),  # only release date
        ],
    )  # fmt: skip
    _write(
        lake,
        "awards",
        "CREATE TABLE t(ocid VARCHAR, award_id VARCHAR, award_date VARCHAR, supplier_id VARCHAR,"
        " supplier_ruc VARCHAR, supplier_name VARCHAR, amount DOUBLE)",
        [
            ("o1", "a1", "2023-05-10", "s", COMPANY, "EMPRESA UNO SA", 90.0),
            ("o0", "a0", "2022-01-05", "s", COMPANY, "EMPRESA UNO SA", 50.0),
            ("o2", "a2", "2023-06-01", "s", PERSON, "JUAN PEREZ", 40.0),
            ("o5", "a5", None, "s", COMPANY, "EMPRESA UNO SA", None),
            ("o6", "a6", None, "s", COMPANY, "EMPRESA UNO SA", 10.0),
            ("o7", "a7", None, "s", PERSON, "JUAN PEREZ", 5.0),
        ],
    )  # fmt: skip
    _write(
        lake,
        "company_financials",
        "CREATE TABLE t(ruc VARCHAR, year INT, revenue DOUBLE)",
        [(COMPANY, 2021, 1000.0), (COMPANY, 2023, 5000.0), (COMPANY, 2025, 9000.0)],
    )
    evidence = json.dumps({"supplier_ruc": PERSON, "supplier_name": "JUAN PEREZ", "n": 2})
    _write(
        marts,
        "process_signals",
        "CREATE TABLE t(ocid VARCHAR, signal_code VARCHAR, value DOUBLE, threshold DOUBLE, "
        "evidence_json VARCHAR)",
        [("o2", "BUYER_CONCENTRATION", 0.7, 0.3, evidence)],
    )
    return lake, marts


def test_full_pack_with_history_comparison_and_masking(dirs):
    lake, marts = dirs
    pack = EvidenceReader(lake, marts).load("o1")
    assert pack.winner.name == "EMPRESA UNO SA" and pack.winner.kind == "company"
    h = pack.history
    assert (h.n_previous_awards, h.total_previous_amount) == (1, 50.0)
    assert (h.reference_date, h.reference_date_kind) == ("2023-05-10", "fecha de adjudicación")
    assert h.first_award_date == "2022-01-05"
    assert (h.n_pair_awards, h.pair_first_year, h.pair_last_year) == (4, 2022, 2024)
    assert pack.process.award_budget_ratio == 0.9
    assert pack.comparison.n_processes == 5  # method Menor, year 2023: o1 o2 o3 o4 o5
    assert pack.comparison.median_tenderers == 3.0
    assert pack.comparison.single_bidder_share == pytest.approx(0.3333, abs=1e-4)
    assert pack.signals == [] and pack.signals_available is True


def test_history_uses_the_same_date_fallback_as_the_signals(dirs):
    lake, marts = dirs
    reader = EvidenceReader(lake, marts)
    signed = reader.load("o5").history
    assert (signed.reference_date, signed.reference_date_kind) == ("2023-08-01", "fecha de firma")
    assert signed.n_previous_awards == 2  # o0 and o1 precede 2023-08-01; award o5 has no own date
    started = reader.load("o6").history
    assert (started.reference_date, started.reference_date_kind) == ("2024-02-01", "inicio de ofertas")
    assert started.n_previous_awards == 3  # o0, o1 and o5 (its day comes from the process signature date)
    released = reader.load("o7").history
    assert released.reference_date_kind == "fecha de publicación"


def test_history_is_null_only_without_any_date(dirs):
    lake, marts = dirs
    assert EvidenceReader(lake, marts).load("o4").history is None


def test_zero_previous_awards_is_distinct_from_unavailable(dirs):
    lake, marts = dirs
    history = EvidenceReader(lake, marts).load("o0").history
    assert history.n_previous_awards == 0 and history.total_previous_amount is None
    assert history.n_pair_awards == 4


def test_revenue_of_the_award_year_and_the_latest_are_both_reported(dirs):
    lake, marts = dirs
    registry = EvidenceReader(lake, marts).load("o1").winner.registry
    assert (registry.award_year, registry.revenue_award_year) == (2023, 5000.0)
    assert (registry.latest_revenue_year, registry.latest_revenue) == (2025, 9000.0)
    other = EvidenceReader(lake, marts).load("o0").winner.registry
    assert (other.award_year, other.revenue_award_year) == (2022, None)


def test_sources_carry_the_documented_licences(dirs):
    lake, marts = dirs
    sources = {s.dataset: s for s in EvidenceReader(lake, marts).load("o1").sources}
    sercop = next(s for d, s in sources.items() if d.startswith("SERCOP datos abiertos OCDS: procesos"))
    assert sercop.licence == "CC BY 3.0 EC" and sercop.retrieved_at == "2026-11-16"
    assert sercop.url == "https://data.open-contracting.org/en/publication/110"
    assert "no verificada" not in open(evidence_reader.__file__).read()


def test_optional_tables_absent_give_null_facts(dirs):
    lake, marts = dirs
    registry = EvidenceReader(lake, marts).load("o1").winner.registry
    assert registry.status is None and registry.ghost_listed is None


def test_natural_person_masked_in_winner_and_evidence(dirs):
    lake, marts = dirs
    pack = EvidenceReader(lake, marts).load("o2")
    assert pack.winner.name == "Persona natural" and pack.winner.ruc == "0912*********"
    dumped = pack.model_dump_json()
    assert PERSON not in dumped and "JUAN PEREZ" not in dumped


def test_missing_marts_marks_signals_unavailable(dirs):
    lake, marts = dirs
    pack = EvidenceReader(lake, marts / "nope").load("o1")
    assert pack.signals_available is False and pack.risk_score is None


def test_unknown_ocid_returns_none(dirs):
    lake, marts = dirs
    assert EvidenceReader(lake, marts).load("missing") is None


def test_connection_is_locked_down_like_the_api_reader(dirs):
    lake, marts = dirs
    con, _ = EvidenceReader(lake, marts)._connect()
    try:
        assert con.execute("SELECT count(*) FROM processes").fetchone()[0] == 8
        with pytest.raises(duckdb.Error):
            con.execute("SELECT * FROM read_csv('/etc/hosts')").fetchall()
        with pytest.raises(duckdb.Error):
            con.execute("SET enable_external_access=true")
        with pytest.raises(duckdb.Error):
            con.execute("SET allowed_directories=['/']")
        with pytest.raises(duckdb.Error):
            con.execute("COPY (SELECT 1) TO '/tmp/veedor_should_not_exist.csv'")
    finally:
        con.close()


def test_hostile_description_is_screened_and_personal_names_withheld(dirs):
    lake, marts = dirs
    pack = EvidenceReader(lake, marts).load("o7")  # supplier is a natural person
    assert not hasattr(pack.process, "description")  # the free-text description is not loaded at all
    assert "JUAN PEREZ" not in pack.model_dump_json()
