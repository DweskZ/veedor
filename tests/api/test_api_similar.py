"""GET /processes/{ocid}/similar over the synthetic lake with an in-memory vector store."""

from __future__ import annotations

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

from veedor.api.v1.similar import get_vector_store
from veedor.use_cases.similar_processes import Neighbour, ProcessNotIndexed, VectorsUnavailable

API = "/api/v1"
UNIT = "ocds-5wno2w-test-0002"
PAYLOADS = [
    "' OR 1=1 --",
    "'; DROP TABLE process_vectors; --",
    "1; SELECT pg_sleep(5)",
    "%00",
    "../../../etc/passwd",
    "${jndi:ldap://x}",
    "9" * 400,
    "-1",
    "1e999",
]


class FakeStore:
    """Indexed: the two company/natural processes and one natural-person-buyer process."""

    indexed = {fx.OCID_COMPANY, fx.OCID_NATURAL, fx.OCID_DIRECT, "ocds-5wno2w-test-0005"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, bool]] = []

    def neighbours(self, ocid: str, k: int, same_buyer: bool) -> list[Neighbour]:
        self.calls.append((ocid, k, same_buyer))
        if ocid not in self.indexed:
            raise ProcessNotIndexed(ocid)
        rows = [
            Neighbour(fx.OCID_NATURAL, 0.91, 2023, fx.BUYER_RUC, "Cotización", 500.0, "532100111"),
            Neighbour("ocds-5wno2w-test-0005", 0.85, 2022, fx.NATURAL_BUYER_RUC, "Cotización", None, None),
            Neighbour(
                fx.OCID_DIRECT, 0.5, 2022, fx.OTHER_BUYER_RUC, "Contratación directa", 200.0, "532100999"
            ),
        ]
        if same_buyer:
            rows = [r for r in rows if r.buyer_ruc == fx.BUYER_RUC]
        return [r for r in rows if r.ocid != ocid][:k]


class DownStore:
    def neighbours(self, ocid: str, k: int, same_buyer: bool):
        raise VectorsUnavailable("down")


@pytest.fixture
def store(client: TestClient) -> FakeStore:
    fake = FakeStore()
    client.app.dependency_overrides[get_vector_store] = lambda: fake
    return fake


def test_returns_neighbours_best_first(client: TestClient, store: FakeStore) -> None:
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar", params={"k": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["ocid"] == fx.OCID_COMPANY and body["k"] == 2 and body["same_buyer"] is False
    assert [i["ocid"] for i in body["items"]] == [fx.OCID_NATURAL, "ocds-5wno2w-test-0005"]
    first = body["items"][0]
    assert first["similarity"] == 0.91 and first["buyer_name"] == fx.BUYER_NAME and first["year"] == 2023
    assert store.calls == [(fx.OCID_COMPANY, 2, False)]


def test_defaults_and_same_buyer(client: TestClient, store: FakeStore) -> None:
    body = client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar", params={"same_buyer": "true"}).json()
    assert store.calls == [(fx.OCID_COMPANY, 10, True)]
    assert {i["buyer_ruc"] for i in body["items"]} == {fx.BUYER_RUC}


def test_natural_person_buyer_is_masked(client: TestClient, store: FakeStore) -> None:
    text = client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar").text
    assert fx.NATURAL_BUYER_NAME not in text and fx.NATURAL_BUYER_RUC not in text
    item = next(i for i in client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar").json()["items"]
                if i["ocid"] == "ocds-5wno2w-test-0005")  # fmt: skip
    assert (
        item["buyer_name"] == "Persona natural"
        and item["buyer_ruc"] == fx.NATURAL_BUYER_RUC[:4] + "*********"
    )


def test_unknown_process_is_404(client: TestClient, store: FakeStore) -> None:
    response = client.get(f"{API}/processes/ocds-5wno2w-does-not-exist/similar")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_known_but_unindexed_process_is_404_not_indexed(client: TestClient, store: FakeStore) -> None:
    response = client.get(f"{API}/processes/{fx.OCID_LAKE_ONLY}/similar")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_indexed"


def test_unavailable_index_is_503(client: TestClient) -> None:
    client.app.dependency_overrides[get_vector_store] = DownStore
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "vectors_unavailable"


def test_database_down_without_override_is_503(no_db_client: TestClient) -> None:
    response = no_db_client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "vectors_unavailable"


@pytest.mark.parametrize(
    "params",
    [{"k": 0}, {"k": 51}, {"k": -3}, {"k": "abc"}, {"k": "1.5"}, {"same_buyer": "maybe"}, {"k": ""}],
)
def test_invalid_params_are_422(client: TestClient, store: FakeStore, params: dict) -> None:
    assert client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar", params=params).status_code == 422
    assert store.calls == []


@pytest.mark.parametrize("payload", PAYLOADS)
@pytest.mark.parametrize("param", ["k", "same_buyer"])
def test_payloads_in_query_params_never_reach_the_store_or_500(
    client: TestClient, store: FakeStore, payload: str, param: str
) -> None:
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar", params={param: payload})
    assert response.status_code == 422
    assert "Traceback" not in response.text and "SELECT" not in response.text
    assert store.calls == []


@pytest.mark.parametrize("payload", PAYLOADS)
def test_payloads_in_the_path_are_rejected(client: TestClient, store: FakeStore, payload: str) -> None:
    response = client.get(f"{API}/processes/{payload}/similar")
    assert response.status_code in {404, 422}
    assert "Traceback" not in response.text
    assert store.calls == []


def test_k_boundaries_are_accepted(client: TestClient, store: FakeStore) -> None:
    assert client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar", params={"k": 1}).status_code == 200
    assert client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar", params={"k": 50}).status_code == 200


def test_response_carries_the_notice_and_no_accusatory_wording(client: TestClient, store: FakeStore) -> None:
    text = client.get(f"{API}/processes/{fx.OCID_COMPANY}/similar").text.lower()
    assert "no indica una señal de riesgo ni una acusación" in text
    assert "corrupto" not in text and "fraude" not in text
