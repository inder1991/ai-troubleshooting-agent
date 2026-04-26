"""Q12 violation — StorageGateway method without @timed_query.

Pretend-path: backend/src/storage/gateway.py
"""
class StorageGateway:
    async def get_incident(self, incident_id: str) -> None:
        pass
