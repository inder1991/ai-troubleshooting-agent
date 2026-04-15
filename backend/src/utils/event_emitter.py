from datetime import datetime, timezone
from typing import Optional

from src.models.schemas import TaskEvent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EventEmitter:
    """Emits real-time task events via WebSocket and persists them to DiagnosticStore."""

    def __init__(self, session_id: str, websocket_manager=None, store=None):
        self.session_id = session_id
        self._websocket_manager = websocket_manager
        self._store = store
        self._events: list[TaskEvent] = []
        self._pubsub_bridge = None

    def set_pubsub_bridge(self, bridge) -> None:
        """Attach a RedisPubSubBridge for cross-instance event broadcasting."""
        self._pubsub_bridge = bridge

    async def emit(
        self,
        agent_name: str,
        event_type: str,
        message: str,
        details: dict | None = None,
    ) -> TaskEvent:
        """Emit a task event — persists to store, broadcasts via WebSocket."""
        event = TaskEvent(
            timestamp=datetime.now(timezone.utc),
            agent_name=agent_name,
            event_type=event_type,
            message=message,
            details=details,
            session_id=self.session_id,
        )

        # Persist to store first — assigns sequence_number
        if self._store is not None:
            try:
                seq = await self._store.append_event(
                    self.session_id, event.model_dump(mode="json")
                )
                event.sequence_number = seq
            except Exception as e:
                logger.warning("Failed to persist event to store: %s", e,
                               extra={"session_id": self.session_id})

        self._events.append(event)
        logger.debug("Event emitted", extra={
            "session_id": self.session_id, "agent_name": agent_name,
            "action": event_type, "extra": message,
        })

        if self._websocket_manager:
            try:
                await self._websocket_manager.send_message(
                    self.session_id,
                    {"type": "task_event", "data": event.model_dump(mode="json")},
                )
            except Exception as e:
                logger.warning(
                    "WebSocket broadcast failed (event persisted at seq=%s)",
                    event.sequence_number,
                    extra={"session_id": self.session_id, "action": "ws_broadcast_failed",
                           "extra": str(e)},
                )

        if self._pubsub_bridge:
            try:
                await self._pubsub_bridge.publish(
                    self.session_id,
                    {"type": "task_event", "data": event.model_dump(mode="json")},
                )
            except Exception as e:
                logger.warning(
                    "Redis pub/sub publish failed (event persisted at seq=%s)",
                    event.sequence_number,
                    extra={"session_id": self.session_id, "action": "pubsub_publish_failed",
                           "extra": str(e)},
                )

        return event

    def get_all_events(self) -> list[TaskEvent]:
        """Return all in-memory events for this session."""
        return list(self._events)

    def get_events_by_agent(self, agent_name: str) -> list[TaskEvent]:
        """Return events filtered by agent name."""
        return [e for e in self._events if e.agent_name == agent_name]
