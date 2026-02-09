"""
WebSocket connection management
"""

from fastapi import WebSocket
from typing import Dict
import json


class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        """Accept and store WebSocket connection"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        print(f"✅ WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        """Remove WebSocket connection"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            print(f"❌ WebSocket disconnected: {session_id}")

    async def send_message(self, session_id: str, message: dict):
        """Send message to specific session"""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_json(message)
            except Exception as e:
                print(f"❌ Error sending WebSocket message: {e}")
                self.disconnect(session_id)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        disconnected = []
        for session_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except:
                disconnected.append(session_id)
        
        # Clean up disconnected sessions
        for session_id in disconnected:
            self.disconnect(session_id)


# Global connection manager instance
manager = ConnectionManager()
