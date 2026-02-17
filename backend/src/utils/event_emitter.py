from datetime import datetime, timezone
from src.models.schemas import TaskEvent


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
        )
        self._events.append(event)

        if self._websocket_manager:
            event_data = event.model_dump(mode="json")
            event_data["session_id"] = self.session_id
            await self._websocket_manager.send_message(
                self.session_id,
                {
                    "type": "task_event",
                    "data": event_data,
                },
            )

        return event

    def get_all_events(self) -> list[TaskEvent]:
        """Return all stored events."""
        return list(self._events)

    def get_events_by_agent(self, agent_name: str) -> list[TaskEvent]:
        """Return events filtered by agent name."""
        return [e for e in self._events if e.agent_name == agent_name]
