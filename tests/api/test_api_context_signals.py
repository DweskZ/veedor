"""Risk vs context signals are distinguished everywhere they are exposed."""

from __future__ import annotations

import api_fixture_data as fx
from fastapi.testclient import TestClient

API = "/api/v1"


def test_detail_signals_carry_their_kind(client: TestClient) -> None:
    body = client.get(f"{API}/processes/{fx.OCID_COMPANY}").json()
    kinds = {s["code"]: s["kind"] for s in body["signals"]}
    assert kinds == {"GHOST_COMPANY_LISTED_LATER": "context", "LOW_SAVING": "risk", "SINGLE_BIDDER": "risk"}
    assert body["score"]["n_context_signals"] == 1
    assert body["score"]["context_signal_codes"] == [fx.CONTEXT_CODE]


def test_detail_kind_falls_back_to_the_domain_definition(client: TestClient) -> None:
    """The unparseable-evidence row still has a kind."""
    body = client.get(f"{API}/processes/ocds-5wno2w-test-0005").json()
    assert body["signals"][0]["kind"] == "risk"


def test_list_items_expose_context_signals(client: TestClient) -> None:
    rows = {r["ocid"]: r for r in client.get(f"{API}/processes").json()["items"]}
    assert rows[fx.OCID_COMPANY]["n_context_signals"] == 1
    assert rows[fx.OCID_COMPANY]["context_signal_codes"] == [fx.CONTEXT_CODE]
    assert rows[fx.OCID_COMPANY]["signal_codes"] == ["SINGLE_BIDDER", "LOW_SAVING"]  # risk only
    assert (
        rows[fx.OCID_DIRECT]["n_context_signals"] == 0 and rows[fx.OCID_DIRECT]["context_signal_codes"] == []
    )


def test_signal_filter_works_for_context_codes(client: TestClient) -> None:
    body = client.get(f"{API}/processes", params={"signal": fx.CONTEXT_CODE}).json()
    assert body["total"] == 1 and body["items"][0]["ocid"] == fx.OCID_COMPANY
    assert client.get(f"{API}/processes", params={"signal": "SINGLE_BIDDER"}).json()["total"] == 3


def test_catalogue_marks_context_signals_from_the_domain(client: TestClient) -> None:
    from veedor.domain.signals import SIGNALS

    served = {s["code"]: s["kind"] for s in client.get(f"{API}/signals").json()}
    assert served == {s.code: s.kind for s in SIGNALS}
    assert fx.CONTEXT_CODE in served and set(served.values()) == {"risk", "context"}


def test_stats_report_risk_and_context_separately(client: TestClient) -> None:
    body = client.get(f"{API}/stats").json()
    assert {c["code"] for c in body["signal_counts"]} == {"SINGLE_BIDDER", "LOW_SAVING"}
    assert all(c["kind"] == "risk" for c in body["signal_counts"])
    assert body["context_signal_counts"] == [
        {
            "code": fx.CONTEXT_CODE,
            "label_es": body["context_signal_counts"][0]["label_es"],
            "kind": "context",
            "count": 1,
        }
    ]


def test_openapi_documents_the_new_fields(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert "kind" in schemas["FiredSignal"]["properties"]
    assert "kind" in schemas["SignalInfo"]["properties"]
    assert {"n_context_signals", "context_signal_codes"} <= set(schemas["ProcessSummary"]["properties"])
    assert "context_signal_counts" in schemas["Stats"]["properties"]
