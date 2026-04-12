from __future__ import annotations
from src.utils.attestation_log import AttestationLogger


class SessionReplayer:
    def __init__(self, logger: AttestationLogger):
        self._logger = logger

    async def replay(self, session_id: str) -> list[dict]:
        decisions = await self._logger.query(session_id=session_id)
        lifecycle = await self._logger.query_lifecycle(session_id=session_id)

        all_events = []
        for d in decisions:
            all_events.append({
                "event_class": "decision",
                "timestamp": d.get("decided_at", ""),
                **d,
            })
        for lc in lifecycle:
            all_events.append({
                "event_class": "lifecycle",
                "timestamp": lc.get("timestamp", ""),
                **lc,
            })

        all_events.sort(key=lambda e: e.get("timestamp", ""))
        return all_events
