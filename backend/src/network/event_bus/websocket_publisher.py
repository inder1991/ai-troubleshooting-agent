"""Bridge between topology EventBus channels and WebSocket clients.

WebSocketTopologyPublisher subscribes to every topology channel and
forwards each event as a compact "delta" JSON message to all connected
WebSocket clients.  Broken connections are silently unregistered so the
publisher never blocks on a dead socket.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .base import EventBus
from .topology_channels import TOPOLOGY_CHANNELS

logger = logging.getLogger(__name__)


# ── Duck-typed WebSocket protocol ─────────────────────────────────────

class WebSocketLike(Protocol):
    """Minimal interface expected from a WebSocket connection."""

    async def send_json(self, data: dict[str, Any]) -> None: ...


# ── Publisher ─────────────────────────────────────────────────────────

class WebSocketTopologyPublisher:
    """Forwards topology events to registered WebSocket clients."""

    def __init__(self) -> None:
        self._clients: dict[str, WebSocketLike] = {}

    # ── Client management ─────────────────────────────────────────────

    def register(self, client_id: str, websocket: WebSocketLike) -> None:
        """Add a WebSocket client that will receive topology deltas."""
        self._clients[client_id] = websocket
        logger.info("WebSocket client registered: %s", client_id)

    def unregister(self, client_id: str) -> None:
        """Remove a WebSocket client."""
        self._clients.pop(client_id, None)
        logger.info("WebSocket client unregistered: %s", client_id)

    # ── EventBus integration ──────────────────────────────────────────

    async def subscribe(self, bus: EventBus) -> None:
        """Subscribe to all topology channels on *bus*."""
        for channel in TOPOLOGY_CHANNELS:
            await bus.subscribe(channel, self._handle_event)
        logger.info(
            "WebSocketTopologyPublisher subscribed to %d topology channels",
            len(TOPOLOGY_CHANNELS),
        )

    # ── Internal handlers ─────────────────────────────────────────────

    async def _handle_event(self, channel: str, event: dict[str, Any]) -> None:
        """Forward event to every connected client as a delta message."""
        delta = self._to_delta(channel, event)
        dead: list[str] = []

        for client_id, ws in list(self._clients.items()):
            try:
                await ws.send_json(delta)
            except Exception:
                logger.warning(
                    "Auto-unregistering broken WebSocket client: %s", client_id,
                )
                dead.append(client_id)

        for client_id in dead:
            self._clients.pop(client_id, None)

    @staticmethod
    def _to_delta(channel: str, event: dict[str, Any]) -> dict[str, Any]:
        """Convert an internal topology event to the frontend delta format."""
        entity_type_raw = event.get("entity_type", "")
        return {
            "event_type": event.get("event_type", ""),
            "entity_id": event.get("entity_id", ""),
            "entity_type": (
                "node" if entity_type_raw in ("device", "interface") else "edge"
            ),
            "data": event.get("data", {}),
            "changes": event.get("changes", {}),
            "timestamp": event.get("timestamp", ""),
        }
