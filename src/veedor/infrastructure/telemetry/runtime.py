"""Provider setup, the `span` helper and the metric recorders.

Everything is a no-op until `setup_telemetry` ran with an endpoint (or test exporters). The
module keeps its own providers instead of installing global ones, so it never interferes with
other OpenTelemetry users and can be set up again in tests.
"""

from __future__ import annotations

import atexit
import logging
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

from veedor.core.settings import get_settings
from veedor.infrastructure.telemetry.allowlist import METRIC_LABELS, SPAN_ATTRIBUTES, safe_span_name, sanitize

log = logging.getLogger(__name__)

INSTRUMENTATION_NAME = "veedor"
EXPORT_TIMEOUT_SECONDS = 5.0
METRIC_EXPORT_INTERVAL_MS = 5000
FLUSH_TIMEOUT_MS = 5000
TOOL_DURATION_BUCKETS_MS = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 20000, 40000]
INVESTIGATION_DURATION_BUCKETS_MS = [250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 120000, 300000]
HTTP_DURATION_BUCKETS_S = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]


@dataclass
class _Instruments:
    investigations: Counter
    investigation_duration: Histogram
    specialist_runs: Counter
    tool_calls: Counter
    tool_duration: Histogram
    llm_tokens: Counter
    grounding: Counter
    http_duration: Histogram


@dataclass
class _State:
    tracer: Tracer
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    instruments: _Instruments


_state: _State | None = None
_lock = threading.Lock()
_atexit_registered = False


def _service_version() -> str:
    try:
        return version("veedor")
    except PackageNotFoundError:
        return "0.0.0"


def _build_instruments(meter: Meter) -> _Instruments:
    return _Instruments(
        investigations=meter.create_counter(
            "veedor.investigations", unit="{investigation}", description="Finished investigations."
        ),
        investigation_duration=meter.create_histogram(
            "veedor.investigation.duration",
            unit="ms",
            description="Wall time of one investigation.",
            explicit_bucket_boundaries_advisory=INVESTIGATION_DURATION_BUCKETS_MS,
        ),
        specialist_runs=meter.create_counter(
            "veedor.specialist.runs", unit="{run}", description="Specialist agent runs."
        ),
        tool_calls=meter.create_counter("veedor.tool.calls", unit="{call}", description="Tool calls."),
        tool_duration=meter.create_histogram(
            "veedor.tool.duration",
            unit="ms",
            description="Tool call latency.",
            explicit_bucket_boundaries_advisory=TOOL_DURATION_BUCKETS_MS,
        ),
        llm_tokens=meter.create_counter("veedor.llm.tokens", unit="{token}", description="LLM tokens."),
        grounding=meter.create_counter(
            "veedor.grounding.results", unit="{check}", description="Grounding verification results."
        ),
        http_duration=meter.create_histogram(
            "http.server.request.duration",
            unit="s",
            description="Duration of HTTP server requests.",
            explicit_bucket_boundaries_advisory=HTTP_DURATION_BUCKETS_S,
        ),
    )


def _install(
    service_name: str,
    span_exporter: SpanExporter,
    metric_reader: MetricReader,
    *,
    batch_spans: bool,
) -> None:
    global _state, _atexit_registered
    resource = Resource.create({"service.name": service_name, "service.version": _service_version()})
    tracer_provider = TracerProvider(resource=resource)  # default sampler: always on (100 %)
    processor = BatchSpanProcessor(span_exporter) if batch_spans else SimpleSpanProcessor(span_exporter)
    tracer_provider.add_span_processor(processor)
    meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource, shutdown_on_exit=False)
    _state = _State(
        tracer=tracer_provider.get_tracer(INSTRUMENTATION_NAME),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        instruments=_build_instruments(meter_provider.get_meter(INSTRUMENTATION_NAME)),
    )
    if not _atexit_registered:
        atexit.register(shutdown_telemetry)
        _atexit_registered = True


def setup_telemetry(
    service_name: str,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> None:
    """Enable tracing and metrics. No-op when `VEEDOR_OTEL_ENDPOINT` is unset.

    The keyword-only exporter arguments exist for tests: they replace the OTLP exporters.
    """
    endpoint = (get_settings().otel_endpoint or "").rstrip("/")
    with _lock:
        if _state is not None:
            return
        if span_exporter is not None or metric_reader is not None:
            from opentelemetry.sdk.metrics.export import InMemoryMetricReader
            from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

            _install(
                service_name,
                span_exporter or InMemorySpanExporter(),
                metric_reader or InMemoryMetricReader(),
                batch_spans=False,
            )
            return
        if not endpoint:
            return
        _install(
            service_name,
            OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", timeout=EXPORT_TIMEOUT_SECONDS),
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", timeout=EXPORT_TIMEOUT_SECONDS),
                export_interval_millis=METRIC_EXPORT_INTERVAL_MS,
            ),
            batch_spans=True,
        )
        log.info("telemetry enabled for %s", service_name)


def shutdown_telemetry() -> None:
    """Flush pending spans and metrics, then stop. Idempotent; also runs at interpreter exit."""
    global _state
    with _lock:
        state, _state = _state, None
    if state is None:
        return
    for provider in (state.tracer_provider, state.meter_provider):
        try:
            provider.force_flush(FLUSH_TIMEOUT_MS)
            provider.shutdown()
        except Exception:  # noqa: BLE001 - telemetry must never break the caller
            log.warning("telemetry shutdown failed", exc_info=False)


def is_enabled() -> bool:
    return _state is not None


class SpanHandle:
    """What `span()` yields: attribute setters that pass through the allow-list."""

    def __init__(self, span: Span | None) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        if self._span is None:
            return
        for k, v in sanitize({key: value}, SPAN_ATTRIBUTES).items():
            self._span.set_attribute(k, v)

    def set_attributes(self, **attributes: Any) -> None:
        for key, value in attributes.items():
            self.set_attribute(key, value)

    def update_name(self, name: str) -> None:
        if self._span is not None:
            self._span.update_name(safe_span_name(name))

    def mark_error(self, error_type: str | None = None) -> None:
        """Flag the span as failed. Never records the exception message (it may hold free text)."""
        if self._span is None:
            return
        self._span.set_status(Status(StatusCode.ERROR))
        if error_type:
            self.set_attribute("error.type", error_type)


@contextmanager
def _open_span(name: str, kind: SpanKind, attributes: dict[str, Any]) -> Iterator[SpanHandle]:
    state = _state
    if state is None:
        yield SpanHandle(None)
        return
    with state.tracer.start_as_current_span(
        safe_span_name(name),
        kind=kind,
        attributes=sanitize(attributes, SPAN_ATTRIBUTES),
        record_exception=False,
        set_status_on_exception=False,
    ) as raw:
        handle = SpanHandle(raw)
        try:
            yield handle
        except BaseException as error:
            handle.mark_error(type(error).__name__)
            raise


def span(name: str, **attributes: Any) -> AbstractContextManager[SpanHandle]:
    """Open a span. Attributes outside the allow-list are dropped. No-op when disabled."""
    return _open_span(name, SpanKind.INTERNAL, attributes)


def server_span(name: str, **attributes: Any) -> AbstractContextManager[SpanHandle]:
    """Like `span`, with kind SERVER (used by the HTTP middleware)."""
    return _open_span(name, SpanKind.SERVER, attributes)


def _labels(**labels: Any) -> dict[str, Any]:
    return sanitize(labels, METRIC_LABELS)


def record_llm_usage(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    state = _state
    if state is None:
        return
    for token_type, count in (("prompt", prompt_tokens), ("completion", completion_tokens)):
        if count and count > 0:
            state.instruments.llm_tokens.add(int(count), _labels(model=model, token_type=token_type))


def record_tool_call(tool: str, outcome: str, duration_ms: float) -> None:
    state = _state
    if state is None:
        return
    state.instruments.tool_calls.add(1, _labels(tool=tool, outcome=outcome))
    state.instruments.tool_duration.record(max(float(duration_ms), 0.0), _labels(tool=tool))


def record_grounding(passed: bool, mode: str) -> None:
    state = _state
    if state is None:
        return
    state.instruments.grounding.add(1, _labels(passed=bool(passed), mode=mode))


def record_investigation(final_mode: str, duration_ms: float | None = None) -> None:
    """Count one finished investigation by its final mode (extra helper, not in the contract)."""
    state = _state
    if state is None:
        return
    state.instruments.investigations.add(1, _labels(final_mode=final_mode))
    if duration_ms is not None:
        state.instruments.investigation_duration.record(max(float(duration_ms), 0.0), _labels())


def record_specialist_run(specialist: str, outcome: str = "ok") -> None:
    """Count one specialist run (extra helper, not in the contract)."""
    state = _state
    if state is None:
        return
    state.instruments.specialist_runs.add(1, _labels(specialist=specialist, outcome=outcome))


def record_http_request(method: str, route: str, status: int, duration_s: float) -> None:
    state = _state
    if state is None:
        return
    state.instruments.http_duration.record(
        max(duration_s, 0.0),
        _labels(**{"http.request.method": method, "http.route": route, "http.response.status_code": status}),
    )
