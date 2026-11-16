# ruff: noqa: E501
"""Only `POST /processes/{ocid}/ask` may reach a language model (docs/SECURITY.md).

Two independent proofs: a static one (no other module of the API imports a model adapter) and a dynamic one
(every route is called with every model entry point replaced by a spy; none is touched except by `ask`)."""

from __future__ import annotations

import ast
from pathlib import Path

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

from veedor.api.main import create_app

API_DIR = Path(__file__).resolve().parents[2] / "src" / "veedor" / "api"
ALLOWED = {API_DIR / "ask_wiring.py", API_DIR / "v1" / "ask.py"}
FORBIDDEN_PREFIXES = ("veedor.infrastructure.llm", "veedor.agents", "langchain", "openai", "anthropic", "groq")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_no_other_module_of_the_api_imports_a_model_adapter():
    offenders = {}
    for path in sorted(API_DIR.rglob("*.py")):
        if path in ALLOWED:
            continue
        bad = sorted(m for m in imported_modules(path) if m.startswith(FORBIDDEN_PREFIXES))
        if bad:
            offenders[str(path.relative_to(API_DIR))] = bad
    assert offenders == {}


def test_the_modules_that_may_reach_a_model_are_exactly_the_wiring_and_the_ask_route():
    importers = {p for p in API_DIR.rglob("*.py") if any(m.startswith(FORBIDDEN_PREFIXES) for m in imported_modules(p))}
    assert importers <= ALLOWED and (API_DIR / "v1" / "ask.py") in importers | ALLOWED


def test_only_the_ask_route_is_a_post_that_takes_a_question():
    paths = create_app().openapi()["paths"]
    asks = [p for p, ops in paths.items() if p.endswith("/ask")]
    assert asks == ["/api/v1/processes/{ocid}/ask"]


@pytest.fixture
def spies(monkeypatch):
    """Every way to build or call a model client raises a recognisable error and records the attempt."""
    calls: list[str] = []

    def trap(name: str):
        def inner(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"model reached through {name}")

        return inner

    import veedor.infrastructure.llm.factory as factory
    import veedor.infrastructure.llm.langchain_model as lc
    import veedor.infrastructure.llm.structured as structured

    monkeypatch.setattr(factory, "build_chat_model", trap("build_chat_model"))
    monkeypatch.setattr(structured, "build_structured_model", trap("build_structured_model"))
    monkeypatch.setattr(lc.LangChainChatModel, "complete", trap("LangChainChatModel.complete"))
    monkeypatch.setattr(structured.LangChainStructuredModel, "complete_structured", trap("complete_structured"))
    return calls


def sample_value(parameter: dict) -> str:
    name = parameter["name"]
    return {"ocid": fx.OCID_COMPANY, "ruc": fx.COMPANY_RUC}.get(name, "1")


def test_no_route_but_ask_reaches_a_model_client_even_with_the_key_and_the_route_enabled(client: TestClient, spies, monkeypatch):
    from veedor.api.v1 import ask as ask_route
    from veedor.core.settings import Settings

    monkeypatch.setattr(ask_route, "get_settings", lambda: Settings(_env_file=None, ask_enabled=True, llm_provider="openai", llm_model="m", llm_api_key="not-a-real-key"))
    spec = client.app.openapi()
    client = TestClient(client.app, raise_server_exceptions=False)  # the fixture lake lacks some columns: 500 is fine here
    called = 0
    for path, operations in spec["paths"].items():
        if path.endswith("/ask"):
            continue
        for method, operation in operations.items():
            url = path.replace("{ocid}", fx.OCID_COMPANY).replace("{ruc}", fx.COMPANY_RUC)
            for param in operation.get("parameters", []):
                if param["in"] == "path" and "{" + param["name"] + "}" in url:
                    url = url.replace("{" + param["name"] + "}", sample_value(param))
            body = {"json": {}} if method in ("post", "put", "patch") else {}
            response = client.request(method.upper(), url, **body)
            called += 1
            assert "model reached" not in response.text
    assert called > 20
    assert spies == []  # not one route reached a model client


def test_the_ask_route_does_reach_it_when_enabled_with_a_key(client: TestClient, monkeypatch):
    """The positive control: the spy would have fired."""
    import veedor.api.ask_wiring as wiring
    from veedor.api import ask_wiring
    from veedor.api.v1 import ask as ask_route
    from veedor.core.settings import Settings
    from veedor.infrastructure.llm.fake import FakeStructuredModel

    seen = []
    model = FakeStructuredModel([{"answerable": False, "fact_ids": [], "reason": "sin_datos"}])
    original = model.complete_structured
    model.complete_structured = lambda *a, **k: (seen.append(1), original(*a, **k))[1]
    settings = Settings(_env_file=None, ask_enabled=True, llm_provider="openai", llm_model="m", llm_api_key="k")
    monkeypatch.setattr(ask_route, "get_settings", lambda: settings)
    monkeypatch.setattr(wiring, "build_structured_model", lambda s: model)
    monkeypatch.setattr(wiring, "_embedder", lambda: __import__("veedor.infrastructure.vectors.embedding", fromlist=["FakeEmbedder"]).FakeEmbedder())
    from veedor.api.deps import get_reader

    wiring.get_ask_service.cache_clear()
    ask_route._limits = None
    try:
        reader = client.app.dependency_overrides[get_reader]()
        monkeypatch.setattr(wiring, "get_reader", lambda: reader)
        monkeypatch.setattr(wiring, "EvidenceReader", lambda *a, **k: type("R", (), {"load": staticmethod(lambda ocid: __import__("test_api_ask").packs(ocid))})())
        service = wiring.build_service(settings, reader)
        service.thresholds = __import__("test_api_ask").THRESHOLDS
        client.app.dependency_overrides[ask_wiring.get_ask_service] = lambda: service
        response = client.post(f"/api/v1/processes/{fx.OCID_COMPANY}/ask", json={"question": "numero de oferentes inicio de ofertas y cierre de ofertas"})
    finally:
        wiring.get_ask_service.cache_clear()
        ask_route._limits = None
    assert response.status_code == 200 and response.json()["mode"] == "model" and seen == [1]
