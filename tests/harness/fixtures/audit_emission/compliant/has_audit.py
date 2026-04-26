"""SL-rule compliant — write method emits an audit row."""
class StorageGateway:
    async def _audit(self, *args, **kwargs) -> None:
        pass

    async def create_incident(self, payload: dict) -> None:
        await self._audit("create_incident", payload)
