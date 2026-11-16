"""The allow-list is the privacy gate: nothing outside it reaches an exporter."""

from __future__ import annotations

import pytest

from veedor.core.settings import get_settings
from veedor.infrastructure.telemetry import (
    record_grounding,
    record_llm_usage,
    record_specialist_run,
    record_tool_call,
    register_vocabulary,
    span,
)
from veedor.infrastructure.telemetry.allowlist import METRIC_LABELS, SPAN_ATTRIBUTES, sanitize

RUC = "1790012345001"
NATURAL_RUC = "0912345678001"
NAME = "Juan Perez Alvarado"
OCID = "ocds-5wno2w-LICO-GADMC-001-2023-1790012345001"
# Joined-name and identifier-shaped strings the reviewer used to get past the generic token rule.
BYPASSES = [
    "JUAN-PEREZ-LOPEZ",
    "Jose:Maria:Perez",
    "17900-16919-001",
    "juan_perez",
    RUC,
    f"ocds-5wno2w-{'x' * 9}",
]


def _span(**attributes) -> dict:
    return sanitize(attributes, SPAN_ATTRIBUTES)


# ---- keys -----------------------------------------------------------------------------------


def test_disallowed_key_with_ruc_or_free_text_never_reaches_the_exporter(capture) -> None:
    with span(
        "investigator.run",
        ocid=OCID,
        supplier_ruc=RUC,
        winner_name=NAME,
        prompt=f"Explain {NAME} {RUC}",
        note="free text",
        tool_result={"x": NATURAL_RUC},
    ):
        pass
    text = capture.everything_as_text()
    for forbidden in ("supplier_ruc", "winner_name", "prompt=", "note=", "tool_result"):
        assert forbidden not in text
    assert NAME not in text
    assert NATURAL_RUC not in text
    assert text.replace(f"ocid={OCID}", "").count(RUC) == 0
    assert f"ocid={OCID}" in text  # the one identifier that is allowed, under its own key


# ---- numbers: per-key ranges ----------------------------------------------------------------


@pytest.mark.parametrize("key", ["n_signals", "n_findings", "n_tool_calls", "n_dispatches", "attempt"])
def test_count_keys_reject_identifier_sized_and_negative_numbers(key: str) -> None:
    assert _span(**{key: 1790016919001}) == {}
    assert _span(**{key: -1}) == {}
    assert _span(**{key: 2.5}) == {}
    assert _span(**{key: True}) == {}
    assert _span(**{key: 3}) == {key: 3}


@pytest.mark.parametrize("key", ["prompt_tokens", "completion_tokens"])
def test_token_counts_are_capped(key: str) -> None:
    assert _span(**{key: 1790016919001}) == {}
    assert _span(**{key: 1200}) == {key: 1200}


def test_duration_is_capped_finite_and_non_negative() -> None:
    assert _span(duration_ms=1790016919001) == {}
    assert _span(duration_ms=float("nan")) == {}
    assert _span(duration_ms=float("inf")) == {}
    assert _span(duration_ms=-0.1) == {}
    assert _span(duration_ms=850.5) == {"duration_ms": 850.5}


def test_status_code_must_be_a_real_http_status() -> None:
    assert _span(**{"http.response.status_code": 1790016919001}) == {}
    assert _span(**{"http.response.status_code": 99}) == {}
    assert _span(**{"http.response.status_code": 404}) == {"http.response.status_code": 404}


def test_a_string_is_never_accepted_for_a_numeric_key_and_passed_must_be_bool() -> None:
    assert _span(n_signals=RUC, duration_ms="12", passed="true") == {}
    assert _span(passed=True) == {"passed": True}


# ---- closed vocabularies: unknown values become `other` ---------------------------------------


@pytest.mark.parametrize("key", ["tool", "outcome", "specialist", "final_mode", "mode", "node", "token_type"])
@pytest.mark.parametrize("bad", BYPASSES + [NAME, "x" * 200])
def test_closed_vocabulary_keys_replace_unknown_values_with_other(key: str, bad: str) -> None:
    assert _span(**{key: bad}) == {key: "other"}


def test_legitimate_vocabulary_values_pass_unchanged() -> None:
    attributes = _span(
        tool="get_compania_info",
        specialist="tax_registry",
        outcome="upstream_error",
        final_mode="template_minimal",
        mode="llm",
        token_type="prompt",
    )
    assert attributes == {
        "tool": "get_compania_info",
        "specialist": "tax_registry",
        "outcome": "upstream_error",
        "final_mode": "template_minimal",
        "mode": "llm",
        "token_type": "prompt",
    }
    assert _span(outcome="partial") == {"outcome": "partial"}  # a specialist run can end partial


def test_metric_labels_use_the_same_rules(capture) -> None:
    record_tool_call("JUAN-PEREZ-LOPEZ", "Jose:Maria:Perez", 12.0)
    record_specialist_run("17900-16919-001", "ok")
    record_grounding(True, "NAME-SURNAME")
    text = capture.everything_as_text()
    for bad in ("JUAN", "Jose", "17900", "NAME-SURNAME"):
        assert bad not in text
    series = {(name, tuple(sorted(attrs.items()))) for name, attrs, _ in capture.metric_points()}
    assert ("veedor.tool.calls", (("outcome", "other"), ("tool", "other"))) in series
    assert ("veedor.specialist.runs", (("outcome", "ok"), ("specialist", "other"))) in series
    assert ("veedor.grounding.results", (("mode", "other"), ("passed", True))) in series


def test_register_vocabulary_extends_a_closed_set() -> None:
    assert _span(node="supervisor") == {"node": "other"}
    register_vocabulary(node=["supervisor", "assemble_evidence"])
    assert _span(node="supervisor") == {"node": "supervisor"}
    assert _span(node="JUAN-PEREZ") == {"node": "other"}


@pytest.mark.parametrize("bad", ["JUAN-PEREZ", "has space", RUC, "x" * 100, ""])
def test_register_vocabulary_refuses_identifier_unlike_entries(bad: str) -> None:
    with pytest.raises(ValueError):
        register_vocabulary(node=[bad])
    with pytest.raises(ValueError):
        register_vocabulary(not_a_key=["x"])


# ---- error.type -----------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["ocds-5wno2w-ABC-1", NAME, RUC, "JuanPerezLopez", "Error:Juan", "x" * 70])
def test_error_type_outside_the_exception_list_becomes_other(bad: str) -> None:
    assert _span(**{"error.type": bad}) == {"error.type": "other"}


def test_error_type_accepts_real_exception_names_and_registered_ones() -> None:
    assert _span(**{"error.type": "ValueError"}) == {"error.type": "ValueError"}
    assert _span(**{"error.type": "TimeoutError"}) == {"error.type": "TimeoutError"}
    assert _span(**{"error.type": "DispatchRejected"}) == {"error.type": "other"}
    register_vocabulary(**{"error.type": ["DispatchRejected"]})
    assert _span(**{"error.type": "DispatchRejected"}) == {"error.type": "DispatchRejected"}


def test_exception_message_is_never_recorded_and_custom_class_is_other(capture) -> None:
    class JuanPerez(Exception):
        pass

    with pytest.raises(ValueError), span("tool", tool="get_compania_info"):
        raise ValueError(f"{NAME} {RUC}")
    with pytest.raises(JuanPerez), span("tool"):
        raise JuanPerez(NAME)
    first, second = capture.finished_spans()
    assert first.attributes["error.type"] == "ValueError"
    assert second.attributes["error.type"] == "other"
    assert first.events == ()
    text = capture.everything_as_text()
    assert NAME not in text and RUC not in text and "JuanPerez" not in text


# ---- model ----------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", BYPASSES + [NAME, "gpt-" + "9" * 12])
def test_model_not_configured_becomes_other(bad: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEEDOR_LLM_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    assert _span(model=bad) == {"model": "other"}


def test_configured_model_and_its_dated_variant_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEEDOR_LLM_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    assert _span(model="gpt-4o-mini") == {"model": "gpt-4o-mini"}
    assert _span(model="gpt-4o-mini-2024-07-18") == {"model": "gpt-4o-mini-2024-07-18"}
    assert _span(model="fake") == {"model": "fake"}
    assert _span(model="gpt-4o-mini JUAN") == {"model": "other"}
    get_settings.cache_clear()


def test_registered_model_passes() -> None:
    assert _span(model="my-local-model") == {"model": "other"}
    register_vocabulary(model=["my-local-model"])
    assert _span(model="my-local-model") == {"model": "my-local-model"}


# ---- ocid and route -------------------------------------------------------------------------


def test_ocid_shape_is_enforced(capture) -> None:
    with span("investigation", ocid=OCID):
        pass
    assert capture.finished_spans()[0].attributes["ocid"] == OCID
    for bad in ["ocds-5wno2w", "not-an-ocid", f"ocds-5wno2w-{'x' * 200}", RUC, f"{OCID}\n"]:
        assert "ocid" not in _span(ocid=bad)


def test_ocid_under_another_key_is_never_kept() -> None:
    for key in ("error.type", "tool", "outcome", "model", "node", "http.route"):
        assert _span(**{key: OCID}).get(key, "other") in {"other"}


@pytest.mark.parametrize(
    "bad", ["/api/v1/suppliers/JUAN-PEREZ", f"/api/v1/suppliers/{RUC}", "/a b", "x" * 300]
)
def test_http_route_must_be_a_lowercase_template(bad: str) -> None:
    assert "http.route" not in _span(**{"http.route": bad})


def test_http_route_accepts_templates_and_unmatched() -> None:
    for good in ("/api/v1/processes/{ocid}/dossier", "/api/v1/stats", "unmatched"):
        assert _span(**{"http.route": good}) == {"http.route": good}


def test_http_method_outside_the_known_set_becomes_other() -> None:
    assert _span(**{"http.request.method": "JUAN"}) == {"http.request.method": "other"}
    assert _span(**{"http.request.method": "GET"}) == {"http.request.method": "GET"}


# ---- structure ------------------------------------------------------------------------------


def test_non_scalar_values_are_dropped() -> None:
    assert _span(tool=["a"], outcome={"a": 1}, attempt=None) == {}


def test_metric_labels_are_a_low_cardinality_subset() -> None:
    assert "ocid" not in METRIC_LABELS
    assert METRIC_LABELS <= SPAN_ATTRIBUTES


def test_span_name_carrying_an_identifier_is_replaced(capture) -> None:
    with span(f"lookup {RUC}"):
        pass
    with span(f"process {OCID}"):
        pass
    assert {s.name for s in capture.finished_spans()} == {"invalid_span_name"}


def test_metrics_drop_disallowed_keys_and_record_legitimate_series(capture) -> None:
    record_tool_call("get_compania_info", "ok", 12.0)
    record_llm_usage("fake", 10, 5)
    record_grounding(True, "template")
    series = {(name, tuple(sorted(attrs.items()))) for name, attrs, _ in capture.metric_points()}
    assert ("veedor.tool.calls", (("outcome", "ok"), ("tool", "get_compania_info"))) in series
    assert ("veedor.llm.tokens", (("model", "fake"), ("token_type", "prompt"))) in series
