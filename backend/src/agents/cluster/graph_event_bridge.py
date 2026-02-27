"""Filter LangGraph astream_events(v2) into EventEmitter for WebSocket delivery."""

from __future__ import annotations
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)

_KNOWN_NODES = {
    "pre_flight", "ctrl_plane_agent", "node_agent",
    "network_agent", "storage_agent", "synthesize",
    "dispatch", "confidence_check",
}

_INTERNAL_PREFIXES = {"Runnable", "ChatAnthropic", "ChannelWrite", "ChannelRead"}


class GraphEventBridge:
    def __init__(self, diagnostic_id: str, emitter: Any):
        self.diagnostic_id = diagnostic_id
        self._emitter = emitter

    def _is_internal(self, name: str) -> bool:
        return any(name.startswith(prefix) for prefix in _INTERNAL_PREFIXES)

    def _extract_domain(self, name: str, tags: list[str]) -> str:
        if "ctrl_plane" in name:
            return "ctrl_plane"
        if "node_agent" in name:
            return "node"
        if "network" in name:
            return "network"
        if "storage" in name:
            return "storage"
        if "synthesize" in name:
            return "supervisor"
        for tag in tags:
            if tag in ("ctrl_plane", "node", "network", "storage"):
                return tag
        return "supervisor"

    async def handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("event", "")
        name = event.get("name", "")
        tags = event.get("tags", [])

        if self._is_internal(name):
            return

        domain = self._extract_domain(name, tags)

        if event_type == "on_chain_start" and name in _KNOWN_NODES:
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="agent_started",
                message=f"Starting {name}",
                details={"diagnostic_id": self.diagnostic_id, "domain": domain, "node_name": name},
            )
        elif event_type == "on_chain_end" and name in _KNOWN_NODES:
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="agent_completed",
                message=f"Completed {name}",
                details={"diagnostic_id": self.diagnostic_id, "domain": domain, "node_name": name},
            )
        elif event_type == "on_tool_start":
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="tool_call",
                message=f"Querying: {name}",
                details={"diagnostic_id": self.diagnostic_id, "domain": domain, "tool_name": name, "tool_input": str(event.get("data", {}).get("input", ""))[:200]},
            )
        elif event_type == "on_tool_end":
            output = event.get("data", {}).get("output", "")
            summary = str(output)[:300] if output else ""
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="tool_result",
                message=summary,
                details={"diagnostic_id": self.diagnostic_id, "domain": domain, "tool_name": name},
            )
