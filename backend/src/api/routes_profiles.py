"""Profile CRUD API endpoints."""

import os
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.integrations.profile_models import ClusterProfile, ClusterEndpoints, EndpointConfig
from src.integrations.profile_store import ProfileStore
from src.integrations.credential_resolver import get_credential_resolver
from src.integrations.audit_store import AuditLogger
from src.integrations.probe import ClusterProbe, EndpointProbeResult
from src.api.websocket import manager
from src.utils.logger import get_logger

logger = get_logger("routes_profiles")

router = APIRouter(prefix="/api/v5/profiles", tags=["profiles"])

_db_path = os.environ.get("DEBUGDUCK_DB_PATH", "./data/debugduck.db")
_profile_store: ProfileStore | None = None
_audit: AuditLogger | None = None


def get_profile_store() -> ProfileStore:
    global _profile_store
    if _profile_store is None:
        _profile_store = ProfileStore(db_path=_db_path)
        _profile_store._ensure_tables()
    return _profile_store


def get_audit() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger(db_path=_db_path)
        _audit._ensure_tables()
    return _audit


# --- Request models ---

class CreateProfileRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    cluster_type: Literal["openshift", "kubernetes"] = "openshift"
    cluster_url: str = ""
    environment: Literal["prod", "staging", "dev"] = "dev"
    auth_method: Literal["kubeconfig", "token", "service_account", "none"] = "token"
    auth_data: Optional[str] = None  # plaintext credential (will be encrypted)
    endpoints: Optional[dict] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    cluster_type: Optional[Literal["openshift", "kubernetes"]] = None
    cluster_url: Optional[str] = None
    environment: Optional[Literal["prod", "staging", "dev"]] = None
    auth_method: Optional[Literal["kubeconfig", "token", "service_account", "none"]] = None
    auth_data: Optional[str] = None
    endpoints: Optional[dict] = None


class TestEndpointRequest(BaseModel):
    endpoint_name: str  # openshift_api, prometheus, jaeger


# --- Routes ---

@router.post("/")
async def create_profile(request: CreateProfileRequest):
    store = get_profile_store()
    resolver = get_credential_resolver()
    audit = get_audit()

    profile = ClusterProfile(
        name=request.name,
        display_name=request.display_name,
        cluster_type=request.cluster_type,
        cluster_url=request.cluster_url,
        environment=request.environment,
        auth_method=request.auth_method,
    )

    # Encrypt credentials if provided (strip whitespace/newlines from pasted tokens)
    if request.auth_data:
        clean_data = request.auth_data.strip()
        handle = resolver.encrypt_and_store(profile.id, "cluster_token", clean_data)
        profile.auth_credential_handle = handle

    # Parse endpoints
    if request.endpoints:
        profile.endpoints = _parse_endpoints(profile.id, request.endpoints, resolver)

    stored = store.add(profile)
    audit.log("cluster_profile", profile.id, "created", f"Profile '{profile.name}' created")

    return stored.to_safe_dict()


@router.get("/")
async def list_profiles():
    return [p.to_safe_dict() for p in get_profile_store().list_all()]


@router.get("/active")
async def get_active_profile():
    profile = get_profile_store().get_active_profile()
    if not profile:
        return {"active_profile": None}
    return profile.to_safe_dict()


@router.get("/{profile_id}")
async def get_profile(profile_id: str):
    profile = get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile.to_safe_dict()


@router.put("/{profile_id}")
async def update_profile(profile_id: str, request: UpdateProfileRequest):
    store = get_profile_store()
    resolver = get_credential_resolver()
    audit = get_audit()

    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Update fields
    if request.name is not None:
        profile.name = request.name
    if request.display_name is not None:
        profile.display_name = request.display_name
    if request.cluster_type is not None:
        profile.cluster_type = request.cluster_type
    if request.cluster_url is not None:
        profile.cluster_url = request.cluster_url
    if request.environment is not None:
        profile.environment = request.environment
    if request.auth_method is not None:
        profile.auth_method = request.auth_method

    # Re-encrypt if new auth_data provided (strip whitespace/newlines from pasted tokens)
    if request.auth_data:
        clean_data = request.auth_data.strip()
        handle = resolver.encrypt_and_store(profile.id, "cluster_token", clean_data)
        profile.auth_credential_handle = handle
        audit.log("cluster_profile", profile.id, "credential_rotated")

    # Update endpoints
    if request.endpoints:
        profile.endpoints = _parse_endpoints(profile.id, request.endpoints, resolver)

    profile.updated_at = datetime.now()
    store.update(profile)
    audit.log("cluster_profile", profile.id, "updated")

    # Broadcast change
    await _broadcast_profile_change(profile.id, "updated")

    return profile.to_safe_dict()


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str):
    store = get_profile_store()
    audit = get_audit()
    resolver = get_credential_resolver()

    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Clean up secrets
    resolver.delete(profile_id, "cluster_token")
    store.delete(profile_id)
    audit.log("cluster_profile", profile_id, "deleted", f"Profile '{profile.name}' deleted")

    await _broadcast_profile_change(profile_id, "deleted")

    return {"status": "deleted"}


@router.post("/{profile_id}/activate")
async def activate_profile(profile_id: str):
    store = get_profile_store()
    audit = get_audit()

    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    store.set_active(profile_id)
    audit.log("cluster_profile", profile_id, "activated")

    await _broadcast_profile_change(profile_id, "activated")

    return {"status": "activated", "profile_id": profile_id}


@router.post("/{profile_id}/test-endpoint")
async def test_endpoint(profile_id: str, request: TestEndpointRequest):
    store = get_profile_store()
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    endpoint_name = request.endpoint_name
    endpoint: EndpointConfig | None = getattr(profile.endpoints, endpoint_name, None)

    if not endpoint:
        raise HTTPException(status_code=400, detail=f"Endpoint '{endpoint_name}' not configured")

    # Test connectivity via HTTP
    import httpx
    import time

    result = EndpointProbeResult(name=endpoint_name)
    headers = {}

    # Resolve credentials if present
    if endpoint.auth_credential_handle:
        resolver = get_credential_resolver()
        try:
            creds = resolver.resolve(profile_id, endpoint_name, endpoint.auth_credential_handle)
            if endpoint.auth_method == "bearer_token":
                headers["Authorization"] = f"Bearer {creds}"
            elif endpoint.auth_method == "basic_auth":
                import base64
                headers["Authorization"] = f"Basic {base64.b64encode(creds.encode()).decode()}"
            elif endpoint.auth_method == "api_key":
                headers["Authorization"] = f"ApiKey {creds}"
        except Exception as e:
            result.error = f"Credential resolution failed: {e}"
            return result.model_dump()

    test_url = endpoint.url.rstrip("/")
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.get(test_url, headers=headers)
            result.latency_ms = round((time.monotonic() - start) * 1000, 1)
            if resp.status_code < 400:
                result.reachable = True
                endpoint.verified = True
                endpoint.status = "healthy"
            else:
                endpoint.status = "connection_failed"
                result.error = f"HTTP {resp.status_code}"
    except Exception as e:
        endpoint.status = "unreachable"
        result.error = str(e)

    endpoint.last_verified = datetime.now()
    store.update(profile)

    get_audit().log("cluster_profile", profile_id, "probed", f"Tested {endpoint_name}")

    return result.model_dump()


@router.post("/{profile_id}/probe")
async def probe_profile(profile_id: str):
    store = get_profile_store()
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    probe = ClusterProbe()

    # Build a temporary IntegrationConfig for backward compatibility with probe
    from src.integrations.models import IntegrationConfig
    resolver = get_credential_resolver()
    auth_data = ""
    if profile.auth_credential_handle:
        try:
            auth_data = resolver.resolve(profile.id, "cluster_token", profile.auth_credential_handle)
            auth_data = auth_data.strip()
        except Exception:
            pass

    config = IntegrationConfig(
        id=profile.id,
        name=profile.name,
        cluster_type=profile.cluster_type,
        cluster_url=profile.cluster_url,
        auth_method=profile.auth_method,
        auth_data=auth_data,
    )

    result = await probe.probe(config)

    # Update profile with probe results
    if result.reachable:
        profile.status = "connected"
    else:
        profile.status = "unreachable"

    if result.cluster_version:
        profile.cluster_version = result.cluster_version

    # Write discovered endpoint URLs back into the profile
    if result.prometheus_url:
        if not profile.endpoints.prometheus:
            profile.endpoints.prometheus = EndpointConfig(url=result.prometheus_url, auth_method="none")
        elif not profile.endpoints.prometheus.url:
            profile.endpoints.prometheus.url = result.prometheus_url
        ep = profile.endpoints.prometheus
        ep.verified = True
        ep.last_verified = datetime.now()
        ep.status = "healthy"

    if result.elasticsearch_url:
        if not profile.endpoints.jaeger:
            # Store in a discoverable field — elasticsearch isn't a separate endpoint type,
            # but we log it for visibility
            pass
        # Log discovery for audit trail
        logger.info(f"Discovered elasticsearch at {result.elasticsearch_url} for profile {profile_id}")

    # Update endpoint statuses from probe results
    for ep_name, ep_result in result.endpoint_results.items():
        endpoint = getattr(profile.endpoints, ep_name, None)
        if endpoint and ep_result.reachable:
            endpoint.status = "healthy"
            endpoint.verified = True
            endpoint.last_verified = datetime.now()
            if ep_result.discovered_url and not endpoint.url:
                endpoint.url = ep_result.discovered_url
        elif endpoint and ep_result.error:
            endpoint.status = "unreachable"

    profile.last_synced = datetime.now()
    profile.updated_at = datetime.now()
    store.update(profile)

    get_audit().log("cluster_profile", profile_id, "probed", f"Full probe, reachable={result.reachable}")

    return result.model_dump()


# --- Helpers ---

def _parse_endpoints(profile_id: str, endpoints_data: dict, resolver) -> ClusterEndpoints:
    """Parse endpoint data from request, encrypting credentials."""
    endpoints = ClusterEndpoints()
    for ep_name in ("openshift_api", "prometheus", "jaeger"):
        ep_data = endpoints_data.get(ep_name)
        if ep_data:
            handle = None
            if ep_data.get("auth_data"):
                handle = resolver.encrypt_and_store(profile_id, ep_name, ep_data["auth_data"].strip())
            ep = EndpointConfig(
                url=ep_data.get("url", ""),
                auth_method=ep_data.get("auth_method", "none"),
                auth_credential_handle=handle,
            )
            setattr(endpoints, ep_name, ep)
    return endpoints


async def _broadcast_profile_change(profile_id: str, change_type: str):
    """Broadcast profile change to all connected WebSocket clients."""
    try:
        await manager.broadcast({
            "type": "profile_change",
            "data": {
                "profile_id": profile_id,
                "change_type": change_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })
    except Exception as e:
        logger.warning("Failed to broadcast profile change: %s", e)
