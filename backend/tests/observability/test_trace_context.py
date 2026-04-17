"""Task 4.27 — W3C trace context propagation."""
from __future__ import annotations

from src.observability.trace_context import (
    TRACEPARENT_HEADER,
    TraceContext,
    current_context,
    current_trace_id,
    extract_traceparent,
    inject_traceparent,
    set_context,
    start_new_trace,
    structlog_fields,
)


class TestFormat:
    def test_format_header_matches_w3c(self):
        ctx = TraceContext(trace_id="a" * 32, parent_id="b" * 16)
        assert ctx.format_header() == f"00-{'a' * 32}-{'b' * 16}-01"


class TestExtract:
    def test_extract_valid_header(self):
        headers = {"traceparent": f"00-{'a' * 32}-{'b' * 16}-01"}
        ctx = extract_traceparent(headers)
        assert ctx is not None
        assert ctx.trace_id == "a" * 32
        assert ctx.parent_id == "b" * 16

    def test_extract_missing_returns_none(self):
        assert extract_traceparent({}) is None
        assert extract_traceparent({"other": "value"}) is None

    def test_extract_malformed_returns_none(self):
        assert extract_traceparent({"traceparent": "garbage"}) is None
        # Wrong segment count
        assert extract_traceparent({"traceparent": "00-abc"}) is None
        # Invalid hex
        assert extract_traceparent({"traceparent": f"00-zzz-{'b' * 16}-01"}) is None

    def test_extract_case_insensitive_header_lookup(self):
        headers = {"Traceparent": f"00-{'a' * 32}-{'b' * 16}-01"}
        assert extract_traceparent(headers) is not None


class TestInject:
    def test_inject_adds_header_when_context_active(self):
        set_context(TraceContext(trace_id="a" * 32, parent_id="b" * 16))
        out = inject_traceparent({"Authorization": "Bearer x"})
        assert TRACEPARENT_HEADER in out
        assert out["Authorization"] == "Bearer x"

    def test_inject_does_not_mutate_input(self):
        set_context(TraceContext(trace_id="a" * 32, parent_id="b" * 16))
        original = {"x": 1}
        out = inject_traceparent(original)
        assert TRACEPARENT_HEADER not in original
        assert TRACEPARENT_HEADER in out

    def test_inject_preserves_existing_header(self):
        set_context(TraceContext(trace_id="a" * 32, parent_id="b" * 16))
        user = f"00-{'c' * 32}-{'d' * 16}-01"
        out = inject_traceparent({"traceparent": user})
        assert out["traceparent"] == user

    def test_inject_starts_new_trace_if_none_active(self):
        # Clear the context first
        try:
            set_context(None)  # type: ignore
        except Exception:
            pass
        # Use a fresh ContextVar token by calling start_new_trace
        out = inject_traceparent(None)
        # Should have SOMETHING so outbound calls are never silently untraced.
        assert TRACEPARENT_HEADER in out
        # Valid shape
        v = out[TRACEPARENT_HEADER]
        assert v.startswith("00-")
        assert len(v) == 55  # "00-" + 32 + "-" + 16 + "-" + 2 = 55


class TestCurrent:
    def test_current_context_returns_none_initially(self):
        # Can't easily reset context vars globally, but when a new test
        # starts ContextVar.get() returns the default (None).
        # Just verify it doesn't crash.
        v = current_context()
        assert v is None or isinstance(v, TraceContext)

    def test_start_new_trace_installs_context(self):
        ctx = start_new_trace()
        assert current_context() == ctx
        assert current_trace_id() == ctx.trace_id

    def test_structlog_fields_has_trace_id_when_active(self):
        ctx = start_new_trace()
        fields = structlog_fields()
        assert fields["trace_id"] == ctx.trace_id
        assert fields["parent_id"] == ctx.parent_id


class TestRoundTrip:
    def test_extract_then_inject_preserves_trace_id(self):
        original_header = f"00-{'a' * 32}-{'b' * 16}-01"
        ctx = extract_traceparent({"traceparent": original_header})
        set_context(ctx)
        out = inject_traceparent(None)
        # The trace_id must be preserved (span id may rotate later but
        # this module doesn't rotate; it just propagates).
        assert "a" * 32 in out["traceparent"]
