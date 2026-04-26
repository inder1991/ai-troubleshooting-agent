"""Q9 compliant — test makes outbound calls, but they are mocked via respx."""
import httpx
import respx

@respx.mock
async def test_outbound() -> None:
    respx.get("https://example.com").respond(200, json={"ok": True})
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://example.com")
        assert resp.json() == {"ok": True}
