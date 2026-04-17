"""
Jira REST v2 client — create issues, add comments, link PRs.
"""

import base64
from typing import Optional

from src.integrations.http_clients import get_client
from src.integrations.post_retry import idempotent_post
from src.utils.logger import get_logger

logger = get_logger("jira_client")


class JiraClient:
    """Thin async wrapper around Jira REST API v2."""

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

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Bug",
        priority: str = "High",
        labels: Optional[list[str]] = None,
    ) -> dict:
        """POST /rest/api/2/issue — returns {"key": "PROJ-123", "self": "..."}."""
        payload: dict = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
            }
        }
        if priority:
            payload["fields"]["priority"] = {"name": priority}
        if labels:
            payload["fields"]["labels"] = labels

        url = f"{self.base_url}/rest/api/2/issue"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}

        # K.5 — shared per-backend singleton (connection reuse + K.11
        # traceparent injection). K.6 idempotent_post still wraps.
        # verify=_verify_for('jira')=False by default; ops flip via
        # VERIFY_SSL_JIRA=true for deployments with real CA certs.
        client = get_client("jira")
        resp = await idempotent_post(client, url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        issue_key = data.get("key", "")
        logger.info("Created Jira issue %s in project %s", issue_key, project_key)
        return data

    async def add_comment(self, issue_key: str, comment: str) -> dict:
        """POST /rest/api/2/issue/{key}/comment."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/comment"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        payload = {"body": comment}

        client = get_client("jira")
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def add_remote_link(self, issue_key: str, url: str, title: str) -> dict:
        """POST /rest/api/2/issue/{key}/remotelink — links a PR to an issue."""
        endpoint = f"{self.base_url}/rest/api/2/issue/{issue_key}/remotelink"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        payload = {
            "object": {
                "url": url,
                "title": title,
            }
        }

        client = get_client("jira")
        resp = await client.post(endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()
