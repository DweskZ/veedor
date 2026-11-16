"""GET /processes/{ocid}/provenance and the amount filter of GET /processes."""

from __future__ import annotations

from datetime import UTC, datetime

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

from veedor.api.v1.investigations import get_investigation_store
from veedor.domain.investigation.models import InvestigationRecord
from veedor.domain.provenance import catalog
from veedor.domain.signals import SIGNALS
from veedor.infrastructure.investigations.store import InvestigationStore
from veedor.schemas.common import Party
from veedor.schemas.processes import AwardOut, ProcessFacts, Score
from veedor.schemas.profile import SupplierProfile

API = "/api/v1"
FACT_KEYS = {"key", "label_es", "value", "source_id", "source_field", "derived", "derivation_es", "verify_es"}


def get(client: TestClient, ocid: str) -> dict:
    response = client.get(f"{API}/processes/{ocid}/provenance")
    assert response.status_code == 200, response.text
    return response.json()


def by_key(body: dict) -> dict[str, dict]:
    return {f["key"]: f for f in body["facts"]}


# ------------------------------------------------------------------------------- completeness


@pytest.mark.parametrize(
    ("section", "model"),
    [
        ("facts", ProcessFacts),
        ("score", Score),
        ("winner", SupplierProfile),
        ("tenderers", Party),
        ("awards", AwardOut),
    ],
)
def test_every_field_of_the_detail_response_has_a_provenance_entry(section, model):
    """Fails when a field is added to the process detail models without a provenance entry."""
    missing = [f"{section}.{name}" for name in model.model_fields if f"{section}.{name}" not in catalog.FACTS]
    assert missing == []


def test_every_signal_has_inputs_with_a_known_source():
    for definition in SIGNALS:
        for column in definition.fields:
            assert column in catalog.COLUMN_SOURCE, (definition.code, column)
        assert catalog.signal_source_field(definition.code) and catalog.signal_verify(definition.code)


def test_every_investigation_fact_has_a_tool_and_a_verification():
    from veedor.domain.dossier.investigation_facts import FACT_SPECS

    for spec in FACT_SPECS:
        assert spec.id in catalog.investigation_catalogue()
        tool, field = catalog.investigation_tool(spec.id)
        assert tool and field


def test_every_catalogue_entry_names_a_known_source_and_a_way_to_verify():
    entries = [*catalog.FACTS.values(), *(spec for _, spec in catalog.REGISTRY_FACTS.values())]
    for spec in entries:
        assert spec.source_id in catalog.SOURCES and spec.verify_es and spec.label_es
        if spec.derived:
            assert spec.derivation_es, spec.label_es


def test_the_detail_endpoint_facts_are_all_in_the_provenance_of_the_same_process(client: TestClient):
    detail = client.get(f"{API}/processes/{fx.OCID_COMPANY}").json()
    keys = by_key(get(client, fx.OCID_COMPANY))
    for field in detail["facts"]:
        assert f"facts.{field}" in keys, field
    for field in detail["score"]:
        assert f"score.{field}" in keys, field
    for field in detail["winner"]:
        assert f"winner.{field}" in keys, field
    for signal in detail["signals"]:
        assert f"signal.{signal['code']}" in keys, signal["code"]
    for field in detail["awards"][0] if detail["awards"] else ():
        assert f"awards.{field}" in keys
    for field in detail["tenderers"][0]:
        assert f"tenderers.{field}" in keys


# -------------------------------------------------------------------------------- content


def test_shape_sources_and_licences(client: TestClient):
    body = get(client, fx.OCID_COMPANY)
    assert body["ocid"] == fx.OCID_COMPANY
    assert all(set(f) == FACT_KEYS for f in body["facts"])
    sources = {s["id"]: s for s in body["sources"]}
    assert {f["source_id"] for f in body["facts"]} == set(
        sources
    )  # every cited source is listed, and no other
    sercop = sources["sercop_ocds"]
    assert (
        sercop["licence"].startswith("CC BY 3.0 EC") and "Open Contracting Data Registry" in sercop["licence"]
    )
    assert sercop["retrieved_at"] == "2026-11-16" and sercop["publisher"].startswith("SERCOP")
    assert sercop["url"] == "https://data.open-contracting.org/en/publication/110"
    assert sources["veedor_indicators"]["licence"].startswith("MIT")


def test_process_facts_map_to_their_ocds_paths(client: TestClient):
    keys = by_key(get(client, fx.OCID_COMPANY))
    assert keys["facts.n_tenderers"]["source_field"] == "tender.numberOfTenderers"
    assert keys["facts.tender_start"]["source_field"] == "tender.tenderPeriod.startDate"
    assert keys["facts.buyer_region"]["source_field"] == "parties[id = buyer.id].address.region"
    assert (
        keys["facts.award_total"]["derived"] is True and "Suma" in keys["facts.award_total"]["derivation_es"]
    )
    assert keys["facts.method_group"]["derived"] is True
    assert (
        fx.OCID_COMPANY in keys["facts.n_tenderers"]["verify_es"]
        and "{" not in keys["facts.n_tenderers"]["verify_es"]
    )
    assert keys["facts.process_code"]["value"] == "LICO-001"


@pytest.mark.parametrize(
    ("budget_source", "path", "derived"),
    [
        ("tender.value", "tender.value.amount", False),
        ("tender.lots", "tender.lots[].value.amount", True),
        ("planning.budget", "planning.budget.amount.amount", False),
        (None, "tender.value.amount; tender.lots[].value.amount; planning.budget.amount.amount", False),
    ],
)
def test_budget_states_the_path_that_was_actually_used(lake_dirs, budget_source, path, derived):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from veedor.api.deps import get_reader
    from veedor.api.main import create_app
    from veedor.infrastructure.lake.reader import LakeReader

    lake, _ = lake_dirs
    table = pq.read_table(lake / "processes.parquet").to_pylist()
    for row in table:
        row["budget_source"] = budget_source
    pq.write_table(pa.Table.from_pylist(table), lake / "processes.parquet")
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(*lake_dirs)
    fact = by_key(get(TestClient(app), fx.OCID_COMPANY))["facts.budget"]
    assert fact["source_field"] == path and fact["derived"] is derived
    assert "tender.value, suma de lotes, planning.budget" in fact["derivation_es"] or budget_source is None
    assert fact["value"] == 1010.0


def test_fired_signals_carry_rule_threshold_inputs_and_verification(client: TestClient):
    keys = by_key(get(client, fx.OCID_COMPANY))
    low = keys["signal.LOW_SAVING"]
    assert low["derived"] is True and low["source_id"] == "veedor_indicators"
    assert "processes.award_total" in low["source_field"] and "awards[].value.amount" in low["source_field"]
    assert "Regla:" in low["derivation_es"] and "umbral: 0.99" in low["derivation_es"]
    assert "budget = 1010.0" in low["derivation_es"] and "percentil" in low["verify_es"]
    assert (
        keys["signal.SINGLE_BIDDER"]["value"] == 1.0
        and "n_tenderers = 1" in keys["signal.SINGLE_BIDDER"]["derivation_es"]
    )
    assert "signal.GHOST_COMPANY_LISTED_LATER" in keys  # context signals have provenance too
    assert "signal.SHORT_TENDER_WINDOW" not in keys  # only what fired


def test_winner_registry_facts_name_the_file_and_the_column(client: TestClient):
    keys = by_key(get(client, fx.OCID_COMPANY))
    status = keys["registry.sri_status"]
    assert status["value"] == "ACTIVO" and status["source_id"] == "sri_ruc"
    assert (
        status["source_field"].endswith(": ESTADO_CONTRIBUYENTE")
        and "SRI_RUC" in status["source_field"]
        or ".zip" in status["source_field"]
        or "SRI_RUC_<provincia>" in status["source_field"]
    )
    assert keys["registry.sri_activity_start"]["value"] == "2015-01-01"
    assert keys["registry.sri_activity_start"]["source_field"].endswith("FECHA_INICIO_ACTIVIDADES")
    assert fx.COMPANY_RUC in status["verify_es"]
    assert "actual" in status["derivation_es"].lower() or "vigente" in status["derivation_es"].lower()


def test_natural_person_winner_is_masked_and_gets_no_registry_facts(client: TestClient):
    body = get(client, fx.OCID_NATURAL)
    text = str(body)
    for secret in (fx.NATURAL_NAME, fx.NATURAL_RUC, "Ficticia", "Quispe"):
        assert secret not in text, secret
    keys = by_key(body)
    assert keys["winner.name"]["value"] == "Persona natural"
    assert not any(k.startswith("registry.") for k in keys)
    assert keys["facts.description_withheld"]["value"] is True and keys["facts.description"]["value"] is None
    signal_text = keys["signal.SINGLE_BIDDER"]["derivation_es"] + keys["signal.SINGLE_BIDDER"]["verify_es"]
    assert fx.NATURAL_NAME not in signal_text and fx.NATURAL_RUC not in signal_text


def test_party_without_ruc_is_masked_in_every_value(client: TestClient):
    body = get(client, fx.OCID_NORUC)
    text = str(body)
    assert fx.NORUC_NAME not in text and fx.CEDULA not in text and "MENDEZ" not in text
    assert not any(k.startswith("registry.") for k in by_key(body))
    names = by_key(body)["tenderers.name"]["value"]
    assert fx.ENTITY_NORUC_NAME in names and fx.NORUC_NAME not in names


def test_natural_person_buyer_is_masked(client: TestClient):
    body = get(client, "ocds-5wno2w-test-0005")
    assert fx.NATURAL_BUYER_NAME not in str(body) and fx.NATURAL_BUYER_RUC not in str(body)


def test_unknown_process_is_404_and_bad_ocid_422(client: TestClient):
    assert client.get(f"{API}/processes/ocds-5wno2w-nope-9999/provenance").status_code == 404
    assert client.get(f"{API}/processes/not-an-ocid/provenance").status_code == 422


# ---------------------------------------------------------------------------- investigation


@pytest.fixture
def store(client: TestClient, tmp_path):
    investigations = InvestigationStore(tmp_path / "investigations")
    client.app.dependency_overrides[get_investigation_store] = lambda: investigations
    return investigations


def test_stored_investigation_facts_name_tool_and_field_and_unknown_ids_are_ignored(client, store):
    now = datetime(2026, 11, 16, 17, 0, tzinfo=UTC)
    store.save(
        InvestigationRecord(
            ocid=fx.OCID_COMPANY,
            started_at=now,
            finished_at=now,
            renderer_version=6,
            facts_added=["investigation.company.capital", "investigation.tax.live", "investigation.nope"],
        )  # fmt: skip
    )
    body = get(client, fx.OCID_COMPANY)
    keys = by_key(body)
    capital = keys["investigation.company.capital"]
    assert (
        capital["source_field"].startswith("get_compania_info: ")
        and "capital_suscrito" in capital["source_field"]
    )
    assert keys["investigation.tax.live"]["source_field"].startswith("get_sri_ruc_info: ")
    assert "investigation.nope" not in keys
    live = {s["id"]: s for s in body["sources"]}["supercias_company"]
    assert live["retrieved_at"] == "2026-11-16" and live["licence"] == "licencia no declarada por la fuente"
    assert not any(k.startswith("investigation.") for k in by_key(get(client, fx.OCID_NATURAL)))


def test_without_a_stored_investigation_there_are_no_investigation_facts(client, store):
    assert not any(k.startswith("investigation.") for k in by_key(get(client, fx.OCID_COMPANY)))


# ------------------------------------------------------------------------------ amount filter


def total(client: TestClient, **params) -> int:
    response = client.get(f"{API}/processes", params={"page_size": 1, **params})
    assert response.status_code == 200, response.text
    return response.json()["total"]


def test_amount_filter_bounds_are_inclusive_and_combine_with_other_filters(client: TestClient):
    # award totals in the fixture: 1000, 500, 200, 90 and one process without an amount
    assert total(client) == 5
    assert total(client, min_amount=500) == 2
    assert total(client, min_amount=500.01) == 1
    assert total(client, max_amount=200) == 2
    assert total(client, min_amount=100, max_amount=600) == 2
    assert total(client, min_amount=0) == 4  # a process without an amount never matches an amount bound
    assert total(client, min_amount=500, year=2023) == 2 and total(client, min_amount=500, year=2022) == 0
    assert total(client, min_amount=1, signal="LOW_SAVING") == 1
    assert total(client, min_amount=500, q="LICO") == 1


@pytest.mark.parametrize(
    "params",
    [
        {"min_amount": -1},
        {"max_amount": -0.01},
        {"min_amount": "abc"},
        {"min_amount": "nan"},
        {"max_amount": "inf"},
        {"min_amount": 1e13},
        {"min_amount": 10, "max_amount": 5},
        {"min_amount": "1e999"},
        {"min_amount": "' OR 1=1 --"},
        {"max_amount": "%00"},
        {"min_amount": "1; DROP TABLE x"},
    ],
)
def test_invalid_amounts_are_rejected_with_422(client: TestClient, params):
    response = client.get(f"{API}/processes", params=params)
    assert response.status_code == 422, (params, response.text)
    assert "Traceback" not in response.text and "DROP" not in response.text


def test_amount_filter_total_matches_the_rows_returned(client: TestClient):
    body = client.get(f"{API}/processes", params={"min_amount": 100, "page_size": 100}).json()
    assert body["total"] == len(body["items"]) == 3
    assert all(item["award_total"] >= 100 for item in body["items"])
