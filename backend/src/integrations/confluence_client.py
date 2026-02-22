"""
Confluence REST client — create pages in Storage Format.
"""

import base64
from typing import Optional

import httpx

from src.utils.logger import get_logger

logger = get_logger("confluence_client")


class ConfluenceClient:
    """Thin async wrapper around the Confluence REST API."""

    def __init__(self, base_url: str, credentials: str, auth_method: str = "basic_auth"):
        self.base_url = base_url.rstrip("/")
        self.credentials = credentials
        self.auth_method = auth_method

    def _auth_headers(self) -> dict:
        if not self.credentials:
            return {}
        if self.auth_method == "bearer_token" or self.auth_method == "api_token":
            return {"Authorization": f"Bearer {self.credentials}"}
        if self.auth_method == "basic_auth":
            encoded = base64.b64encode(self.credentials.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    async def create_page(
        self,
        space_key: str,
        title: str,
        body_storage_format: str,
        parent_page_id: Optional[str] = None,
    ) -> dict:
        """POST /rest/api/content — body in Confluence Storage Format (XHTML).

        Returns {"id": "12345", "_links": {"webui": "/pages/...", "base": "https://..."}}.
        """
        payload: dict = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": body_storage_format,
                    "representation": "storage",
                }
            },
        }
        if parent_page_id:
            payload["ancestors"] = [{"id": parent_page_id}]

        url = f"{self.base_url}/rest/api/content"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}

        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        page_id = data.get("id", "")
        logger.info("Created Confluence page %s in space %s", page_id, space_key)
        return data

    async def get_space(self, space_key: str) -> dict:
        """GET /rest/api/space/{key} — validates space exists."""
        url = f"{self.base_url}/rest/api/space/{space_key}"
        headers = self._auth_headers()

        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
