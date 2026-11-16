"""GET /processes/{ocid}/investigation: stored records only, masked, 404 when absent."""

from __future__ import annotations

from datetime import UTC, datetime

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

from veedor.api.v1.investigations import get_investigation_store
from veedor.domain.dossier.models import Dossier, GroundingReport, Section
from veedor.domain.investigation.models import InvestigationRecord, ToolCall
from veedor.infrastructure.investigations.store import InvestigationStore

API = "/api/v1"


def record(ocid: str, text: str) -> InvestigationRecord:
    now = datetime.now(UTC)
    return InvestigationRecord(
        ocid=ocid, started_at=now, finished_at=now, renderer_version=6,
        tool_log=[ToolCall(specialist="company", tool="get_compania_info", target="winner", started_at=now,
                           ended_at=now, duration_ms=1.0, outcome="ok")],
        dossier=Dossier(ocid=ocid, generated_at=now, mode="template", summary_es=text,
                        sections=[Section(title="Investigación realizada", body=text)], sources=[],
                        grounding_report=GroundingReport(passed=True, n_checked=0)),
    )  # fmt: skip


@pytest.fixture
def stored(client: TestClient, tmp_path):
    store = InvestigationStore(tmp_path / "investigations")
    client.app.dependency_overrides[get_investigation_store] = lambda: store
    return store


def test_absent_investigation_is_404_and_nothing_is_started(client, stored, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("an HTTP request must never run an investigation")

    monkeypatch.setattr("veedor.use_cases.investigate.InvestigationService.investigate", boom, raising=False)
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/investigation")
    assert response.status_code == 404
    assert stored.ocids() == []


def test_stored_investigation_is_served(client, stored):
    stored.save(record(fx.OCID_COMPANY, "Resumen de la investigación."))
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/investigation")
    assert response.status_code == 200
    body = response.json()
    assert body["ocid"] == fx.OCID_COMPANY and body["tool_log"][0]["outcome"] == "ok"
    assert body["dossier"]["mode"] == "template"


def test_response_is_masked_like_every_other(client, stored):
    leak = f"{fx.NATURAL_NAME} participó; cédula {fx.NATURAL_RUC}"
    with pytest.raises(Exception, match="personal RUC"):  # the writer refuses it ...
        stored.save(record(fx.OCID_NATURAL, leak))
    stored.directory.mkdir(parents=True, exist_ok=True)  # ... so plant an old file to test the boundary
    stored.path(fx.OCID_NATURAL).write_text(record(fx.OCID_NATURAL, leak).model_dump_json())
    response = client.get(f"{API}/processes/{fx.OCID_NATURAL}/investigation")
    assert response.status_code == 200
    assert fx.NATURAL_NAME not in response.text and fx.NATURAL_RUC not in response.text


def test_malformed_ocid_is_rejected(client, stored):
    assert client.get(f"{API}/processes/not-an-ocid/investigation").status_code == 422
