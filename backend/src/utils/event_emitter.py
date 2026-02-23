from datetime import datetime, timezone
from src.models.schemas import TaskEvent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EventEmitter:
    """Emits real-time task events via WebSocket and stores them locally."""

    def __init__(self, session_id: str, websocket_manager=None):
        self.session_id = session_id
        self._websocket_manager = websocket_manager
        self._events: list[TaskEvent] = []

    async def emit(
        self,
        agent_name: str,
        event_type: str,
        message: str,
        details: dict | None = None,
    ) -> TaskEvent:
        """Emit a task event — sends via WebSocket and stores locally."""
        event = TaskEvent(
            timestamp=datetime.now(timezone.utc),
            agent_name=agent_name,
            event_type=event_type,
            message=message,
            details=details,
            session_id=self.session_id,
        )
        self._events.append(event)

        logger.debug("Event emitted", extra={"session_id": self.session_id, "agent_name": agent_name, "action": event_type, "extra": message})

        if self._websocket_manager:
            try:
                await self._websocket_manager.send_message(
                    self.session_id,
                    {
                        "type": "task_event",
                        "data": event.model_dump(mode="json"),
                    },
                )
                logger.debug("WebSocket broadcast", extra={"session_id": self.session_id, "action": "ws_broadcast", "extra": event_type})
            except Exception as e:
                # H3: Log at WARNING — event is stored locally; frontend can catch up via GET /events
                logger.warning("WebSocket broadcast failed (event stored locally)", extra={"session_id": self.session_id, "action": "ws_broadcast_failed", "extra": str(e)})

        return event

    def get_all_events(self) -> list[TaskEvent]:
        """Return all stored events."""
        return list(self._events)

    def get_events_by_agent(self, agent_name: str) -> list[TaskEvent]:
        """Return events filtered by agent name."""
        return [e for e in self._events if e.agent_name == agent_name]
