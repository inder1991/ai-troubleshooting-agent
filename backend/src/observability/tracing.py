"""Q16 epsilon — OpenTelemetry tracer initialization.

Auto-instruments fastapi/httpx/sqlalchemy when their modules are imported.
Manual span requirement on agent runners + workflow steps lives in the
agent code itself; this module just provides the tracer factory."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_initialized = False
_in_memory_exporter: InMemorySpanExporter | None = None


def configure_default(service_name: str = "debugduck") -> None:
    """Wire the default tracer provider with an in-memory exporter.

    Production swaps this for OTLP (deferred to a follow-up sprint when
    prod telemetry lands). In-memory keeps tests deterministic and
    avoids pytest-stdout-closure clashes that plague ConsoleSpanExporter.
    """
    global _initialized, _in_memory_exporter
    if _initialized:
        return
    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)
    _in_memory_exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(_in_memory_exporter))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_finished_spans() -> list:
    """Test helper: return spans captured by the in-memory exporter."""
    if _in_memory_exporter is None:
        return []
    return list(_in_memory_exporter.get_finished_spans())


def get_tracer(name: str = "debugduck"):
    if not _initialized:
        configure_default()
    return trace.get_tracer(name)
