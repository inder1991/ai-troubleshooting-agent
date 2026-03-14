"""Assistant orchestrator — agentic loop for the DebugDuck AI Assistant."""
import asyncio
import json
import logging
from src.utils.llm_client import AnthropicClient
from .tools import (
    list_sessions, get_session_detail, search_sessions,
    start_investigation, cancel_investigation, get_fix_recommendations,
    ASSISTANT_TOOLS,
)
from .prompts import ASSISTANT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

ASSISTANT_MODEL = "claude-sonnet-4-20250514"
MAX_ITERATIONS = 5


async def run_assistant(
    user_message: str,
    sessions: dict,
    thread_history: list[dict],
    timeout: float = 30.0,
) -> dict:
    """Run the assistant agentic loop. Returns {response, actions, usage}."""
    llm = AnthropicClient(agent_name="assistant", model=ASSISTANT_MODEL)

    messages = list(thread_history)
    messages.append({"role": "user", "content": user_message})

    actions = []  # Frontend actions (navigate, download)

    try:
        for iteration in range(MAX_ITERATIONS):
            response = await asyncio.wait_for(
                llm.chat_with_tools(
                    system=ASSISTANT_SYSTEM_PROMPT,
                    messages=messages,
                    tools=ASSISTANT_TOOLS,
                    max_tokens=2048,
                    temperature=0.0,
                ),
                timeout=timeout,
            )

            assistant_content = list(response.content)
            tool_results = []

            for block in response.content:
                if getattr(block, 'type', None) == 'tool_use':
                    tool_name = getattr(block, 'name', '')
                    args = getattr(block, 'input', {}) or {}
                    call_id = getattr(block, 'id', '')

                    result = await _execute_tool(tool_name, args, sessions)

                    # Check for frontend actions
                    if tool_name == "navigate_to":
                        actions.append({"type": "navigate", "page": args.get("page", "home")})
                        result = {"status": "ok", "message": f"Navigating to {args.get('page', 'home')}"}
                    elif tool_name == "download_report":
                        actions.append({"type": "download_report", "session_id": args.get("session_id", "")})
                        result = {"status": "ok", "message": "Report download initiated"}
                    elif tool_name == "start_investigation":
                        actions.append({
                            "type": "start_investigation",
                            "capability": args.get("capability", ""),
                            "service_name": args.get("service_name", ""),
                            "profile_id": args.get("profile_id", ""),
                        })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": json.dumps(result, default=str),
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            if response.stop_reason == "end_turn":
                break

        # Extract final text response
        final_text = ""
        for block in response.content:
            if getattr(block, 'type', None) == 'text':
                final_text += getattr(block, 'text', '')

        return {
            "response": final_text,
            "actions": actions,
            "thread_messages": messages,
            "usage": llm.get_total_usage().model_dump() if hasattr(llm.get_total_usage(), 'model_dump') else {},
        }

    except asyncio.TimeoutError:
        return {"response": "Request timed out. Please try again.", "actions": [], "thread_messages": messages, "usage": {}}
    except Exception as e:
        logger.error("Assistant error: %s", e)
        return {"response": f"Something went wrong: {e}", "actions": [], "thread_messages": messages, "usage": {}}


async def _execute_tool(tool_name: str, args: dict, sessions: dict) -> dict:
    """Execute a single tool call."""
    try:
        if tool_name == "list_sessions":
            return await list_sessions(sessions)
        elif tool_name == "get_session_detail":
            return await get_session_detail(sessions, args.get("session_id", ""))
        elif tool_name == "search_sessions":
            return await search_sessions(sessions, args.get("query", ""))
        elif tool_name == "start_investigation":
            return await start_investigation(sessions, **args)
        elif tool_name == "cancel_investigation":
            return await cancel_investigation(sessions, args.get("session_id", ""))
        elif tool_name == "get_fix_recommendations":
            return await get_fix_recommendations(sessions, args.get("session_id", ""))
        elif tool_name == "navigate_to":
            return {"status": "ok", "page": args.get("page", "home")}
        elif tool_name == "download_report":
            return {"status": "ok", "session_id": args.get("session_id", "")}
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"error": str(e)}
