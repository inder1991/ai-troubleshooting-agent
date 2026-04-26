"""Synthetic StorageGateway for generator tests."""


def timed_query(name):
    def _wrap(fn): return fn
    return _wrap


class StorageGateway:
    @timed_query("get_incident")
    async def get_incident(self, incident_id: str) -> dict | None:
        return None

    @timed_query("create_incident")
    async def create_incident(self, payload: dict) -> dict:
        await self._audit("create_incident", payload)
        return {"id": "x"}

    async def _audit(self, *args, **kwargs) -> None:
        return None
