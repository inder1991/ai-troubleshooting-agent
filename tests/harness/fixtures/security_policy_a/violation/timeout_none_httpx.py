"""Q13 violation — timeout=None on outbound httpx call (unbounded wait)."""
import httpx

async def fetch() -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        await client.get("https://example.com")
