"""Sprint H.0b Story 9 — structlog configured per Q16 discipline."""

from __future__ import annotations


def test_logger_returns_structlog_bound_logger() -> None:
    from src.observability.logging import get_logger
    log = get_logger("test")
    # Bound loggers expose .info/.warning/.error/etc.
    assert hasattr(log, "info")
    assert hasattr(log, "error")
    assert hasattr(log, "exception")


def test_processor_chain_includes_redactor() -> None:
    from src.observability.logging import _processor_names
    names = _processor_names()
    assert any("redactor" in n.lower() or "redact" in n.lower() for n in names), (
        "Q16 mandates secret-redaction processor in the chain"
    )


def test_logger_event_field_carried() -> None:
    """Smoke: emitting a log call doesn't crash and renders to JSON."""
    import io
    from src.observability.logging import configure_for_test_capture, get_logger

    buf = io.StringIO()
    configure_for_test_capture(buf)
    log = get_logger("test")
    log.info("event_under_test", session_id="sess-1")
    output = buf.getvalue()
    assert "event_under_test" in output
    assert "sess-1" in output
