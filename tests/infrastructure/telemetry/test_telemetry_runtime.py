"""No-op safety, metric recording, shutdown and the node bridge."""

from __future__ import annotations

import pytest

from veedor.core.settings import get_settings
from veedor.infrastructure.telemetry import (
    is_enabled,
    record_grounding,
    record_investigation,
    record_llm_usage,
    record_specialist_run,
    record_tool_call,
    register_vocabulary,
    setup_telemetry,
    shutdown_telemetry,
    span,
    traced_node,
)


def _value(capture, name: str, **labels):
    for metric, attributes, point in capture.metric_points():
        if metric == name and attributes == labels:
            return getattr(point, "value", None) if hasattr(point, "value") else point.sum
    raise AssertionError(f"series not found: {name} {labels}")


def test_everything_is_a_noop_without_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VEEDOR_OTEL_ENDPOINT", raising=False)
    get_settings.cache_clear()
    shutdown_telemetry()
    setup_telemetry("veedor-test")
    assert not is_enabled()
    with span("anything", ocid="x", tool="t") as handle:
        handle.set_attribute("tool", "t")
        handle.mark_error("E")
    record_llm_usage("m", 1, 2)
    record_tool_call("t", "ok", 1.0)
    record_grounding(True, "template")
    record_investigation("template", 5.0)
    record_specialist_run("company")
    shutdown_telemetry()  # idempotent
    get_settings.cache_clear()


def test_exceptions_still_propagate_when_disabled() -> None:
    shutdown_telemetry()
    with pytest.raises(KeyError), span("x"):
        raise KeyError("boom")


def test_metrics_are_recorded_with_expected_labels(capture) -> None:
    record_investigation("template", 120.0)
    record_investigation("llm")
    record_specialist_run("company", "ok")
    record_tool_call("get_compania_info", "ok", 250.0)
    record_tool_call("get_compania_info", "timeout", 5000.0)
    record_llm_usage("fake", 100, 40)
    record_grounding(True, "llm")
    record_grounding(False, "llm")
    assert _value(capture, "veedor.investigations", final_mode="template") == 1
    assert _value(capture, "veedor.specialist.runs", specialist="company", outcome="ok") == 1
    assert _value(capture, "veedor.tool.calls", tool="get_compania_info", outcome="timeout") == 1
    assert _value(capture, "veedor.llm.tokens", model="fake", token_type="prompt") == 100
    assert _value(capture, "veedor.llm.tokens", model="fake", token_type="completion") == 40
    assert _value(capture, "veedor.grounding.results", passed=False, mode="llm") == 1
    assert _value(capture, "veedor.tool.duration", tool="get_compania_info") == 5250.0


def test_traced_node_preserves_behaviour_and_emits_a_span(capture) -> None:
    register_vocabulary(node=["assess_signals"])  # graph nodes are registered by the graph owner

    @traced_node("assess_signals")
    def node(state: dict) -> dict:
        return {"seen": state["x"]}

    assert node({"x": 3}) == {"seen": 3}
    finished = capture.finished_spans()[0]
    assert finished.name == "node assess_signals"
    assert finished.attributes["node"] == "assess_signals"
    assert node.__name__ == "node"


def test_traced_node_is_transparent_when_disabled() -> None:
    shutdown_telemetry()

    @traced_node("n")
    def node(state: dict) -> dict:
        return {"ok": True}

    assert node({}) == {"ok": True}


def test_nested_spans_share_a_trace(capture) -> None:
    with span("investigation", ocid="ocds-5wno2w-ABC-1"), span("specialist", specialist="audit"):
        pass
    child, parent = capture.finished_spans()
    assert child.parent is not None and child.parent.span_id == parent.context.span_id
    assert child.context.trace_id == parent.context.trace_id


def test_shutdown_stops_recording_and_is_idempotent(capture) -> None:
    shutdown_telemetry()
    shutdown_telemetry()
    assert not is_enabled()
    with span("after shutdown"):
        pass
    assert capture.finished_spans() == ()
