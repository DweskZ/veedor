from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veedor.core.settings import get_settings
from veedor.infrastructure.telemetry import allowlist, setup_telemetry, shutdown_telemetry


@dataclass
class Capture:
    spans: InMemorySpanExporter
    metrics: InMemoryMetricReader

    def finished_spans(self):
        return self.spans.get_finished_spans()

    def metric_points(self) -> list[tuple[str, dict, object]]:
        """Flatten to (metric name, attributes, point) for every data point."""
        data = self.metrics.get_metrics_data()
        points = []
        for resource_metrics in data.resource_metrics if data else []:
            for scope in resource_metrics.scope_metrics:
                for metric in scope.metrics:
                    for point in metric.data.data_points:
                        points.append((metric.name, dict(point.attributes), point))
        return points

    def everything_as_text(self) -> str:
        """Every span name, attribute, event and metric label/name as one string."""
        parts: list[str] = []
        for finished in self.finished_spans():
            parts.append(finished.name)
            parts.extend(f"{k}={v}" for k, v in (finished.attributes or {}).items())
            parts.append(str(finished.status.description))
            for event in finished.events:
                parts.append(event.name)
                parts.extend(f"{k}={v}" for k, v in (event.attributes or {}).items())
        for name, attributes, _ in self.metric_points():
            parts.append(name)
            parts.extend(f"{k}={v}" for k, v in attributes.items())
        return "\n".join(parts)


@pytest.fixture(autouse=True)
def _fresh_vocabulary() -> Iterator[None]:
    allowlist._vocab = None  # registrations made by a test must not leak into the next
    yield
    allowlist._vocab = None


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> Iterator[Capture]:
    monkeypatch.delenv("VEEDOR_OTEL_ENDPOINT", raising=False)
    get_settings.cache_clear()
    shutdown_telemetry()
    spans, metrics = InMemorySpanExporter(), InMemoryMetricReader()
    setup_telemetry("veedor-test", span_exporter=spans, metric_reader=metrics)
    yield Capture(spans, metrics)
    shutdown_telemetry()
    get_settings.cache_clear()
