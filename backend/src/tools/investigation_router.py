"""
InvestigationRouter: Fast Path (slash commands, buttons) + Smart Path (NL -> Haiku LLM).
Both paths converge on ToolExecutor.execute() -> EvidencePinFactory.from_tool_result().
"""

import asyncio
import json
from typing import Optional, Any

from src.tools.tool_executor import ToolExecutor
from src.tools.tool_result import ToolResult
from src.tools.evidence_pin_factory import EvidencePinFactory
from src.tools.router_models import InvestigateRequest, InvestigateResponse, RouterContext
from src.tools.tool_registry import TOOL_REGISTRY, SLASH_COMMAND_MAP
from src.models.schemas import EvidencePin
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InvestigationRouter:
    """Routes investigation requests via Fast Path or Smart Path.

    Fast Path: slash commands (/logs, /promql, etc.) and quick_action button
    payloads are parsed without LLM involvement.

    Smart Path: natural language queries are classified by an LLM (Haiku) into
    an intent + params JSON payload.

    Both paths resolve context defaults, dispatch to ToolExecutor, and wrap the
    result in an EvidencePin via EvidencePinFactory.
    """

    def __init__(self, tool_executor: ToolExecutor, llm_client=None):
        self._executor = tool_executor
        self._llm = llm_client

    async def route(self, request: InvestigateRequest) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        """Route an investigation request to the correct tool. Returns (response, pin)."""
        if request.quick_action:
            return await self._fast_path_quick_action(request)
        elif request.command:
            return await self._fast_path_slash_command(request)
        elif request.query:
            return await self._smart_path(request)
        else:
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="fast", status="error",
                error="No input provided",
            ), None

    # -- Fast Path: Quick Action Button ------------------------------------

    async def _fast_path_quick_action(
        self, request: InvestigateRequest
    ) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        qa = request.quick_action
        params = self._apply_context_defaults(qa.intent, qa.params, request.context)

        try:
            result = await self._executor.execute(qa.intent, params)
        except KeyError:
            return InvestigateResponse(
                pin_id="", intent=qa.intent, params=params, path_used="fast",
                status="error", error=f"Unknown tool: {qa.intent}",
            ), None

        pin = EvidencePinFactory.from_tool_result(result, "quick_action", request.context)
        return InvestigateResponse(
            pin_id=pin.id, intent=qa.intent, params=params,
            path_used="fast", status="executing",
        ), pin

    # -- Fast Path: Slash Command ------------------------------------------

    async def _fast_path_slash_command(
        self, request: InvestigateRequest
    ) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        command = request.command.strip()
        parsed = self._parse_slash_command(command)

        if not parsed:
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="fast",
                status="error", error=f"Unknown command: {command.split()[0]}",
            ), None

        intent, params = parsed
        params = self._apply_context_defaults(intent, params, request.context)

        try:
            result = await self._executor.execute(intent, params)
        except KeyError:
            return InvestigateResponse(
                pin_id="", intent=intent, params=params, path_used="fast",
                status="error", error=f"Unknown tool: {intent}",
            ), None

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", request.context)
        return InvestigateResponse(
            pin_id=pin.id, intent=intent, params=params,
            path_used="fast", status="executing",
        ), pin

    # -- Smart Path: Natural Language -> Haiku LLM -------------------------

    async def _smart_path(
        self, request: InvestigateRequest
    ) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        if not self._llm:
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="smart",
                status="error", error="LLM client not configured for smart path",
            ), None

        system_prompt = self._build_smart_prompt(request.context)
        try:
            llm_response = await asyncio.wait_for(
                self._llm.chat(
                    user_message=request.query,
                    system_prompt=system_prompt,
                ),
                timeout=15.0,
            )
            parsed = json.loads(llm_response.text)
            intent = parsed["intent"]
            params = parsed.get("params", {})
        except asyncio.TimeoutError:
            logger.error("Smart path LLM call timed out after 15s", extra={
                "action": "smart_path_timeout",
                "extra": {"query": request.query},
            })
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="smart",
                status="error", error="Smart path timed out",
            ), None
        except (json.JSONDecodeError, KeyError) as e:
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="smart",
                status="error", error=f"Failed to parse LLM response: {e}",
            ), None

        params = self._apply_context_defaults(intent, params, request.context)

        try:
            result = await self._executor.execute(intent, params)
        except KeyError:
            return InvestigateResponse(
                pin_id="", intent=intent, params=params, path_used="smart",
                status="error", error=f"Unknown tool: {intent}",
            ), None

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", request.context)
        return InvestigateResponse(
            pin_id=pin.id, intent=intent, params=params,
            path_used="smart", status="executing",
        ), pin

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _parse_slash_command(command: str) -> Optional[tuple[str, dict]]:
        """Parse '/logs namespace=x pod=y' into (intent, {namespace: x, pod: y})."""
        parts = command.strip().split()
        if not parts or not parts[0].startswith("/"):
            return None

        slash = parts[0]
        intent = SLASH_COMMAND_MAP.get(slash)
        if not intent:
            return None

        params: dict[str, Any] = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                # Convert boolean strings
                if value.lower() in ("true", "false"):
                    params[key] = value.lower() == "true"
                else:
                    # Try integer conversion
                    try:
                        params[key] = int(value)
                    except ValueError:
                        params[key] = value

        return intent, params

    @staticmethod
    def _apply_context_defaults(intent: str, params: dict, context: RouterContext) -> dict:
        """Fill missing params from RouterContext using tool registry defaults."""
        tool_def = next((t for t in TOOL_REGISTRY if t["intent"] == intent), None)
        if not tool_def:
            return params

        for param_def in tool_def.get("params_schema", []):
            name = param_def["name"]
            ctx_field = param_def.get("default_from_context")
            if name not in params and ctx_field:
                ctx_value = getattr(context, ctx_field, None)
                if ctx_value is not None:
                    params[name] = ctx_value

        return params

    @staticmethod
    def _build_smart_prompt(context: RouterContext) -> str:
        """Build the system prompt for LLM-based intent classification."""
        tool_descriptions = "\n".join(
            f"- {t['intent']}: {t['description']} (params: {', '.join(p['name'] for p in t.get('params_schema', []))})"
            for t in TOOL_REGISTRY
        )
        return f"""You are an investigation router. Parse the user's request into a tool call.

Current context:
- Active namespace: {context.active_namespace}
- Active service: {context.active_service}
- Active pod: {context.active_pod}
- Known pods: {', '.join(context.pod_names[:20])}
- Time window: {context.time_window.start} to {context.time_window.end}

Available tools:
{tool_descriptions}

Use the active context to fill any missing parameters.
Output ONLY valid JSON: {{"intent": "tool_name", "params": {{...}}}}
"""
