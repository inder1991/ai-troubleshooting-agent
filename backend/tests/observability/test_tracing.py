"""Sprint H.0b Story 9 — OpenTelemetry tracer initialized."""

from __future__ import annotations


def test_get_tracer_returns_a_tracer() -> None:
    from src.observability.tracing import get_tracer
    tracer = get_tracer("test")
    # OpenTelemetry tracers expose start_as_current_span.
    assert hasattr(tracer, "start_as_current_span")


def test_span_creation_does_not_crash() -> None:
    from src.observability.tracing import get_tracer
    tracer = get_tracer("test")
    with tracer.start_as_current_span("test.span", attributes={"k": "v"}):
        pass
