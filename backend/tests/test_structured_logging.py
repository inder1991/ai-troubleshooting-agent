"""Tests for Structured Logging — Task 62."""
import json
import logging
import pytest


class TestJSONFormatter:
    def test_outputs_valid_json(self):
        from src.utils.structured_logging import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"

    def test_includes_timestamp(self):
        from src.utils.structured_logging import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="ts test",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed
        assert len(parsed["timestamp"]) > 0

    def test_includes_log_level(self):
        from src.utils.structured_logging import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="warn test",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "WARNING"

    def test_includes_logger_name(self):
        from src.utils.structured_logging import JSONFormatter
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="my.custom.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="name test",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["logger"] == "my.custom.logger"

    def test_includes_correlation_id(self):
        from src.utils.structured_logging import JSONFormatter, correlation_id
        # Set a known correlation ID
        token = correlation_id.set("abc123")
        try:
            formatter = JSONFormatter()
            record = logging.LogRecord(
                name="test_logger",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="corr test",
                args=None,
                exc_info=None,
            )
            output = formatter.format(record)
            parsed = json.loads(output)
            assert parsed["correlation_id"] == "abc123"
        finally:
            correlation_id.reset(token)

    def test_empty_correlation_id(self):
        from src.utils.structured_logging import JSONFormatter, correlation_id
        # Ensure clean state
        token = correlation_id.set("")
        try:
            formatter = JSONFormatter()
            record = logging.LogRecord(
                name="test_logger",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="empty corr",
                args=None,
                exc_info=None,
            )
            output = formatter.format(record)
            parsed = json.loads(output)
            assert parsed["correlation_id"] == ""
        finally:
            correlation_id.reset(token)


class TestNewCorrelationId:
    def test_generates_unique_ids(self):
        from src.utils.structured_logging import new_correlation_id
        ids = {new_correlation_id() for _ in range(100)}
        assert len(ids) == 100

    def test_sets_context_var(self):
        from src.utils.structured_logging import new_correlation_id, correlation_id
        cid = new_correlation_id()
        assert correlation_id.get() == cid

    def test_id_is_8_chars(self):
        from src.utils.structured_logging import new_correlation_id
        cid = new_correlation_id()
        assert len(cid) == 8


class TestSetupStructuredLogging:
    def test_setup_configures_root_logger(self):
        from src.utils.structured_logging import setup_structured_logging, JSONFormatter
        # Create a temporary logger to test
        logger = logging.getLogger("test_structured_setup")
        logger.handlers.clear()
        setup_structured_logging(level="DEBUG")
        root = logging.getLogger()
        # Check that at least one handler has JSONFormatter
        json_handlers = [
            h for h in root.handlers
            if isinstance(h.formatter, JSONFormatter)
        ]
        assert len(json_handlers) >= 1
        # Clean up
        for h in json_handlers:
            root.removeHandler(h)

    def test_setup_with_info_level(self):
        from src.utils.structured_logging import setup_structured_logging, JSONFormatter
        setup_structured_logging(level="INFO")
        root = logging.getLogger()
        json_handlers = [
            h for h in root.handlers
            if isinstance(h.formatter, JSONFormatter)
        ]
        assert len(json_handlers) >= 1
        for h in json_handlers:
            root.removeHandler(h)
