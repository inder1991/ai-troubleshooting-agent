"""Q7 violation — bans `aiohttp`; only httpx.AsyncClient permitted."""
import aiohttp

async def fetch(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()
