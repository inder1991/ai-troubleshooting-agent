"""
WebSocket connection management
"""

from fastapi import WebSocket
from typing import Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        """Accept and store WebSocket connection"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info("WebSocket connected", extra={"session_id": session_id, "action": "ws_connect"})

    def disconnect(self, session_id: str):
        """Remove WebSocket connection"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info("WebSocket disconnected", extra={"session_id": session_id, "action": "ws_disconnect"})

    async def send_message(self, session_id: str, message: dict):
        """Send message to specific session"""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_json(message)
            except Exception as e:
                logger.warning("Error sending WebSocket message", extra={"session_id": session_id, "action": "ws_send_error", "extra": str(e)})
                self.disconnect(session_id)

    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        disconnected = []
        for session_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(session_id)

        for session_id in disconnected:
            self.disconnect(session_id)

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
