"""Q7 compliant — async httpx + asyncio.sleep + no banned imports."""
import asyncio
import httpx

async def fetch(url: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.text

async def patient(seconds: float) -> None:
    await asyncio.sleep(seconds)
