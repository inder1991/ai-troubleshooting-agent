"""Tests for InvestigationRouter — Fast Path + Smart Path routing.

Covers:
- Fast path: quick_action buttons bypass LLM, go straight to ToolExecutor
- Fast path: slash commands (/logs, /promql, etc.) parsed via regex
- Smart path: natural language routed through LLM for intent classification
- Context defaults: missing params filled from RouterContext
- Error handling: unknown commands, missing LLM, bad JSON
- Pydantic validation: exactly-one-input enforcement
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tools.investigation_router import InvestigationRouter
from src.tools.router_models import (
    InvestigateRequest, QuickActionPayload, RouterContext, InvestigateResponse,
)
from src.tools.tool_result import ToolResult
from src.tools.tool_registry import TOOL_REGISTRY, SLASH_COMMAND_MAP
from src.models.schemas import TimeWindow, EvidencePin


def _make_context(**overrides):
    defaults = dict(
        active_namespace="payment-api",
        active_service="auth-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        session_id="test-session",
        incident_id="INC-TEST",
    )
    defaults.update(overrides)
    return RouterContext(**defaults)


def _make_tool_result(**overrides):
    defaults = dict(
        success=True, intent="fetch_pod_logs", raw_output="log text",
        summary="Pod auth: 1 error", evidence_snippets=["ERROR"],
        evidence_type="log", domain="compute", severity="medium",
        error=None, metadata={"pod": "auth-5b6q"},
    )
    defaults.update(overrides)
    return ToolResult(**defaults)


# ── Tool Registry Tests ──────────────────────────────────────────────


class TestToolRegistry:
    def test_registry_has_seven_tools(self):
        assert len(TOOL_REGISTRY) == 7

    def test_all_tools_have_required_fields(self):
        required_keys = {"intent", "label", "icon", "slash_command", "category", "description", "params_schema", "requires_context"}
        for tool in TOOL_REGISTRY:
            missing = required_keys - set(tool.keys())
            assert not missing, f"Tool '{tool.get('intent', '?')}' missing keys: {missing}"

    def test_slash_command_map_matches_registry(self):
        for tool in TOOL_REGISTRY:
            assert tool["slash_command"] in SLASH_COMMAND_MAP
            assert SLASH_COMMAND_MAP[tool["slash_command"]] == tool["intent"]

    def test_all_slash_commands_start_with_slash(self):
        for tool in TOOL_REGISTRY:
            assert tool["slash_command"].startswith("/"), f"Slash command for {tool['intent']} must start with /"

    def test_intents_are_unique(self):
        intents = [t["intent"] for t in TOOL_REGISTRY]
        assert len(intents) == len(set(intents)), "Duplicate intents in TOOL_REGISTRY"

    def test_slash_commands_are_unique(self):
        cmds = [t["slash_command"] for t in TOOL_REGISTRY]
        assert len(cmds) == len(set(cmds)), "Duplicate slash commands in TOOL_REGISTRY"


# ── Fast Path: Quick Action Button ────────────────────────────────────


class TestFastPathQuickAction:
    @pytest.mark.asyncio
    async def test_quick_action_bypasses_llm(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result())

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        request = InvestigateRequest(
            quick_action=QuickActionPayload(intent="fetch_pod_logs", params={"pod": "auth-5b6q", "namespace": "payment-api"}),
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.path_used == "fast"
        assert response.intent == "fetch_pod_logs"
        assert response.status == "executing"
        assert isinstance(pin, EvidencePin)
        assert pin.source == "manual"
        assert pin.triggered_by == "quick_action"

    @pytest.mark.asyncio
    async def test_quick_action_applies_context_defaults(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result())

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        # No namespace in params — should be filled from context
        request = InvestigateRequest(
            quick_action=QuickActionPayload(intent="fetch_pod_logs", params={"pod": "auth-5b6q"}),
            context=_make_context(active_namespace="payment-api"),
        )
        response, pin = await router.route(request)

        call_params = mock_executor.execute.call_args[0][1]
        assert call_params["namespace"] == "payment-api"

    @pytest.mark.asyncio
    async def test_quick_action_unknown_tool_returns_error(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(side_effect=KeyError("nonexistent"))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        request = InvestigateRequest(
            quick_action=QuickActionPayload(intent="nonexistent", params={}),
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.status == "error"
        assert "Unknown tool" in response.error
        assert pin is None


# ── Fast Path: Slash Command ──────────────────────────────────────────


class TestFastPathSlashCommand:
    @pytest.mark.asyncio
    async def test_slash_logs_parsed(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result())

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        request = InvestigateRequest(
            command="/logs namespace=payment-api pod=auth-5b6q",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.path_used == "fast"
        assert response.intent == "fetch_pod_logs"
        assert response.status == "executing"
        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args
        assert call_args[0][0] == "fetch_pod_logs"
        assert call_args[0][1]["pod"] == "auth-5b6q"

    @pytest.mark.asyncio
    async def test_slash_command_uses_context_defaults(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result())

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        # No namespace in command -- should use context
        request = InvestigateRequest(
            command="/logs pod=auth-5b6q",
            context=_make_context(active_namespace="payment-api"),
        )
        response, pin = await router.route(request)

        call_params = mock_executor.execute.call_args[0][1]
        assert call_params["namespace"] == "payment-api"

    @pytest.mark.asyncio
    async def test_slash_promql_parsed(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result(
            intent="query_prometheus", evidence_type="metric", domain="compute",
        ))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        request = InvestigateRequest(
            command="/promql query=rate(http_requests_total[5m])",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.path_used == "fast"
        assert response.intent == "query_prometheus"
        call_params = mock_executor.execute.call_args[0][1]
        assert call_params["query"] == "rate(http_requests_total[5m])"

    @pytest.mark.asyncio
    async def test_slash_command_boolean_param(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result())

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        request = InvestigateRequest(
            command="/logs pod=auth-5b6q previous=true tail_lines=50",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        call_params = mock_executor.execute.call_args[0][1]
        assert call_params["previous"] is True
        assert call_params["tail_lines"] == 50

    @pytest.mark.asyncio
    async def test_unknown_slash_command(self):
        router = InvestigationRouter(tool_executor=AsyncMock(), llm_client=None)

        request = InvestigateRequest(
            command="/nonexistent foo=bar",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.status == "error"
        assert "Unknown command" in response.error
        assert pin is None

    @pytest.mark.asyncio
    async def test_all_registered_slash_commands_resolve(self):
        """Every slash command in the registry should successfully parse."""
        for tool in TOOL_REGISTRY:
            parsed = InvestigationRouter._parse_slash_command(tool["slash_command"])
            assert parsed is not None, f"Slash command '{tool['slash_command']}' failed to parse"
            intent, params = parsed
            assert intent == tool["intent"]


# ── Smart Path: Natural Language -> Haiku LLM ─────────────────────────


class TestSmartPath:
    @pytest.mark.asyncio
    async def test_natural_language_uses_llm(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result())

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            text='{"intent": "fetch_pod_logs", "params": {"pod": "auth-5b6q", "namespace": "payment-api"}}'
        ))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=mock_llm)

        request = InvestigateRequest(
            query="check the auth pod logs",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.path_used == "smart"
        assert response.intent == "fetch_pod_logs"
        assert response.status == "executing"
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_smart_path_without_llm_returns_error(self):
        router = InvestigationRouter(tool_executor=AsyncMock(), llm_client=None)

        request = InvestigateRequest(
            query="check the auth pod logs",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.status == "error"
        assert "not configured" in response.error
        assert pin is None

    @pytest.mark.asyncio
    async def test_smart_path_bad_json_returns_error(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="not valid json"))

        router = InvestigationRouter(tool_executor=AsyncMock(), llm_client=mock_llm)

        request = InvestigateRequest(
            query="do something",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.status == "error"
        assert pin is None

    @pytest.mark.asyncio
    async def test_smart_path_missing_intent_key_returns_error(self):
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            text='{"tool": "fetch_pod_logs", "params": {}}'
        ))

        router = InvestigationRouter(tool_executor=AsyncMock(), llm_client=mock_llm)

        request = InvestigateRequest(
            query="check logs",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.status == "error"
        assert pin is None

    @pytest.mark.asyncio
    async def test_smart_path_applies_context_defaults(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=_make_tool_result())

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            text='{"intent": "fetch_pod_logs", "params": {"pod": "auth-5b6q"}}'
        ))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=mock_llm)

        request = InvestigateRequest(
            query="get logs from auth pod",
            context=_make_context(active_namespace="payment-api"),
        )
        response, pin = await router.route(request)

        call_params = mock_executor.execute.call_args[0][1]
        assert call_params["namespace"] == "payment-api"

    @pytest.mark.asyncio
    async def test_smart_path_builds_system_prompt_with_context(self):
        """The system prompt should include context and all tool descriptions."""
        context = _make_context(active_namespace="prod", active_service="checkout", pod_names=["pod-a", "pod-b"])
        prompt = InvestigationRouter._build_smart_prompt(context)

        assert "prod" in prompt
        assert "checkout" in prompt
        assert "pod-a" in prompt
        # All tools should be described
        for tool in TOOL_REGISTRY:
            assert tool["intent"] in prompt


# ── Context Defaults ──────────────────────────────────────────────────


class TestContextDefaults:
    def test_apply_defaults_fills_namespace(self):
        context = _make_context(active_namespace="my-ns")
        params = {"pod": "test-pod"}
        result = InvestigationRouter._apply_context_defaults("fetch_pod_logs", params, context)
        assert result["namespace"] == "my-ns"
        assert result["pod"] == "test-pod"

    def test_apply_defaults_does_not_overwrite_existing(self):
        context = _make_context(active_namespace="context-ns")
        params = {"pod": "test-pod", "namespace": "explicit-ns"}
        result = InvestigationRouter._apply_context_defaults("fetch_pod_logs", params, context)
        assert result["namespace"] == "explicit-ns"

    def test_apply_defaults_unknown_intent_returns_params_unchanged(self):
        context = _make_context()
        params = {"foo": "bar"}
        result = InvestigationRouter._apply_context_defaults("unknown_intent", params, context)
        assert result == {"foo": "bar"}

    def test_apply_defaults_fills_elk_index(self):
        context = _make_context(elk_index="app-logs-2026")
        params = {"query": "error"}
        result = InvestigationRouter._apply_context_defaults("search_logs", params, context)
        assert result["index"] == "app-logs-2026"


# ── Pydantic Validation ──────────────────────────────────────────────


class TestPydanticValidation:
    def test_exactly_one_input_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvestigateRequest(
                command="/logs pod=x",
                query="check logs",
                context=_make_context(),
            )

    def test_no_input_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvestigateRequest(context=_make_context())

    def test_command_only_accepted(self):
        req = InvestigateRequest(command="/logs pod=x", context=_make_context())
        assert req.command == "/logs pod=x"
        assert req.query is None
        assert req.quick_action is None

    def test_query_only_accepted(self):
        req = InvestigateRequest(query="check logs", context=_make_context())
        assert req.query == "check logs"
        assert req.command is None

    def test_quick_action_only_accepted(self):
        req = InvestigateRequest(
            quick_action=QuickActionPayload(intent="fetch_pod_logs", params={"pod": "x"}),
            context=_make_context(),
        )
        assert req.quick_action is not None
        assert req.command is None


# ── Slash Command Parsing ─────────────────────────────────────────────


class TestSlashCommandParsing:
    def test_parse_basic_slash_command(self):
        result = InvestigationRouter._parse_slash_command("/logs namespace=test pod=my-pod")
        assert result is not None
        intent, params = result
        assert intent == "fetch_pod_logs"
        assert params["namespace"] == "test"
        assert params["pod"] == "my-pod"

    def test_parse_slash_command_no_params(self):
        result = InvestigationRouter._parse_slash_command("/events")
        assert result is not None
        intent, params = result
        assert intent == "get_events"
        assert params == {}

    def test_parse_boolean_values(self):
        result = InvestigationRouter._parse_slash_command("/logs pod=test previous=true")
        assert result is not None
        _, params = result
        assert params["previous"] is True

    def test_parse_false_boolean(self):
        result = InvestigationRouter._parse_slash_command("/logs pod=test previous=false")
        assert result is not None
        _, params = result
        assert params["previous"] is False

    def test_parse_integer_values(self):
        result = InvestigationRouter._parse_slash_command("/logs pod=test tail_lines=100")
        assert result is not None
        _, params = result
        assert params["tail_lines"] == 100

    def test_parse_unknown_command_returns_none(self):
        result = InvestigationRouter._parse_slash_command("/unknown foo=bar")
        assert result is None

    def test_parse_empty_string_returns_none(self):
        result = InvestigationRouter._parse_slash_command("")
        assert result is None

    def test_parse_no_slash_returns_none(self):
        result = InvestigationRouter._parse_slash_command("logs pod=test")
        assert result is None
