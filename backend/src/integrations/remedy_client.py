"""
BMC Remedy ITSM client — JWT login, create incident.
"""

from src.integrations.http_clients import get_client
from src.integrations.post_retry import idempotent_post
from src.utils.logger import get_logger

logger = get_logger("remedy_client")


class RemedyClient:
    """Thin async wrapper around the BMC Remedy/Helix ITSM REST API."""

    def __init__(self, base_url: str, credentials: str, auth_method: str = "bearer_token"):
        self.base_url = base_url.rstrip("/")
        self.credentials = credentials
        self.auth_method = auth_method
        self._jwt_token: str = ""

    async def _ensure_token(self) -> str:
        """Get a valid JWT token.

        If auth_method is basic_auth, POST /api/jwt/login with username:password
        to obtain a JWT. If bearer_token, use credentials directly.
        """
        if self.auth_method == "bearer_token":
            return self.credentials

        if self._jwt_token:
            return self._jwt_token

        # basic_auth: credentials expected as "username:password"
        # K.5 — shared remedy pool; verify=_verify_for('remedy')=False by default,
        # flip via VERIFY_SSL_REMEDY=true for deployments with real CA certs.
        url = f"{self.base_url}/api/jwt/login"
        client = get_client("remedy")
        resp = await client.post(
            url,
            content=self.credentials,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        self._jwt_token = resp.text.strip()

        logger.info("Obtained Remedy JWT token")
        return self._jwt_token

    async def create_incident(
        self,
        summary: str,
        description: str,
        urgency: str = "2-High",
        impact: str = "2-Significant",
        assigned_group: str = "",
        service_ci: str = "",
    ) -> dict:
        """POST /api/arsys/v1/entry/HPD:IncidentInterface_Create.

        Returns {"values": {"Incident Number": "INC000001234", ...}}.
        """
        token = await self._ensure_token()

        url = f"{self.base_url}/api/arsys/v1/entry/HPD:IncidentInterface_Create"
        headers = {
            "Authorization": f"AR-JWT {token}",
            "Content-Type": "application/json",
        }

        values: dict = {
            "Description": summary,
            "Detailed_Decription": description,
            "Urgency": urgency,
            "Impact": impact,
            "Reported Source": "Direct Input",
            "Service_Type": "Infrastructure Event",
            "Status": "New",
        }
        if assigned_group:
            values["Assigned Group"] = assigned_group
        if service_ci:
            values["CI Name"] = service_ci

        payload = {"values": values}

        # K.5 — shared remedy pool + K.6 idempotent_post wrap so a retried POST
        # doesn't create a second incident. verify=_verify_for('remedy')=False
        # by default; flip via VERIFY_SSL_REMEDY=true for real CA certs.
        client = get_client("remedy")
        resp = await idempotent_post(client, url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        incident_number = data.get("values", {}).get("Incident Number", "")
        logger.info("Created Remedy incident %s", incident_number)
        return data
