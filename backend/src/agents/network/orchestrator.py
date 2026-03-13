"""NetworkAgentOrchestrator — AI logic layer for the network chat agent.

Ties together the chat store, tool guard, tool registry, tool executor,
and Anthropic LLM client into a single tool-calling loop that powers
the per-view network chat overlay.
"""

from __future__ import annotations

from typing import Optional

from src.agents.network.prompts import build_system_prompt
from src.agents.network.tool_registry import NetworkToolRegistry
from src.agents.network.tool_guard import ToolGuard, ToolGuardError
from src.agents.network.tool_executor import NetworkToolExecutor
from src.database.network_chat_store import NetworkChatStore
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────

MAX_TOOL_ROUNDS: int = 5
MAX_TOOL_ROUNDS_INVESTIGATION: int = 10
CHAT_HISTORY_CAP: int = 20

# Views that enable investigation mode (all tools, higher round cap)
_INVESTIGATION_VIEWS: frozenset[str] = frozenset({"investigation"})


class NetworkAgentOrchestrator:
    """Orchestrates LLM conversations with tool calling for network views.

    Parameters
    ----------
    db_path:
        Path to the SQLite database for thread/message persistence.
    """

    def __init__(self, db_path: str = "data/debugduck.db") -> None:
        self._store = NetworkChatStore(db_path=db_path)
        self._guard = ToolGuard()
        self._tool_executor = NetworkToolExecutor()
        self._llm = AnthropicClient(agent_name="network_chat")

    # ── Main entry point ─────────────────────────────────────────

    async def handle_message(
        self,
        user_id: str,
        view: str,
        message: str,
        visible_data_summary: dict,
        thread_id: Optional[str] = None,
    ) -> dict:
        """Process a user message and return the assistant's response.

        Flow:
        1. Resolve or create thread
        2. Persist user message
        3. Build system prompt from view + visible data
        4. Load tools (all for investigation, view-specific otherwise)
        5. Load chat history
        6. Run tool-calling loop (max rounds)
        7. Persist and return assistant response

        Returns
        -------
        dict
            ``{"response": str, "thread_id": str, "tool_calls": list[dict]}``
        """
        is_investigation = view in _INVESTIGATION_VIEWS
        max_rounds = (
            MAX_TOOL_ROUNDS_INVESTIGATION if is_investigation else MAX_TOOL_ROUNDS
        )

        # 1. Resolve thread
        thread = self._resolve_thread(user_id, view, thread_id)
        tid = thread["thread_id"]

        # 2. Persist user message
        self._store.add_message(thread_id=tid, role="user", content=message)

        # 3. Build system prompt
        system_prompt = build_system_prompt(view, visible_data_summary)

        # 4. Load tools
        if is_investigation:
            tools = NetworkToolRegistry.get_all_tools()
        else:
            tools = NetworkToolRegistry.get_tools_for_view(view)

        # 5. Load chat history and build LLM messages
        history = self._store.list_messages(tid, limit=CHAT_HISTORY_CAP)
        llm_messages = self._build_llm_messages(history)

        # 6. Tool-calling loop
        tool_calls_log: list[dict] = []
        response_text: str = ""

        for _round in range(max_rounds):
            response = await self._llm.chat_with_tools(
                system=system_prompt,
                messages=llm_messages,
                tools=tools,
            )

            # Check for tool_use blocks
            tool_use_blocks = [
                block for block in response.content if block.type == "tool_use"
            ]

            if not tool_use_blocks:
                # No tool calls — extract text and break
                response_text = self._extract_text(response)
                break

            # Process each tool call
            tool_results: list[dict] = []
            # Also collect any text blocks from this response
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append(
                        {"type": "text", "text": block.text}
                    )
                elif block.type == "tool_use":
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

            # Append assistant message with tool_use blocks
            llm_messages.append({"role": "assistant", "content": assistant_content})

            for block in tool_use_blocks:
                tool_name = block.name
                tool_args = block.input
                tool_id = block.id

                try:
                    # Validate and rate-limit
                    self._guard.validate(
                        tool_name, tool_args, view, is_investigation=is_investigation
                    )
                    self._guard.check_rate_limit(tid)

                    # Execute
                    result_json = await self._tool_executor.execute(
                        tool_name, tool_args
                    )

                    # Truncate
                    result_json = self._guard.truncate_result(result_json)

                except ToolGuardError as e:
                    result_json = f'{{"error": "Guard rejected: {str(e)}"}}'
                    logger.warning(
                        "Tool guard rejected: %s — %s", tool_name, e
                    )

                # Log the tool call
                tool_calls_log.append(
                    {"name": tool_name, "args": tool_args, "result": result_json}
                )

                # Persist tool message
                self._store.add_message(
                    thread_id=tid,
                    role="tool",
                    content=result_json,
                    tool_name=tool_name,
                    tool_args=tool_args,
                )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_json,
                    }
                )

            # Append tool results to messages for next LLM call
            llm_messages.append({"role": "user", "content": tool_results})

        else:
            # Exhausted all rounds — extract whatever text we got last
            response_text = self._extract_text(response)
            if not response_text:
                response_text = (
                    "I've reached the maximum number of tool calls for this "
                    "request. Here's what I found so far based on the tools "
                    "I was able to run."
                )

        # 7. Persist assistant response
        self._store.add_message(thread_id=tid, role="assistant", content=response_text)

        return {
            "response": response_text,
            "thread_id": tid,
            "tool_calls": tool_calls_log,
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _resolve_thread(
        self, user_id: str, view: str, thread_id: Optional[str]
    ) -> dict:
        """Get an existing thread or create a new one.

        If *thread_id* is provided and valid, returns that thread.
        Otherwise creates a new thread for the user+view pair.
        """
        if thread_id:
            thread = self._store.get_thread(thread_id)
            if thread is not None:
                return thread

        # Try to find an existing active thread for this user+view
        thread = self._store.get_active_thread(user_id, view)
        if thread is not None:
            return thread

        # Create a new thread
        return self._store.create_thread(user_id, view)

    @staticmethod
    def _build_llm_messages(history: list[dict]) -> list[dict]:
        """Convert stored message history to LLM-compatible message format.

        Filters to only user and assistant messages (tool messages are
        internal and were already processed in their respective rounds).
        """
        messages: list[dict] = []
        for msg in history:
            role = msg.get("role")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg["content"]})
        return messages

    @staticmethod
    def _extract_text(response) -> str:
        """Extract concatenated text from an LLM response's content blocks."""
        parts: list[str] = []
        for block in response.content:
            if block.type == "text" and block.text:
                parts.append(block.text)
        return "\n".join(parts) if parts else ""
