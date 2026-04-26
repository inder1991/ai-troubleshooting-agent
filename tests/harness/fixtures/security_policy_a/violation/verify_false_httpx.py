"""Q13 violation — httpx.AsyncClient(verify=False) disables TLS validation."""
import httpx

async def fetch() -> None:
    async with httpx.AsyncClient(verify=False) as client:
        await client.get("https://example.com")
