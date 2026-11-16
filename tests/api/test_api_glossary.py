"""`GET /glossary`: served from one file, validated strictly, 503 when the file cannot be trusted."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from veedor.api.deps import get_glossary_store
from veedor.api.main import create_app
from veedor.core.settings import Settings
from veedor.infrastructure import glossary as glossary_module
from veedor.infrastructure.glossary import GlossaryStore, GlossaryUnavailableError, parse_glossary

API = "/api/v1"
ENTRY = {
    "term": "Oferente",
    "aliases": ["oferentes", "licitante"],
    "definition_es": "Empresa que presenta una oferta en un proceso de compra.",
    "source": "Redacción de Veedor.",
}


@pytest.fixture
def glossary_client(tmp_path: Path) -> Callable[[object], tuple[TestClient, Path]]:
    path = tmp_path / "glossary.json"

    def build(content: object) -> tuple[TestClient, Path]:
        if isinstance(content, bytes):
            path.write_bytes(content)
        elif content is not None:
            path.write_text(json.dumps(content), encoding="utf-8")
        app = create_app()
        app.dependency_overrides[get_glossary_store] = lambda: GlossaryStore(path)
        return TestClient(app), path

    return build


def test_serves_the_items_of_the_file(glossary_client) -> None:
    client, _ = glossary_client({"items": [ENTRY, {**ENTRY, "term": "Adjudicación", "source": None}]})
    response = client.get(f"{API}/glossary")
    assert response.status_code == 200
    assert response.json() == {
        "items": [ENTRY, {**ENTRY, "term": "Adjudicación", "source": None}],
    }


def test_a_bare_list_is_accepted_and_unknown_keys_are_dropped(glossary_client) -> None:
    client, _ = glossary_client([{**ENTRY, "id": 7, "slug": "oferente"}])
    assert client.get(f"{API}/glossary").json() == {"items": [ENTRY]}


def test_aliases_default_to_empty_and_source_is_optional(glossary_client) -> None:
    client, _ = glossary_client([{"term": "RUC", "definition_es": "Número de contribuyente."}])
    assert client.get(f"{API}/glossary").json()["items"] == [
        {"term": "RUC", "aliases": [], "definition_es": "Número de contribuyente.", "source": None}
    ]


def test_missing_file_is_a_controlled_503(glossary_client) -> None:
    client, path = glossary_client(None)
    assert not path.exists()
    response = client.get(f"{API}/glossary")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "glossary_unavailable"
    assert str(path) not in response.text


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b"",
        b"\xff\xfe\x00",
        json.dumps({"items": []}).encode(),
        json.dumps({"items": "x"}).encode(),
        json.dumps({"entries": [ENTRY]}).encode(),
        json.dumps("text").encode(),
        json.dumps([ENTRY, {**ENTRY, "term": "oferente"}]).encode(),  # duplicate, case-insensitive
        json.dumps([{**ENTRY, "term": ""}]).encode(),
        json.dumps([{**ENTRY, "term": "x" * 101}]).encode(),
        json.dumps([{**ENTRY, "definition_es": "x" * 1501}]).encode(),
        json.dumps([{**ENTRY, "definition_es": "   "}]).encode(),
        json.dumps([{**ENTRY, "source": "x" * 301}]).encode(),
        json.dumps([{**ENTRY, "aliases": ["a"] * 21}]).encode(),
        json.dumps([{**ENTRY, "aliases": [1]}]).encode(),
        json.dumps([{**ENTRY, "aliases": "oferentes"}]).encode(),
        json.dumps([{**ENTRY, "term": 5}]).encode(),
        json.dumps([{**ENTRY, "term": "Ofe\x00rente"}]).encode(),
        json.dumps([{**ENTRY, "definition_es": "a‮b"}]).encode(),
        json.dumps([{**ENTRY, "aliases": ["a\tb"]}]).encode(),
        json.dumps(["just a string"]).encode(),
        json.dumps([{"term": "RUC"}]).encode(),
        json.dumps([{**ENTRY, "term": f"t{i}"} for i in range(401)]).encode(),
        b"[" * 100_000,
    ],
)
def test_invalid_content_is_a_503_not_a_partial_answer(glossary_client, content: bytes) -> None:
    client, _ = glossary_client(content)
    response = client.get(f"{API}/glossary")
    assert response.status_code == 503 and response.json()["error"]["code"] == "glossary_unavailable"


def test_a_file_over_the_size_cap_is_refused(glossary_client, monkeypatch) -> None:
    monkeypatch.setattr(glossary_module, "MAX_FILE_BYTES", 50)
    client, _ = glossary_client([ENTRY])
    assert client.get(f"{API}/glossary").status_code == 503


def test_newlines_are_allowed_in_definitions(glossary_client) -> None:
    client, _ = glossary_client([{**ENTRY, "definition_es": "Primera línea.\nSegunda línea."}])
    assert (
        client.get(f"{API}/glossary").json()["items"][0]["definition_es"] == "Primera línea.\nSegunda línea."
    )


def test_the_file_is_reread_when_it_changes(glossary_client) -> None:
    client, path = glossary_client([ENTRY])
    assert len(client.get(f"{API}/glossary").json()["items"]) == 1
    path.write_text(json.dumps([ENTRY, {**ENTRY, "term": "Presupuesto referencial"}]), encoding="utf-8")
    assert len(client.get(f"{API}/glossary").json()["items"]) == 2
    path.write_text("broken", encoding="utf-8")
    assert client.get(f"{API}/glossary").status_code == 503
    path.write_text(json.dumps([ENTRY]), encoding="utf-8")
    assert client.get(f"{API}/glossary").status_code == 200


def test_unchanged_file_is_not_parsed_again(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "g.json"
    path.write_text(json.dumps([ENTRY]), encoding="utf-8")
    store = GlossaryStore(path)
    store.items()
    calls = []
    real = glossary_module.parse_glossary
    monkeypatch.setattr(glossary_module, "parse_glossary", lambda raw: calls.append(1) or real(raw))
    store.items()
    store.items()
    assert calls == []


def test_parse_glossary_raises_a_single_error_type() -> None:
    with pytest.raises(GlossaryUnavailableError):
        parse_glossary(b'{"items": [{"term": "a"}]}')


def test_default_path_is_the_web_content_file() -> None:
    assert Settings().glossary_path.parts[-4:] == ("web", "src", "data", "glossary.json")


def test_the_repository_glossary_file_passes_the_strict_validation() -> None:
    path = Settings().glossary_path
    if not path.is_file():
        pytest.skip("web/src/data/glossary.json is not present")
    items = parse_glossary(path.read_bytes())
    assert items and all(item["definition_es"] for item in items)


def test_compose_mounts_the_glossary_read_only_for_the_api() -> None:
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    api = compose.split("\n  api:\n", 1)[1].split("\n  web:", 1)[0]
    assert "./web/src/data:/app/web/src/data:ro" in api
    assert "VEEDOR_GLOSSARY_PATH: /app/web/src/data/glossary.json" in api
