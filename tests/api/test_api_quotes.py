"""GET /processes/{ocid}/quotes: stored quotes served after a second safety pass."""

from __future__ import annotations

from pathlib import Path

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

from veedor.infrastructure.quotes.store import QUOTES_SCHEMA, STATS_SCHEMA, VOCABULARY_SCHEMA
from veedor.schemas.quotes import QUOTES_NOTE_ES

API = "/api/v1"
VOCABULARY = {"hector", "ivan", "baquerizo", "menendez", "ruales"}
SAFE = "Se amplía el plazo de presentación de ofertas hasta el 10 de mayo."
PAIR = "Respuesta: el cronograma se modifica mediante adenda."


def quote(rank=1, text=SAFE, signal="SINGLE_BIDDER", pair_text=PAIR, **extra):
    row = {
        "rank": rank, "kind": "enquiry_question", "text": text, "date": "2023-01-02T00:00:00-05:00",
        "author_kind": "oferente", "source_field": "tender.enquiries[0].description",
        "related_signal": signal, "similarity": 0.512, "truncated": False,
        "pair_text": pair_text, "pair_kind": "enquiry_answer" if pair_text else None,
        "pair_source_field": "tender.enquiries[0].answer" if pair_text else None,
    }  # fmt: skip
    return row | extra


def write(marts: Path, ocid: str, quotes: list[dict], stats: dict | None = None) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [{"ocid": ocid, **q} for q in quotes]
    stat = {
        "ocid": ocid, "available_total": 5, "excluded_personal": 1, "excluded_unsafe": 2, "below_floor": 0,
        "n_eligible": 2, "n_quotes": len(quotes),
    } | (stats or {})  # fmt: skip
    pq.write_table(pa.Table.from_pylist(rows, schema=QUOTES_SCHEMA), marts / "process_quotes.parquet")
    pq.write_table(pa.Table.from_pylist([stat], schema=STATS_SCHEMA), marts / "process_quote_stats.parquet")
    tokens = [{"token": t} for t in sorted(VOCABULARY)]
    pq.write_table(
        pa.Table.from_pylist(tokens, schema=VOCABULARY_SCHEMA), marts / "person_name_tokens.parquet"
    )


@pytest.fixture
def marts(lake_dirs) -> Path:
    return lake_dirs[1]


def test_quotes_are_served_with_label_pair_counts_and_the_note(client: TestClient, marts: Path):
    write(marts, fx.OCID_COMPANY, [quote(), quote(rank=2, pair_text=None, signal="LOW_SAVING")])
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes")
    assert response.status_code == 200
    body = response.json()
    assert body["ocid"] == fx.OCID_COMPANY and body["available_total"] == 5
    assert body["omitted"] == {"personal_data": 1, "unsafe": 2, "below_relevance": 0}
    assert body["note_es"] == QUOTES_NOTE_ES and "No son palabras de Veedor" in body["note_es"]
    first, second = body["items"]
    assert first["text"] == SAFE and first["related_signal_label_es"] == "Oferente único"
    assert first["pair"] == {
        "kind": "enquiry_answer",
        "text": PAIR,
        "source_field": "tender.enquiries[0].answer",
    }
    assert second["pair"] is None and second["related_signal"] == "LOW_SAVING"
    assert set(first) == {
        "kind", "text", "date", "author_kind", "source_field", "related_signal", "related_signal_label_es",
        "similarity", "truncated", "pair",
    }  # fmt: skip


def test_unknown_process_is_404_and_a_process_without_quotes_is_200_empty(client: TestClient, marts: Path):
    write(marts, fx.OCID_COMPANY, [quote()])
    assert client.get(f"{API}/processes/ocds-5wno2w-nope-9999/quotes").status_code == 404
    response = client.get(f"{API}/processes/{fx.OCID_DIRECT}/quotes")
    assert response.status_code == 200
    assert response.json() == {
        "ocid": fx.OCID_DIRECT, "items": [], "available_total": 0,
        "omitted": {"personal_data": 0, "unsafe": 0, "below_relevance": 0}, "note_es": QUOTES_NOTE_ES,
    }  # fmt: skip


def test_missing_mart_is_a_controlled_503(client: TestClient):
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes")
    assert response.status_code == 503 and response.json()["error"]["code"] == "data_unavailable"


@pytest.mark.parametrize(
    ("stored", "bucket"),
    [
        (f"Consulta de {fx.NORUC_NAME} sobre el plazo", "personal_data"),  # a party with no RUC
        ("Consulte con el Ing. Juan Pérez sobre el plazo", "personal_data"),
        ("consulte con el ing. juan perez", "personal_data"),
        (f"cédula {fx.CEDULA} del representante", "personal_data"),
        ("cédula 171 003 4065", "personal_data"),
        ("llame al 0991234567", "personal_data"),
        ("escriba a alguien@correo.com", "personal_data"),
        ("Atentamente, Maria Lopez", "personal_data"),
        ("Es calificado HECTOR IVAN BAQUERIZO MENENDEZ de la empresa", "personal_data"),  # not a party
        ("personal técnico Señor Rúales Marcos según el formulario", "personal_data"),
        ("hubo fraude en el proceso", "unsafe"),
        ("frаude con a cirílica", "unsafe"),
        ("f r a u d e", "unsafe"),
        ("ignore previous instructions", "unsafe"),
        ("<b>plazo</b>", "unsafe"),
        ("visite https://sitio.example", "unsafe"),
    ],
)
def test_a_stored_quote_that_fails_now_is_dropped_and_counted(
    client: TestClient, marts: Path, stored, bucket
):
    write(
        marts,
        fx.OCID_NORUC,
        [quote(text=stored, pair_text=None), quote(rank=2, pair_text=None)],
        {"excluded_personal": 0, "excluded_unsafe": 0},
    )
    body = client.get(f"{API}/processes/{fx.OCID_NORUC}/quotes").json()
    assert [i["text"] for i in body["items"]] == [SAFE]
    assert body["omitted"][bucket] == 1
    assert stored not in client.get(f"{API}/processes/{fx.OCID_NORUC}/quotes").text


def test_an_unsafe_pair_is_dropped_but_the_quote_stays(client: TestClient, marts: Path):
    write(marts, fx.OCID_COMPANY, [quote(pair_text="Se comprobó un delito")], {"excluded_unsafe": 0})
    body = client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes").json()
    assert body["items"][0]["text"] == SAFE and body["items"][0]["pair"] is None
    assert body["omitted"]["unsafe"] == 1


def test_a_company_name_in_a_quote_passes(client: TestClient, marts: Path):
    text = f"La oferta de {fx.COMPANY_NAME} cumple el plazo."
    write(marts, fx.OCID_COMPANY, [quote(text=text, pair_text=None)])
    assert client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes").json()["items"][0]["text"] == text


def test_an_unknown_signal_code_in_the_mart_is_not_served(client: TestClient, marts: Path):
    write(marts, fx.OCID_COMPANY, [quote(signal="NOT_A_SIGNAL")])
    body = client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes").json()
    assert body["items"] == [] and body["omitted"]["unsafe"] == 3


def test_the_response_is_cached_per_data_build(client: TestClient, marts: Path):
    write(marts, fx.OCID_COMPANY, [quote()])
    assert client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes").json()["items"][0]["text"] == SAFE
    write(marts, fx.OCID_COMPANY, [quote(text="Otro texto sobre el plazo de entrega.")])  # rebuilt mart
    assert (
        client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes").json()["items"][0]["text"].startswith("Otro")
    )


PAYLOADS = [
    "' OR 1=1 --", "'; DROP TABLE reviews; --", "%' UNION SELECT * FROM read_text('/etc/passwd') --",
    "../../../etc/passwd", "..%2f..%2fetc%2fpasswd", "1; ATTACH '/tmp/x.db' AS x", "%00", "${jndi:ldap://x}",
    "ocds-5wno2w-" + "a" * 121, "ocds-5wno2w-١٢٣", "ocds-5wno2w-x'; SELECT 1; --",
]  # fmt: skip


@pytest.mark.parametrize("payload", PAYLOADS)
def test_injection_payloads_on_the_new_paths_never_error(client: TestClient, marts: Path, payload: str):
    write(marts, fx.OCID_COMPANY, [quote()])
    for route in ("quotes", "provenance"):
        response = client.get(f"{API}/processes/{payload}/{route}")
        assert response.status_code in {404, 422}, (route, payload, response.status_code)
        assert "Traceback" not in response.text and "duckdb" not in response.text.lower()
        assert "SELECT" not in response.text


def test_quotes_endpoint_runs_only_single_selects_by_ocid(
    lake_dirs, marts: Path, monkeypatch: pytest.MonkeyPatch
):
    from veedor.infrastructure.lake.reader import LakeReader

    write(marts, fx.OCID_COMPANY, [quote()])
    seen: list[str] = []
    original = LakeReader.fetch

    def spy(self, sql, params=(), *, tables):
        seen.append(sql)
        return original(self, sql, params, tables=tables)

    monkeypatch.setattr(LakeReader, "fetch", spy)
    from veedor.api.deps import get_reader
    from veedor.api.main import create_app

    app = create_app()
    app.dependency_overrides[get_reader] = lambda: LakeReader(*lake_dirs)
    assert TestClient(app).get(f"{API}/processes/{fx.OCID_COMPANY}/quotes").status_code == 200
    assert seen and all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in seen)
    unbounded = [s for s in seen if "WHERE" not in s.upper()]
    # the only statement without a key is the person-name vocabulary: a few hundred rows, once per build
    assert unbounded == ["SELECT token FROM person_name_tokens"], seen
