"""SL-rule violation — gateway write without _audit emission."""
class StorageGateway:
    async def create_incident(self, payload: dict) -> None:
        pass
