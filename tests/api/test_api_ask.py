# ruff: noqa: E501
"""POST /processes/{ocid}/ask: disabled by default, retrieval without a key, limits, masking, no trace."""

from __future__ import annotations

import sys
from pathlib import Path

import api_fixture_data as fx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qa"))

from qa_support import LogCapture  # noqa: E402

from veedor.agents.qa.selector import ModelSelector  # noqa: E402
from veedor.api import ask_wiring
from veedor.api.v1 import ask as ask_route
from veedor.core.settings import Settings
from veedor.domain.qa.selection import Thresholds
from veedor.infrastructure.lake.reader import LakeReader
from veedor.infrastructure.llm.fake import FakeStructuredModel
from veedor.infrastructure.vectors.embedding import FakeEmbedder
from veedor.use_cases.ask import AskService, DailyBudget
from veedor.use_cases.queries.ask_context import ApiContextLoader

API = "/api/v1"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dossier"
THRESHOLDS = Thresholds(floor=0.2, k=2, model_floor=0.05, candidates=40, quote_floor=0.2)
QUESTION = "numero de oferentes inicio de ofertas y cierre de ofertas"


def packs(ocid: str):
    """Evidence packs of the dossier fixtures under the API fixture's identifiers; the natural-person
    process leaks a name on purpose (a sentence holding an identifier is dropped earlier), to exercise the last
    masking net of the route."""
    from veedor.domain.dossier.models import EvidencePack

    if ocid not in (fx.OCID_COMPANY, fx.OCID_NATURAL):
        return None
    pack = EvidencePack.model_validate_json((FIXTURES / "pack_full.json").read_text())
    process = pack.process.model_copy(update={"ocid": ocid})
    if ocid == fx.OCID_NATURAL:
        process = process.model_copy(update={"buyer_name": fx.NATURAL_NAME})
    return pack.model_copy(update={"process": process})


@pytest.fixture
def enable(monkeypatch, lake_dirs: tuple[Path, Path], client: TestClient):
    """Turn the route on with a service over the synthetic lake; returns a function to adjust the service."""
    state = {"settings": Settings(
            _env_file=None, ask_enabled=True, ask_rate_per_minute=600, ask_rate_per_hour=10_000,
            ask_retrieval_rate_per_minute=600, ask_retrieval_rate_per_hour=10_000,
        )}
    monkeypatch.setattr(ask_route, "get_settings", lambda: state["settings"])
    ask_route._limits = None

    def build(replies: list | None = None, budget: int | None = None) -> AskService:
        lake = LakeReader(*lake_dirs)
        selector = ModelSelector(FakeStructuredModel(replies)) if replies is not None else None
        service = AskService(
            ApiContextLoader(lake, packs, lambda ocid: None),
            FakeEmbedder(), selector, THRESHOLDS,
            budget=DailyBudget(budget) if budget is not None else None,
        )  # fmt: skip
        client.app.dependency_overrides[ask_wiring.get_ask_service] = lambda: service
        return service

    build.settings = state
    build()
    yield build
    ask_route._limits = None


def post(client, ocid=fx.OCID_COMPANY, question=QUESTION):
    return client.post(f"{API}/processes/{ocid}/ask", json={"question": question})


def test_the_route_is_off_by_default_and_a_disabled_route_is_a_plain_404(client: TestClient):
    for body in ({"question": QUESTION}, {"question": ""}, {"nada": 1}):
        response = client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", json=body)
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    assert client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", content=b"\xff\x00").status_code == 404


def test_enabled_without_a_model_it_answers_by_retrieval(client, enable):
    response = post(client)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "retrieval" and body["answerable"] and body["reason"] == "answered"
    assert set(body) == {"ocid", "answerable", "mode", "reason", "sentences", "quotes", "note_es"}
    assert body["sentences"] and set(body["sentences"][0]) == {"text", "fact_id", "source_id", "source_field"}
    assert {s["fact_id"] for s in body["sentences"]} & {"process.tenderers", "process.award_dates"}
    assert response.headers["cache-control"] == "no-store"


def test_a_judgement_question_gets_the_fixed_sentence(client, enable):
    body = post(client, question="¿Hubo corrupción en este proceso?").json()
    assert body["answerable"] is False and body["reason"] == "judgement" and body["sentences"] == []
    assert "no emite juicios" in body["note_es"]


@pytest.mark.parametrize("question", ["a", "x" * 301, "uno\ndos", "¿Quién ganó? ¿Cuánto costó?", ""])
def test_a_malformed_question_is_a_422_that_does_not_repeat_it(client, enable, question):
    response = post(client, question=question)
    assert response.status_code == 422
    assert len(question.strip()) < 6 or question[:12] not in response.text


def test_a_natural_person_winner_is_masked_in_every_answer(client, enable):
    for question in ("entidad contratante quien compro ruc de la entidad", QUESTION, "region y localidad de la entidad"):
        response = post(client, fx.OCID_NATURAL, question)
        assert response.status_code == 200
        assert fx.NATURAL_NAME not in response.text and fx.CEDULA not in response.text and "Ficticia" not in response.text
    enable([{"answerable": True, "fact_ids": ["process.entity"], "reason": "directa"}])
    leaking = post(client, fx.OCID_NATURAL, "entidad contratante quien compro").json()
    assert [s["fact_id"] for s in leaking["sentences"]] == ["process.entity"]  # the sentence is there, masked
    assert fx.NATURAL_NAME not in str(leaking) and "[persona natural]" in str(leaking)


def test_an_unknown_process_is_a_404_and_a_bad_path_a_422(client, enable):
    assert post(client, "ocds-5wno2w-does-not-exist").status_code == 404
    for ocid in ("not-an-ocid", "ocds-5wno2w-" + "a" * 200, "ocds-5wno2w-x%00", "ocds-5wno2w-'; DROP TABLE x;--"):
        assert post(client, ocid).status_code in (404, 422)


def test_per_ip_rate_limit_answers_429(client, enable):
    enable.settings["settings"] = Settings(_env_file=None, ask_enabled=True, ask_retrieval_rate_per_minute=3)
    codes = [post(client).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert "Demasiadas" in post(client).json()["error"]["message"]


def test_retrieval_only_answers_have_a_generous_limit_and_model_answers_the_strict_one(client, enable):
    """Five suggested questions in a row must not be blocked without a model (default 4 per minute for the model)."""
    defaults = Settings(_env_file=None, ask_enabled=True)
    assert (defaults.ask_rate_per_minute, defaults.ask_rate_per_hour) == (4, 30)
    assert (defaults.ask_retrieval_rate_per_minute, defaults.ask_retrieval_rate_per_hour) == (20, 200)
    enable.settings["settings"] = defaults
    assert [post(client).status_code for _ in range(6)] == [200] * 6  # retrieval only: generous pair
    reply = {"answerable": True, "fact_ids": ["process.tenderers"], "reason": "directa"}
    enable([reply] * 8)  # a model can be called: the strict pair applies
    ask_route._limits = None
    codes = [post(client, question=f"{QUESTION} {n}").status_code for n in range(6)]
    assert codes == [200, 200, 200, 200, 429, 429]
    assert "retry-after" in post(client).headers


def test_a_429_carries_retry_after_and_cors_exposes_it(client, enable):
    enable.settings["settings"] = Settings(_env_file=None, ask_enabled=True, ask_retrieval_rate_per_minute=1)
    origin = {"Origin": "http://localhost:3000"}
    assert client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", json={"question": QUESTION}, headers=origin).status_code == 200
    blocked = client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", json={"question": QUESTION}, headers=origin)
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 60  # the minute window is the one that is full
    assert "retry-after" in blocked.headers["access-control-expose-headers"].lower()
    assert blocked.json()["error"]["code"] == "http_error"


def test_retry_after_is_the_longer_wait_when_the_hour_window_is_full(client, enable):
    enable.settings["settings"] = Settings(
        _env_file=None, ask_enabled=True, ask_retrieval_rate_per_minute=100, ask_retrieval_rate_per_hour=1
    )
    assert post(client).status_code == 200
    blocked = post(client)
    assert blocked.status_code == 429 and 60 < int(blocked.headers["retry-after"]) <= 3600


def test_with_a_model_the_daily_budget_falls_back_to_retrieval_not_to_an_error(client, enable):
    reply = {"answerable": True, "fact_ids": ["process.tenderers"], "reason": "directa"}
    enable([reply] * 4, budget=1)
    first = post(client, question=QUESTION).json()
    second = post(client, question="inicio de ofertas, cierre de ofertas y numero de oferentes").json()
    assert first["mode"] == "model" and second["mode"] == "retrieval" and second["answerable"]


def test_a_model_that_misbehaves_never_changes_what_the_route_may_say(client, enable):
    hostile = {"answerable": True, "fact_ids": ["process.tenderers", "x.y"], "reason": "directa", "texto": "culpable"}
    enable([hostile])
    body = post(client).json()
    assert body["mode"] == "retrieval"
    assert "culpable" not in str(body)


@pytest.mark.parametrize(
    "payload",
    ["'; DROP TABLE processes; --", "../../etc/passwd", "<script>alert(1)</script>", "${jndi:ldap://x/a}", "{{7*7}}", "%00%0d%0a", "a" * 5000, "‮", "ｉｇｎｏｒａ"],
)
def test_injection_payloads_in_the_body_never_cause_a_500_and_are_never_echoed(client, enable, payload):
    response = post(client, question=payload)
    assert response.status_code in (200, 422) and response.status_code != 500
    assert payload not in response.text or len(payload) < 4


def test_extra_or_mistyped_body_fields_are_rejected(client, enable):
    assert client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", json={"question": QUESTION, "extra": 1}).status_code == 422
    assert client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", json={"question": ["x"]}).status_code == 422
    assert client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", json=[QUESTION]).status_code == 422


def test_a_body_over_16_kib_is_refused(client, enable):
    assert client.post(f"{API}/processes/{fx.OCID_COMPANY}/ask", json={"question": "a" * 20_000}).status_code == 413


def test_the_question_is_in_no_log_record_and_no_span_attribute(client, enable):
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from veedor.infrastructure import telemetry

    exporter = InMemorySpanExporter()
    telemetry.shutdown_telemetry()
    telemetry.setup_telemetry("test", span_exporter=exporter)
    secret = "zafiro inicio de ofertas numero de oferentes cierre de ofertas"
    try:
        with LogCapture() as logs:
            assert post(client, question=secret).status_code == 200
            assert post(client, question="¿Hubo corrupción? zafiro").status_code == 200
            assert post(client, question="zafiro\n").status_code == 422
    finally:
        spans = exporter.get_finished_spans()
        telemetry.shutdown_telemetry()
    spans_text = repr([(s.name, dict(s.attributes or {})) for s in spans])
    assert "zafiro" not in logs.text and "zafiro" not in spans_text and "qhash=" in logs.text
    names = {s.name for s in spans}
    assert "ask" in names
    ask_span = next(s for s in spans if s.name == "ask")
    assert dict(ask_span.attributes).get("mode") == "retrieval" and "ocid" in ask_span.attributes
