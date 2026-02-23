"""
WebSocket connection management
"""

from fastapi import WebSocket
from typing import Dict, List

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections — supports multiple connections per session."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        """Accept and store WebSocket connection"""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info("WebSocket connected", extra={"session_id": session_id, "action": "ws_connect", "extra": {"total": len(self.active_connections[session_id])}})

    def disconnect(self, session_id: str, websocket: WebSocket = None):
        """Remove WebSocket connection"""
        if session_id not in self.active_connections:
            return
        if websocket:
            self.active_connections[session_id] = [
                ws for ws in self.active_connections[session_id] if ws is not websocket
            ]
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        else:
            del self.active_connections[session_id]
        logger.info("WebSocket disconnected", extra={"session_id": session_id, "action": "ws_disconnect"})

    async def send_message(self, session_id: str, message: dict):
        """Send message to all connections for a session. H2: Retries once on failure."""
        if session_id not in self.active_connections:
            return
        disconnected = []
        for ws in self.active_connections[session_id]:
            try:
                await ws.send_json(message)
            except Exception:
                # H2: Retry once before disconnecting
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.warning("WebSocket send failed after retry", extra={"session_id": session_id, "action": "ws_send_error", "extra": str(e)})
                    disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(session_id, ws)

    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        disconnected = []
        for session_id, connections in self.active_connections.items():
            for ws in connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append((session_id, ws))

        for session_id, ws in disconnected:
            self.disconnect(session_id, ws)

    async def broadcast_profile_change(self, profile_id: str, change_type: str):
        """Broadcast a profile change event to all connected sessions."""
        from datetime import datetime, timezone

        await self.broadcast({
            "type": "profile_change",
            "data": {
                "profile_id": profile_id,
                "change_type": change_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })


# Global connection manager instance
manager = ConnectionManager()
