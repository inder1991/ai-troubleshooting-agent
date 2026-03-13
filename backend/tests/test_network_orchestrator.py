# backend/tests/test_network_orchestrator.py
"""Tests for NetworkAgentOrchestrator — the AI logic layer."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.network.orchestrator import NetworkAgentOrchestrator


def _make_tool_use_block(name: str, input: dict, id: str):
    """Create a tool_use content block that behaves like the Anthropic SDK."""
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id)


def _make_text_block(text: str):
    """Create a text content block that behaves like the Anthropic SDK."""
    return SimpleNamespace(type="text", text=text)


@pytest.fixture
def orchestrator(tmp_path):
    db_path = str(tmp_path / "test.db")
    return NetworkAgentOrchestrator(db_path=db_path)


class TestBuildSystemPrompt:
    """Verify that prompts.build_system_prompt is wired correctly."""

    def test_prompt_contains_base_role(self):
        from src.agents.network.prompts import build_system_prompt

        prompt = build_system_prompt("observatory", {})
        assert "senior network engineer" in prompt

    def test_prompt_contains_view_context(self):
        from src.agents.network.prompts import build_system_prompt

        prompt = build_system_prompt("ipam", {})
        assert "IPAM" in prompt
        assert "IP Address Management" in prompt

    def test_prompt_includes_visible_data(self):
        from src.agents.network.prompts import build_system_prompt

        prompt = build_system_prompt("observatory", {"alerts": 3, "top_talker": "10.0.0.1"})
        assert "CURRENTLY VISIBLE DATA" in prompt
        assert "10.0.0.1" in prompt

    def test_prompt_truncates_large_summary(self):
        from src.agents.network.prompts import build_system_prompt, MAX_SUMMARY_BYTES

        big_data = {"data": "x" * 5000}
        prompt = build_system_prompt("observatory", big_data)
        # The summary portion should be truncated
        assert "CURRENTLY VISIBLE DATA" in prompt

    def test_prompt_unknown_view_gets_fallback(self):
        from src.agents.network.prompts import build_system_prompt

        prompt = build_system_prompt("unknown-view-xyz", {})
        assert "unknown-view-xyz" in prompt
        assert "general network questions" in prompt

    def test_all_views_have_prompts(self):
        from src.agents.network.prompts import build_system_prompt

        views = [
            "observatory", "network-topology", "ipam", "device-monitoring",
            "network-adapters", "matrix", "mib-browser", "cloud-resources",
            "security-resources",
        ]
        for view in views:
            prompt = build_system_prompt(view, {})
            assert "VIEW CONTEXT" in prompt, f"Missing VIEW CONTEXT for {view}"
            assert "TOOL USAGE INSTRUCTIONS" in prompt


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_handle_message_creates_thread(self, orchestrator):
        """When no thread_id is given, orchestrator should create one."""
        mock_response = MagicMock()
        mock_response.content = [_make_text_block("Here's what I see.")]
        mock_response.stop_reason = "end_turn"

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, return_value=mock_response,
        ):
            result = await orchestrator.handle_message(
                user_id="user-1",
                view="observatory",
                message="What's happening?",
                visible_data_summary={"alerts": 3},
            )
            assert result["response"] == "Here's what I see."
            assert result["thread_id"] is not None
            assert isinstance(result["thread_id"], str)
            assert len(result["thread_id"]) > 0

    @pytest.mark.asyncio
    async def test_handle_message_reuses_thread(self, orchestrator):
        """When a thread_id is provided, orchestrator should reuse it."""
        mock_response = MagicMock()
        mock_response.content = [_make_text_block("ok")]
        mock_response.stop_reason = "end_turn"

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, return_value=mock_response,
        ):
            # First call creates a thread
            result1 = await orchestrator.handle_message(
                user_id="user-1", view="observatory",
                message="Hello", visible_data_summary={},
            )
            thread_id = result1["thread_id"]

            # Second call reuses the thread
            result2 = await orchestrator.handle_message(
                user_id="user-1", view="observatory",
                message="Follow up", visible_data_summary={},
                thread_id=thread_id,
            )
            assert result2["thread_id"] == thread_id

    @pytest.mark.asyncio
    async def test_loads_correct_tools_for_view(self, orchestrator):
        """IPAM view should include search_ip tool."""
        mock_response = MagicMock()
        mock_response.content = [_make_text_block("ok")]
        mock_response.stop_reason = "end_turn"

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, return_value=mock_response,
        ) as mock_llm:
            await orchestrator.handle_message(
                user_id="user-1", view="ipam",
                message="Any conflicts?", visible_data_summary={},
            )
            call_args = mock_llm.call_args
            tools = call_args.kwargs.get("tools") or call_args[1].get("tools", [])
            tool_names = {t["name"] for t in tools}
            assert "search_ip" in tool_names
            assert "summarize_context" in tool_names  # shared tools always included

    @pytest.mark.asyncio
    async def test_loads_all_tools_for_investigation(self, orchestrator):
        """Investigation view should load all tools."""
        mock_response = MagicMock()
        mock_response.content = [_make_text_block("ok")]
        mock_response.stop_reason = "end_turn"

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, return_value=mock_response,
        ) as mock_llm:
            await orchestrator.handle_message(
                user_id="user-1", view="investigation",
                message="Full analysis", visible_data_summary={},
            )
            call_args = mock_llm.call_args
            tools = call_args.kwargs.get("tools") or call_args[1].get("tools", [])
            tool_names = {t["name"] for t in tools}
            # Investigation should have tools from all groups
            assert "get_top_talkers" in tool_names
            assert "search_ip" in tool_names
            assert "get_topology_graph" in tool_names

    @pytest.mark.asyncio
    async def test_handles_tool_calls(self, orchestrator):
        """Orchestrator should execute tool calls and loop back to LLM."""
        tool_use_block = _make_tool_use_block("get_active_alerts", {}, "tool-1")
        text_block = _make_text_block("There are 3 active alerts.")

        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:
                resp.content = [tool_use_block]
                resp.stop_reason = "tool_use"
            else:
                resp.content = [text_block]
                resp.stop_reason = "end_turn"
            return resp

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, side_effect=side_effect,
        ):
            with patch.object(
                orchestrator._tool_executor, "execute",
                new_callable=AsyncMock, return_value='[{"id":"a1"}]',
            ):
                result = await orchestrator.handle_message(
                    user_id="user-1", view="observatory",
                    message="Any alerts?", visible_data_summary={},
                )
                assert result["response"] == "There are 3 active alerts."
                assert len(result.get("tool_calls", [])) == 1
                assert result["tool_calls"][0]["name"] == "get_active_alerts"

    @pytest.mark.asyncio
    async def test_tool_guard_rejection(self, orchestrator):
        """When ToolGuard rejects a call, the error is sent back to the LLM."""
        tool_use_block = _make_tool_use_block(
            "simulate_rule_change",
            {"device_id": "fw1", "action": "add", "rule": {}},
            "tool-2",
        )
        text_block = _make_text_block(
            "I cannot simulate rule changes outside investigation mode.",
        )

        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:
                resp.content = [tool_use_block]
                resp.stop_reason = "tool_use"
            else:
                resp.content = [text_block]
                resp.stop_reason = "end_turn"
            return resp

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, side_effect=side_effect,
        ):
            result = await orchestrator.handle_message(
                user_id="user-1", view="observatory",
                message="Simulate adding a rule", visible_data_summary={},
            )
            assert "cannot simulate" in result["response"].lower() or "investigation" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_max_tool_rounds_enforced(self, orchestrator):
        """The tool loop should stop after MAX_TOOL_ROUNDS iterations."""
        tool_use_block = _make_tool_use_block("get_active_alerts", {}, "tool-x")

        async def always_tool_use(**kwargs):
            resp = MagicMock()
            resp.content = [tool_use_block]
            resp.stop_reason = "tool_use"
            return resp

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, side_effect=always_tool_use,
        ):
            with patch.object(
                orchestrator._tool_executor, "execute",
                new_callable=AsyncMock, return_value='{"ok": true}',
            ):
                result = await orchestrator.handle_message(
                    user_id="user-1", view="observatory",
                    message="Keep going", visible_data_summary={},
                )
                # Should still return something, not loop forever
                assert result["response"] is not None
                assert result["thread_id"] is not None

    @pytest.mark.asyncio
    async def test_persists_messages_to_store(self, orchestrator):
        """User and assistant messages should be persisted in the chat store."""
        mock_response = MagicMock()
        mock_response.content = [_make_text_block("Noted.")]
        mock_response.stop_reason = "end_turn"

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, return_value=mock_response,
        ):
            result = await orchestrator.handle_message(
                user_id="user-1", view="observatory",
                message="Check alerts", visible_data_summary={},
            )
            thread_id = result["thread_id"]
            messages = orchestrator._store.list_messages(thread_id)
            # Should have user message + assistant message
            assert len(messages) >= 2
            roles = [m["role"] for m in messages]
            assert "user" in roles
            assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_empty_tool_calls_in_response(self, orchestrator):
        """When LLM returns no tool calls, tool_calls list should be empty."""
        mock_response = MagicMock()
        mock_response.content = [_make_text_block("All clear.")]
        mock_response.stop_reason = "end_turn"

        with patch.object(
            orchestrator._llm, "chat_with_tools",
            new_callable=AsyncMock, return_value=mock_response,
        ):
            result = await orchestrator.handle_message(
                user_id="user-1", view="observatory",
                message="Status?", visible_data_summary={},
            )
            assert result["tool_calls"] == []


class TestBuildLLMMessages:
    """Test the _build_llm_messages helper."""

    def test_converts_user_and_assistant_messages(self, orchestrator):
        history = [
            {"role": "user", "content": "hello", "tool_name": None, "tool_result": None},
            {"role": "assistant", "content": "hi there", "tool_name": None, "tool_result": None},
        ]
        msgs = orchestrator._build_llm_messages(history)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "hi there"

    def test_skips_tool_messages(self, orchestrator):
        history = [
            {"role": "user", "content": "check alerts", "tool_name": None, "tool_result": None},
            {"role": "tool", "content": "", "tool_name": "get_active_alerts", "tool_result": '{"alerts": []}'},
            {"role": "assistant", "content": "No alerts.", "tool_name": None, "tool_result": None},
        ]
        msgs = orchestrator._build_llm_messages(history)
        # Tool messages should be skipped — only user and assistant
        roles = [m["role"] for m in msgs]
        assert "tool" not in roles

    def test_empty_history(self, orchestrator):
        msgs = orchestrator._build_llm_messages([])
        assert msgs == []
