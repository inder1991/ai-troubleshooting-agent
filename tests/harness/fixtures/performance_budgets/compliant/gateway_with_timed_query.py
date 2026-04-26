"""Q12 compliant — every gateway method decorated with @timed_query.

Pretend-path: backend/src/storage/gateway.py
"""
from backend.src.storage._timing import timed_query

class StorageGateway:
    @timed_query("get_incident")
    async def get_incident(self, incident_id: str) -> None:
        pass
