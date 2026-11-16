"""OpenTelemetry traces and metrics. Every function is a safe no-op without an endpoint."""

from veedor.infrastructure.telemetry.allowlist import register_vocabulary
from veedor.infrastructure.telemetry.asgi import TelemetryMiddleware, instrument_app
from veedor.infrastructure.telemetry.nodes import traced_node
from veedor.infrastructure.telemetry.runtime import (
    SpanHandle,
    is_enabled,
    record_grounding,
    record_investigation,
    record_llm_usage,
    record_specialist_run,
    record_tool_call,
    setup_telemetry,
    shutdown_telemetry,
    span,
)

__all__ = [
    "SpanHandle",
    "TelemetryMiddleware",
    "instrument_app",
    "is_enabled",
    "record_grounding",
    "record_investigation",
    "record_llm_usage",
    "record_specialist_run",
    "record_tool_call",
    "register_vocabulary",
    "setup_telemetry",
    "shutdown_telemetry",
    "span",
    "traced_node",
]
