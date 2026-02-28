"""Tests for evidence pin quality + bounds (B5, B6, B9, B10, B11, B13).

Covers:
- B9:  Parameter clamping (tail_lines <= 5000, range_minutes/since_minutes <= 1440)
- B10: raw_output truncation to 50,000 chars in EvidencePinFactory
- B11: Confidence capped at 0.5 when evidence_snippets is empty
- B13: Warning event count aggregation with None-safe fallback
- B5:  Duplicate pin dedup (same source_tool + claim within 60s)
- B6:  causal_role validation against allowed set
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src.tools.tool_result import ToolResult
from src.tools.tool_executor import ToolExecutor
from src.tools.evidence_pin_factory import EvidencePinFactory
from src.tools.router_models import RouterContext
from src.models.schemas import EvidencePin, TimeWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executor(**overrides) -> ToolExecutor:
    """Create a ToolExecutor with a dummy config and mocked K8s clients."""
    config = overrides.pop("config", {"kubeconfig": "/fake/path"})
    executor = ToolExecutor(connection_config=config)
    executor._k8s_core_api = overrides.get("core_api", MagicMock())
    executor._k8s_apps_api = overrides.get("apps_api", MagicMock())
    return executor


def _make_tool_result(**overrides) -> ToolResult:
    """Create a ToolResult with sensible defaults."""
    defaults = dict(
        success=True,
        intent="fetch_pod_logs",
        raw_output="some log output",
        summary="Found 3 errors in pod logs",
        evidence_snippets=["ERROR connection refused"],
        evidence_type="log",
        domain="compute",
        severity="medium",
        metadata={"pod": "test-pod", "namespace": "default"},
    )
    defaults.update(overrides)
    return ToolResult(**defaults)


def _make_router_context(**overrides) -> RouterContext:
    """Create a RouterContext with sensible defaults."""
    defaults = dict(
        active_namespace="default",
        active_service="test-svc",
        time_window=TimeWindow(start="2026-02-28T10:00:00Z", end="2026-02-28T11:00:00Z"),
        session_id="test-session",
    )
    defaults.update(overrides)
    return RouterContext(**defaults)


# ---------------------------------------------------------------------------
# B9: Parameter clamping
# ---------------------------------------------------------------------------

class TestParameterClamping:
    """B9: Verify tail_lines, range_minutes, since_minutes are clamped."""

    @pytest.mark.asyncio
    async def test_tail_lines_clamped_to_5000(self):
        """tail_lines exceeding 5000 should be clamped to 5000."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(return_value="log line\n")
        executor = _make_executor(core_api=mock_api)

        await executor._fetch_pod_logs({
            "namespace": "default",
            "pod": "test-pod",
            "tail_lines": 99999,
        })

        # Verify the actual K8s call used clamped value
        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs[1]["tail_lines"] == 5000 or call_kwargs.kwargs.get("tail_lines") == 5000

    @pytest.mark.asyncio
    async def test_tail_lines_below_max_unchanged(self):
        """tail_lines within limit should not be modified."""
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log = MagicMock(return_value="log line\n")
        executor = _make_executor(core_api=mock_api)

        await executor._fetch_pod_logs({
            "namespace": "default",
            "pod": "test-pod",
            "tail_lines": 500,
        })

        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs[1]["tail_lines"] == 500 or call_kwargs.kwargs.get("tail_lines") == 500

    @pytest.mark.asyncio
    async def test_range_minutes_clamped_to_1440(self):
        """range_minutes exceeding 1440 should be clamped for Prometheus queries."""
        mock_prom = MagicMock()
        mock_prom.query_range = MagicMock(return_value={"data": {"result": []}})
        executor = _make_executor()
        executor._prom_client = mock_prom

        result = await executor._query_prometheus({
            "query": "up{job='test'}",
            "range_minutes": 10000,
        })

        # Verify the call used clamped value
        call_args = mock_prom.query_range.call_args
        assert call_args[0][1] == 1440 or call_args.kwargs.get("range_minutes") == 1440

    @pytest.mark.asyncio
    async def test_search_logs_since_minutes_clamped_to_1440(self):
        """since_minutes exceeding 1440 should be clamped for ES log search."""
        mock_es = MagicMock()
        mock_es.search = MagicMock(return_value={
            "hits": {"total": {"value": 0}, "hits": []}
        })
        executor = _make_executor()
        executor._es_client = mock_es

        result = await executor._search_logs({
            "query": "error",
            "since_minutes": 5000,
        })

        # Verify the ES query body uses clamped value (1440)
        call_kwargs = mock_es.search.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body")
        range_filter = body["query"]["bool"]["filter"][0]["range"]["@timestamp"]
        assert range_filter["gte"] == "now-1440m"

    @pytest.mark.asyncio
    async def test_get_events_since_minutes_clamped_to_1440(self):
        """since_minutes exceeding 1440 should be clamped for K8s events."""
        mock_api = MagicMock()
        # Return an empty event list
        event_list = MagicMock()
        event_list.items = []
        mock_api.list_namespaced_event = MagicMock(return_value=event_list)
        executor = _make_executor(core_api=mock_api)

        result = await executor._get_events({
            "namespace": "default",
            "since_minutes": 9999,
        })

        # Should succeed - the clamped value is used internally for time filtering
        assert result.success is True
        assert "1440" in result.summary


# ---------------------------------------------------------------------------
# B10: raw_output truncation
# ---------------------------------------------------------------------------

class TestRawOutputTruncation:
    """B10: EvidencePinFactory should truncate raw_output to 50,000 chars."""

    def test_raw_output_truncated_to_50k(self):
        """raw_output exceeding 50,000 chars should be truncated."""
        long_output = "x" * 100_000
        result = _make_tool_result(raw_output=long_output)
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", context)

        assert len(pin.raw_output) == 50_000

    def test_raw_output_within_limit_unchanged(self):
        """raw_output within 50,000 chars should not be modified."""
        short_output = "y" * 10_000
        result = _make_tool_result(raw_output=short_output)
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", context)

        assert pin.raw_output == short_output
        assert len(pin.raw_output) == 10_000


# ---------------------------------------------------------------------------
# B11: Confidence cap when no evidence
# ---------------------------------------------------------------------------

class TestConfidenceCap:
    """B11: Confidence should be 0.5 when evidence_snippets is empty, not 1.0."""

    def test_confidence_05_when_no_evidence(self):
        """A successful result with no evidence snippets should get confidence 0.5."""
        result = _make_tool_result(evidence_snippets=[], success=True)
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", context)

        assert pin.confidence == 0.5

    def test_confidence_10_when_has_evidence(self):
        """A successful result with evidence snippets should get confidence 1.0."""
        result = _make_tool_result(
            evidence_snippets=["ERROR something went wrong"],
            success=True,
        )
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", context)

        assert pin.confidence == 1.0

    def test_confidence_0_when_failed(self):
        """A failed result should get confidence 0.0 regardless of evidence."""
        result = _make_tool_result(success=False, evidence_snippets=["some data"])
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", context)

        assert pin.confidence == 0.0


# ---------------------------------------------------------------------------
# B13: Warning event count aggregation (None-safe)
# ---------------------------------------------------------------------------

class TestWarningEventCount:
    """B13: Event count aggregation should handle None counts gracefully."""

    @pytest.mark.asyncio
    async def test_warning_count_with_none_event_counts(self):
        """Events with count=None should be treated as count=1."""
        mock_api = MagicMock()

        # Create mock events: two warnings (one with count=None, one with count=3)
        # and one normal event
        now = datetime.now(timezone.utc)
        events = []
        for type_, count in [("Warning", None), ("Warning", 3), ("Normal", 1)]:
            event = MagicMock()
            event.type = type_
            event.count = count
            event.last_timestamp = now
            event.reason = "TestReason"
            event.message = "Test message"
            event.involved_object = MagicMock()
            event.involved_object.name = "test-pod"
            event.involved_object.kind = "Pod"
            events.append(event)

        event_list = MagicMock()
        event_list.items = events
        mock_api.list_namespaced_event = MagicMock(return_value=event_list)
        executor = _make_executor(core_api=mock_api)

        result = await executor._get_events({
            "namespace": "default",
            "since_minutes": 60,
        })

        assert result.success is True
        # Warning count should be 1 (None->1) + 3 = 4
        assert result.metadata["warning_count"] == 4

    @pytest.mark.asyncio
    async def test_warning_count_with_zero_event_counts(self):
        """Events with count=0 should be treated as count=1 (0 is falsy)."""
        mock_api = MagicMock()
        now = datetime.now(timezone.utc)

        event = MagicMock()
        event.type = "Warning"
        event.count = 0
        event.last_timestamp = now
        event.reason = "TestReason"
        event.message = "Test message"
        event.involved_object = MagicMock()
        event.involved_object.name = "test-pod"
        event.involved_object.kind = "Pod"

        event_list = MagicMock()
        event_list.items = [event]
        mock_api.list_namespaced_event = MagicMock(return_value=event_list)
        executor = _make_executor(core_api=mock_api)

        result = await executor._get_events({
            "namespace": "default",
            "since_minutes": 60,
        })

        # count=0 is falsy, should fallback to 1
        assert result.metadata["warning_count"] == 1


# ---------------------------------------------------------------------------
# B5: Duplicate pin dedup
# ---------------------------------------------------------------------------

class TestPinDedup:
    """B5: Duplicate pins (same source_tool + claim within 60s) should be skipped."""

    def test_is_duplicate_pin_within_window(self):
        """A pin with same source_tool + claim within 60s should be detected as duplicate."""
        from src.api.routes_v4 import _is_duplicate_pin

        now = datetime.now(timezone.utc)
        existing_pins = [{
            "source_tool": "fetch_pod_logs",
            "claim": "Found 3 errors in pod logs",
            "timestamp": now.isoformat(),
        }]

        new_pin = MagicMock()
        new_pin.source_tool = "fetch_pod_logs"
        new_pin.claim = "Found 3 errors in pod logs"
        new_pin.timestamp = now + timedelta(seconds=30)

        assert _is_duplicate_pin(existing_pins, new_pin) is True

    def test_is_not_duplicate_outside_window(self):
        """A pin with same source_tool + claim outside 60s window should not be duplicate."""
        from src.api.routes_v4 import _is_duplicate_pin

        now = datetime.now(timezone.utc)
        existing_pins = [{
            "source_tool": "fetch_pod_logs",
            "claim": "Found 3 errors in pod logs",
            "timestamp": (now - timedelta(seconds=120)).isoformat(),
        }]

        new_pin = MagicMock()
        new_pin.source_tool = "fetch_pod_logs"
        new_pin.claim = "Found 3 errors in pod logs"
        new_pin.timestamp = now

        assert _is_duplicate_pin(existing_pins, new_pin) is False

    def test_is_not_duplicate_different_claim(self):
        """A pin with different claim should not be duplicate."""
        from src.api.routes_v4 import _is_duplicate_pin

        now = datetime.now(timezone.utc)
        existing_pins = [{
            "source_tool": "fetch_pod_logs",
            "claim": "Found 3 errors in pod logs",
            "timestamp": now.isoformat(),
        }]

        new_pin = MagicMock()
        new_pin.source_tool = "fetch_pod_logs"
        new_pin.claim = "Found 5 errors in pod logs"
        new_pin.timestamp = now + timedelta(seconds=5)

        assert _is_duplicate_pin(existing_pins, new_pin) is False

    def test_is_not_duplicate_different_tool(self):
        """A pin with different source_tool should not be duplicate."""
        from src.api.routes_v4 import _is_duplicate_pin

        now = datetime.now(timezone.utc)
        existing_pins = [{
            "source_tool": "fetch_pod_logs",
            "claim": "Found 3 errors in pod logs",
            "timestamp": now.isoformat(),
        }]

        new_pin = MagicMock()
        new_pin.source_tool = "search_logs"
        new_pin.claim = "Found 3 errors in pod logs"
        new_pin.timestamp = now + timedelta(seconds=5)

        assert _is_duplicate_pin(existing_pins, new_pin) is False


# ---------------------------------------------------------------------------
# B6: causal_role validation
# ---------------------------------------------------------------------------

class TestCausalRoleValidation:
    """B6: causal_role should be validated against allowed set."""

    def test_valid_causal_roles_accepted(self):
        """Valid causal_role values should be accepted as-is."""
        from src.api.routes_v4 import _validate_causal_role, _VALID_CAUSAL_ROLES

        for role in _VALID_CAUSAL_ROLES:
            pin = MagicMock()
            pin.causal_role = role
            _validate_causal_role(pin)
            assert pin.causal_role == role

    def test_invalid_causal_role_falls_back(self):
        """Invalid causal_role values should be replaced with 'informational'."""
        from src.api.routes_v4 import _validate_causal_role

        pin = MagicMock()
        pin.causal_role = "definitely_not_valid"
        _validate_causal_role(pin)
        assert pin.causal_role == "informational"

    def test_none_causal_role_left_alone(self):
        """None causal_role should remain None (not yet assigned by critic)."""
        from src.api.routes_v4 import _validate_causal_role

        pin = MagicMock()
        pin.causal_role = None
        _validate_causal_role(pin)
        assert pin.causal_role is None
