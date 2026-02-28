"""Tests for ToolExecutor parameter validation and the re_investigate_service stub.

Covers:
- Missing required params return ToolResult(success=False) with descriptive error
- The re_investigate_service stub is dispatched and returns 'not yet implemented'
- Optional params are not flagged as missing
- Unknown intents still raise KeyError (validation is skipped for unregistered intents)
"""

import pytest
from unittest.mock import MagicMock

from src.tools.tool_result import ToolResult
from src.tools.tool_executor import ToolExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executor() -> ToolExecutor:
    """Create a ToolExecutor with dummy config and mocked K8s clients."""
    executor = ToolExecutor(connection_config={"kubeconfig": "/fake/path"})
    executor._k8s_core_api = MagicMock()
    executor._k8s_apps_api = MagicMock()
    return executor


# ---------------------------------------------------------------------------
# Parameter Validation Tests
# ---------------------------------------------------------------------------


class TestParameterValidation:
    """Tests for _validate_params and its integration in execute()."""

    @pytest.mark.asyncio
    async def test_missing_namespace_returns_error(self):
        """fetch_pod_logs requires 'namespace'; omitting it should fail validation."""
        executor = _make_executor()
        result = await executor.execute("fetch_pod_logs", {"pod": "my-pod"})

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "namespace" in result.error
        assert result.intent == "fetch_pod_logs"

    @pytest.mark.asyncio
    async def test_missing_pod_returns_error(self):
        """fetch_pod_logs requires 'pod'; omitting it should fail validation."""
        executor = _make_executor()
        result = await executor.execute("fetch_pod_logs", {"namespace": "prod"})

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "pod" in result.error
        assert result.intent == "fetch_pod_logs"

    @pytest.mark.asyncio
    async def test_missing_query_for_promql(self):
        """query_prometheus requires 'query'; omitting it should fail validation."""
        executor = _make_executor()
        result = await executor.execute("query_prometheus", {})

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "query" in result.error
        assert result.intent == "query_prometheus"

    @pytest.mark.asyncio
    async def test_optional_param_not_required(self):
        """Optional params (like 'container' on fetch_pod_logs) should not
        cause a validation failure when omitted."""
        executor = _make_executor()
        # Provide the two required params, omit optional 'container', 'previous', 'tail_lines'
        mock_api = executor._k8s_core_api
        mock_api.read_namespaced_pod_log = MagicMock(return_value="INFO all good\n")

        result = await executor.execute("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "my-pod",
        })

        # Should pass validation and succeed
        assert result.success is True

    @pytest.mark.asyncio
    async def test_multiple_missing_params_listed(self):
        """When multiple required params are missing, all should be named in the error."""
        executor = _make_executor()
        result = await executor.execute("fetch_pod_logs", {})

        assert result.success is False
        assert "namespace" in result.error
        assert "pod" in result.error

    def test_validate_params_returns_none_for_valid(self):
        """_validate_params should return None when all required params present."""
        error = ToolExecutor._validate_params("fetch_pod_logs", {
            "namespace": "prod",
            "pod": "my-pod",
        })
        assert error is None

    def test_validate_params_returns_none_for_unknown_intent(self):
        """_validate_params should return None for intents not in TOOL_REGISTRY
        (validation is skipped; KeyError happens later in dispatch)."""
        error = ToolExecutor._validate_params("totally_unknown", {"a": 1})
        assert error is None

    def test_validate_params_catches_none_value(self):
        """A param present but set to None should still be flagged as missing."""
        error = ToolExecutor._validate_params("fetch_pod_logs", {
            "namespace": "prod",
            "pod": None,
        })
        assert error is not None
        assert "pod" in error


# ---------------------------------------------------------------------------
# re_investigate_service Stub Tests
# ---------------------------------------------------------------------------


class TestReInvestigateServiceStub:
    """Tests for the re_investigate_service handler stub."""

    @pytest.mark.asyncio
    async def test_re_investigate_returns_stub(self):
        """re_investigate_service should be dispatched and return a stub error."""
        executor = _make_executor()
        result = await executor.execute("re_investigate_service", {
            "service": "payment-svc",
            "namespace": "prod",
        })

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.error == "not yet implemented"
        assert result.intent == "re_investigate_service"
        assert result.metadata.get("service") == "payment-svc"
        assert result.metadata.get("namespace") == "prod"

    @pytest.mark.asyncio
    async def test_re_investigate_missing_params(self):
        """re_investigate_service requires 'service' and 'namespace';
        omitting them should fail validation before reaching the stub."""
        executor = _make_executor()
        result = await executor.execute("re_investigate_service", {})

        assert result.success is False
        assert "service" in result.error
        assert "namespace" in result.error

    def test_re_investigate_in_handlers_dict(self):
        """re_investigate_service should be present in HANDLERS."""
        assert "re_investigate_service" in ToolExecutor.HANDLERS
        assert ToolExecutor.HANDLERS["re_investigate_service"] == "_re_investigate_service"


# ---------------------------------------------------------------------------
# Unknown Intent Tests
# ---------------------------------------------------------------------------


class TestUnknownIntent:
    """Tests for unknown/invalid intent names after validation."""

    @pytest.mark.asyncio
    async def test_unknown_intent_raises_key_error(self):
        """An intent not in HANDLERS (and not in TOOL_REGISTRY) should raise KeyError.

        Validation passes (returns None for unknown intents), but dispatch
        raises KeyError when looking up the handler name.
        """
        executor = _make_executor()
        with pytest.raises(KeyError):
            await executor.execute("nonexistent_tool", {"foo": "bar"})
