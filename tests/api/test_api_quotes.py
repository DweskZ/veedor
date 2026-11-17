"""GET /processes/{ocid}/quotes: stored quotes served after a second safety pass."""

from __future__ import annotations

from pathlib import Path

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

from veedor.core.settings import get_settings
from veedor.infrastructure.quotes.store import (
    LEXICON_SCHEMA,
    QUOTES_SCHEMA,
    STATS_SCHEMA,
    VOCABULARY_SCHEMA,
)
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
        "pair_truncated": False,
    }  # fmt: skip
    return row | extra


# Institutional capitalised words and ordinary words of the synthetic mart (what the build would store).
LEX_CAP = {"oferta", "sercop", "mayo", "adenda", "cronograma", "consulta"}
LEX_LOW = set(
    "se amplia el plazo de presentacion de ofertas hasta respuesta modifica mediante la oferta cumple "
    "otro texto sobre entrega consulta de con calificado es del personal tecnico segun formulario "
    "hubo en proceso ignore previous instructions visite".split()
)


def write(
    marts: Path,
    ocid: str,
    quotes: list[dict],
    stats: dict | None = None,
    *,
    vocabulary: bool = True,
    lexicon: bool = True,
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [{"ocid": ocid, **q} for q in quotes]
    stat = {
        "ocid": ocid, "available_total": 5, "excluded_personal": 1, "excluded_unsafe": 2, "below_floor": 0,
        "n_eligible": 2, "n_quotes": len(quotes),
    } | (stats or {})  # fmt: skip
    pq.write_table(pa.Table.from_pylist(rows, schema=QUOTES_SCHEMA), marts / "process_quotes.parquet")
    pq.write_table(pa.Table.from_pylist([stat], schema=STATS_SCHEMA), marts / "process_quote_stats.parquet")
    if lexicon:
        lex = [{"token": t, "form": "capitalised"} for t in sorted(LEX_CAP)]
        lex += [{"token": t, "form": "lowercase"} for t in sorted(LEX_LOW)]
        pq.write_table(pa.Table.from_pylist(lex, schema=LEXICON_SCHEMA), marts / "quote_lexicon.parquet")
    if not vocabulary:
        return
    tokens = [{"token": t} for t in sorted(VOCABULARY)]
    pq.write_table(
        pa.Table.from_pylist(tokens, schema=VOCABULARY_SCHEMA), marts / "person_name_tokens.parquet"
    )


@pytest.fixture
def marts(lake_dirs) -> Path:
    return lake_dirs[1]


@pytest.fixture(autouse=True)
def quotes_on(monkeypatch: pytest.MonkeyPatch):
    """Quotes are off by default; these tests exercise the route with the flag on."""
    monkeypatch.setenv("VEEDOR_QUOTES_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_quotes_are_off_by_default_a_plain_404_that_hides_the_mart(
    client: TestClient, marts: Path, monkeypatch: pytest.MonkeyPatch
):
    write(marts, fx.OCID_COMPANY, [quote()])
    monkeypatch.delenv("VEEDOR_QUOTES_ENABLED")
    get_settings.cache_clear()
    for ocid in (fx.OCID_COMPANY, "ocds-5wno2w-nope-9999"):
        response = client.get(f"{API}/processes/{ocid}/quotes")
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
        assert SAFE not in response.text
    assert client.get(f"{API}/meta").json()["quotes_enabled"] is False


def test_meta_reports_quotes_enabled_next_to_ask_enabled(client: TestClient):
    body = client.get(f"{API}/meta").json()
    assert body["quotes_enabled"] is True and body["ask_enabled"] is False


def test_a_mart_without_the_lexicon_is_refused_not_served_unscreened(client: TestClient, marts: Path):
    write(marts, fx.OCID_COMPANY, [quote()], lexicon=False)
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes")
    assert response.status_code == 503 and response.json()["error"]["code"] == "data_unavailable"


def test_a_stored_passage_with_an_unknown_capitalised_word_is_dropped_by_the_deny_by_default_screen(
    client: TestClient, marts: Path
):
    stored = "Se amplía el plazo según Zorgonplim Wuxy sobre la oferta."
    write(marts, fx.OCID_COMPANY, [quote(text=stored, pair_text=None), quote(rank=2, pair_text=None)])
    body = client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes").json()
    assert [i["text"] for i in body["items"]] == [SAFE]
    assert body["omitted"]["personal_data"] == 2  # 1 stored by the build + this one


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
        "truncated": False,
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
    # the only statements without a key are the person-name vocabulary and the lexicon: once per build
    assert sorted(unbounded) == [
        "SELECT token FROM person_name_tokens",
        "SELECT token, form FROM quote_lexicon",
    ], seen


def test_quotes_are_served_without_the_name_vocabulary_table(client: TestClient, marts: Path):
    write(marts, fx.OCID_COMPANY, [quote()], vocabulary=False)
    response = client.get(f"{API}/processes/{fx.OCID_COMPANY}/quotes")
    assert response.status_code == 200 and response.json()["items"][0]["text"] == SAFE


@pytest.mark.parametrize(
    "ocid",
    ["ocds-5wno2w-CLC-GAD-MC- 001-2017-91883", "ocds-5wno2w-CDC-AMASL–001-2016-710584"],
)
def test_widened_identifiers_reach_the_route_and_are_simply_unknown(
    client: TestClient, marts: Path, ocid: str
):
    write(marts, fx.OCID_COMPANY, [quote()])
    assert client.get(f"{API}/processes/{ocid}/quotes").status_code == 404
    # accepted by the pattern, not in the fixture
    assert client.get(f"{API}/processes/{ocid}").status_code == 404


@pytest.mark.parametrize(
    "ocid", ["ocds-5wno2w-A%2FB", "ocds-5wno2w-A'B", "ocds-5wno2w-A­B", "ocds-5wno2w-..%2F..%2Fx"]
)
def test_unsafe_identifiers_are_still_422(client: TestClient, ocid: str):
    assert client.get(f"{API}/processes/{ocid}").status_code in {404, 422}
    assert client.get(f"{API}/processes/{ocid}/provenance").status_code in {404, 422}
