"""API endpoints for protocol-first device monitoring (Datadog NDM-inspired)."""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.network.collectors.models import (
    DeviceInstance,
    DeviceStatus,
    DiscoveryConfig,
    PingConfig,
    ProtocolConfig,
    SNMPCredentials,
    SNMPVersion,
)
from src.network.collectors.instance_store import InstanceStore
from src.network.collectors.profile_loader import ProfileLoader
from src.network.collectors.snmp_collector import SNMPProtocolCollector
from src.network.collectors.autodiscovery import AutodiscoveryEngine
from src.network.collectors.ping_prober import PingProber
from src.network.collectors.event_store import EventStore
from src.network.metrics_store import MetricsStore

logger = logging.getLogger(__name__)

collector_router = APIRouter(prefix="/api/collector", tags=["collector"])

# ── Singletons (initialized at startup) ──

_instance_store: InstanceStore | None = None
_profile_loader: ProfileLoader | None = None
_snmp_collector: SNMPProtocolCollector | None = None
_autodiscovery: AutodiscoveryEngine | None = None
_ping_prober: PingProber | None = None
_event_store: EventStore | None = None
_metrics_store: MetricsStore | None = None


def init_collector_endpoints(
    instance_store: InstanceStore,
    profile_loader: ProfileLoader,
    snmp_collector: SNMPProtocolCollector,
    autodiscovery: AutodiscoveryEngine,
    ping_prober: PingProber,
    event_store: EventStore | None = None,
    metrics_store: MetricsStore | None = None,
) -> None:
    global _instance_store, _profile_loader, _snmp_collector, _autodiscovery, _ping_prober
    global _event_store, _metrics_store
    _instance_store = instance_store
    _profile_loader = profile_loader
    _snmp_collector = snmp_collector
    _autodiscovery = autodiscovery
    _ping_prober = ping_prober
    _event_store = event_store
    _metrics_store = metrics_store


def _store() -> InstanceStore:
    if not _instance_store:
        raise HTTPException(503, "Collector system not initialized")
    return _instance_store


# ── Request Models ──

class AddDeviceRequest(BaseModel):
    ip_address: str
    snmp_version: str = "2c"
    community_string: str = "public"
    port: int = 161
    v3_user: str | None = None
    v3_auth_protocol: str | None = None
    v3_auth_key: str | None = None
    v3_priv_protocol: str | None = None
    v3_priv_key: str | None = None
    tags: list[str] = Field(default_factory=list)
    profile: str | None = None
    ping: dict[str, Any] | None = None
    hostname: str | None = None


class AddDiscoveryRequest(BaseModel):
    cidr: str
    snmp_version: str = "2c"
    community: str = "public"
    v3_user: str | None = None
    v3_auth_protocol: str | None = None
    v3_auth_key: str | None = None
    v3_priv_protocol: str | None = None
    v3_priv_key: str | None = None
    port: int = 161
    interval_seconds: int = 300
    excluded_ips: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ping: dict[str, Any] | None = None


class UpdateDeviceRequest(BaseModel):
    hostname: str | None = None
    tags: list[str] | None = None
    ping: dict[str, Any] | None = None
    profile: str | None = None


# ── Device Endpoints ──

@collector_router.post("/devices")
async def add_device(req: AddDeviceRequest):
    """Add individual device by IP with SNMP credentials."""
    store = _store()

    # Check for duplicate IP
    existing = store.get_device_by_ip(req.ip_address)
    if existing:
        raise HTTPException(409, f"Device with IP {req.ip_address} already exists")

    # Build SNMP credentials
    snmp_creds = SNMPCredentials(
        version=SNMPVersion(req.snmp_version),
        community=req.community_string,
        port=req.port,
        v3_user=req.v3_user,
        v3_auth_protocol=req.v3_auth_protocol,
        v3_auth_key=req.v3_auth_key,
        v3_priv_protocol=req.v3_priv_protocol,
        v3_priv_key=req.v3_priv_key,
    )

    # Query sysObjectID for profile matching
    sys_oid = None
    matched_profile = req.profile
    vendor = ""

    if _snmp_collector:
        try:
            creds_dict = snmp_creds.model_dump()
            sys_oid = await _snmp_collector.query_sys_object_id(req.ip_address, creds_dict)
        except Exception as e:
            logger.warning("sysObjectID query failed for %s: %s", req.ip_address, e)

    if not matched_profile and sys_oid and _profile_loader:
        profile = _profile_loader.match(sys_oid)
        if profile:
            matched_profile = profile.name
            vendor = profile.vendor

    ping_cfg = PingConfig(**(req.ping or {"enabled": True}))

    device = DeviceInstance(
        device_id=str(uuid4()),
        hostname=req.hostname or req.ip_address,
        management_ip=req.ip_address,
        sys_object_id=sys_oid,
        matched_profile=matched_profile,
        vendor=vendor,
        protocols=[ProtocolConfig(protocol="snmp", priority=5, snmp=snmp_creds)],
        discovered=False,
        tags=req.tags,
        ping_config=ping_cfg,
        status=DeviceStatus.NEW,
    )

    store.upsert_device(device)
    return {"device": device.model_dump(), "message": "Device added successfully"}


@collector_router.get("/devices")
async def list_devices():
    """List all monitored devices."""
    return {"devices": [d.model_dump() for d in _store().list_devices()]}


@collector_router.get("/devices/{device_id}")
async def get_device(device_id: str):
    """Get device details."""
    device = _store().get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    return {"device": device.model_dump()}


@collector_router.put("/devices/{device_id}")
async def update_device(device_id: str, req: UpdateDeviceRequest):
    """Update device properties."""
    store = _store()
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")

    if req.hostname is not None:
        device.hostname = req.hostname
    if req.tags is not None:
        device.tags = req.tags
    if req.ping is not None:
        device.ping_config = PingConfig(**req.ping)
    if req.profile is not None and _profile_loader:
        profile = _profile_loader.get(req.profile)
        if profile:
            device.matched_profile = profile.name
            device.vendor = profile.vendor

    store.upsert_device(device)
    return {"device": device.model_dump()}


@collector_router.delete("/devices/{device_id}")
async def delete_device(device_id: str):
    """Remove a monitored device."""
    if not _store().delete_device(device_id):
        raise HTTPException(404, "Device not found")
    return {"message": "Device deleted"}


@collector_router.post("/devices/{device_id}/test")
async def test_device(device_id: str):
    """Test SNMP connectivity to a device."""
    device = _store().get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not _snmp_collector:
        raise HTTPException(503, "SNMP collector not available")

    health = await _snmp_collector.health_check(device)
    return {"health": health.model_dump()}


@collector_router.post("/devices/{device_id}/collect")
async def collect_device(device_id: str):
    """Trigger immediate collection for a device."""
    store = _store()
    device = store.get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not _snmp_collector or not _profile_loader:
        raise HTTPException(503, "Collector system not ready")

    profile = _profile_loader.get(device.matched_profile or "generic")
    if not profile:
        profile = _profile_loader.get("generic")
    if not profile:
        raise HTTPException(500, "No profile available")

    data = await _snmp_collector.collect(device, profile)
    device.last_collected = time.time()
    device.status = DeviceStatus.UP
    store.upsert_device(device)
    return {"collected_data": data.model_dump()}


# ── Discovery Config Endpoints ──

@collector_router.post("/discovery")
async def add_discovery_config(req: AddDiscoveryRequest):
    """Add autodiscovery subnet configuration."""
    store = _store()
    ping_cfg = PingConfig(**(req.ping or {"enabled": True}))

    config = DiscoveryConfig(
        config_id=str(uuid4()),
        cidr=req.cidr,
        snmp_version=SNMPVersion(req.snmp_version),
        community=req.community,
        v3_user=req.v3_user,
        v3_auth_protocol=req.v3_auth_protocol,
        v3_auth_key=req.v3_auth_key,
        v3_priv_protocol=req.v3_priv_protocol,
        v3_priv_key=req.v3_priv_key,
        port=req.port,
        interval_seconds=req.interval_seconds,
        excluded_ips=req.excluded_ips,
        tags=req.tags,
        ping=ping_cfg,
    )

    store.upsert_discovery_config(config)
    return {"config": config.model_dump(), "message": "Discovery config added"}


@collector_router.get("/discovery")
async def list_discovery_configs():
    """List all discovery configurations."""
    return {"configs": [c.model_dump() for c in _store().list_discovery_configs()]}


@collector_router.get("/discovery/{config_id}")
async def get_discovery_config(config_id: str):
    config = _store().get_discovery_config(config_id)
    if not config:
        raise HTTPException(404, "Discovery config not found")
    return {"config": config.model_dump()}


@collector_router.delete("/discovery/{config_id}")
async def delete_discovery_config(config_id: str):
    if not _store().delete_discovery_config(config_id):
        raise HTTPException(404, "Discovery config not found")
    return {"message": "Discovery config deleted"}


@collector_router.post("/discovery/{config_id}/scan")
async def trigger_scan(config_id: str):
    """Trigger immediate autodiscovery scan for a config."""
    store = _store()
    config = store.get_discovery_config(config_id)
    if not config:
        raise HTTPException(404, "Discovery config not found")
    if not _autodiscovery:
        raise HTTPException(503, "Autodiscovery engine not available")

    discovered = await _autodiscovery.scan_network(config)

    # Persist discovered devices
    for device in discovered:
        existing = store.get_device_by_ip(device.management_ip)
        if not existing:
            store.upsert_device(device)

    config.last_scan = time.time()
    config.devices_found = len(discovered)
    store.upsert_discovery_config(config)

    return {
        "devices_found": len(discovered),
        "devices": [d.model_dump() for d in discovered],
    }


# ── Profile Endpoints ──

@collector_router.get("/profiles")
async def list_profiles():
    """List all available device profiles."""
    if not _profile_loader:
        raise HTTPException(503, "Profile loader not available")
    profiles = _profile_loader.list_profiles()
    return {
        "profiles": [
            {
                "name": p.name,
                "vendor": p.vendor,
                "device_type": p.device_type,
                "sysobjectid_patterns": p.sysobjectid,
                "metric_count": len(p.metrics),
            }
            for p in profiles
        ]
    }


@collector_router.get("/profiles/{name}")
async def get_profile(name: str):
    """Get profile details."""
    if not _profile_loader:
        raise HTTPException(503, "Profile loader not available")
    profile = _profile_loader.get(name)
    if not profile:
        raise HTTPException(404, "Profile not found")
    return {"profile": profile.model_dump()}


# ── Ping Endpoint ──

@collector_router.post("/devices/{device_id}/ping")
async def ping_device(device_id: str):
    """Ping a device and return results."""
    device = _store().get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not _ping_prober:
        raise HTTPException(503, "Ping prober not available")

    result = await _ping_prober.probe(device.management_ip, device.ping_config)

    # Persist result
    device.last_ping = result
    _store().update_device_ping(device_id, result.model_dump_json())

    return {"ping": result.model_dump()}


# ── Health Endpoint ──

@collector_router.get("/health")
async def collector_health():
    """Get collector system health."""
    device_count = len(_store().list_devices()) if _instance_store else 0
    config_count = len(_store().list_discovery_configs()) if _instance_store else 0
    profile_count = len(_profile_loader.list_profiles()) if _profile_loader else 0

    return {
        "status": "ok" if _instance_store else "not_initialized",
        "device_count": device_count,
        "discovery_config_count": config_count,
        "profile_count": profile_count,
        "snmp_available": _snmp_collector is not None,
        "pysnmp_available": _snmp_collector._pysnmp_available if _snmp_collector else False,
    }


# ── Helper accessors ──

def _events() -> EventStore:
    if not _event_store:
        raise HTTPException(503, "Event store not initialized")
    return _event_store


def _metrics() -> MetricsStore:
    if not _metrics_store:
        raise HTTPException(503, "Metrics store not initialized")
    return _metrics_store


def _require_device(device_id: str) -> DeviceInstance:
    """Look up a device by ID or raise 404."""
    device = _store().get_device(device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    return device


# ── Trap Endpoints ──

@collector_router.get("/traps")
async def query_traps(
    device_id: str | None = None,
    severity: str | None = None,
    oid: str | None = None,
    time_from: float | None = None,
    time_to: float | None = None,
    limit: int = 100,
):
    """Query SNMP trap events with optional filters."""
    events = _events().query_traps(
        device_id=device_id,
        severity=severity,
        oid=oid,
        time_from=time_from,
        time_to=time_to,
        limit=limit,
    )
    return {"traps": events, "count": len(events)}


@collector_router.get("/traps/summary")
async def trap_summary(
    time_from: float | None = None,
    time_to: float | None = None,
):
    """Aggregated trap statistics: counts by severity and top OIDs."""
    return _events().trap_summary(time_from=time_from, time_to=time_to)


# ── Syslog Endpoints ──

@collector_router.get("/syslog")
async def query_syslog(
    device_id: str | None = None,
    severity: str | None = None,
    facility: str | None = None,
    search: str | None = None,
    time_from: float | None = None,
    time_to: float | None = None,
    limit: int = 100,
):
    """Query syslog events with optional filters."""
    events = _events().query_syslog(
        device_id=device_id,
        severity=severity,
        facility=facility,
        search=search,
        time_from=time_from,
        time_to=time_to,
        limit=limit,
    )
    return {"syslog": events, "count": len(events)}


@collector_router.get("/syslog/summary")
async def syslog_summary(
    time_from: float | None = None,
    time_to: float | None = None,
):
    """Aggregated syslog statistics: counts by severity and facility."""
    return _events().syslog_summary(time_from=time_from, time_to=time_to)


# ── Per-Device Event & Metric Endpoints ──

@collector_router.get("/devices/{device_id}/syslog")
async def device_syslog(device_id: str, limit: int = 100):
    """Get syslog events for a specific device."""
    _require_device(device_id)
    events = _events().query_syslog(device_id=device_id, limit=limit)
    return {"syslog": events, "count": len(events)}


@collector_router.get("/devices/{device_id}/traps")
async def device_traps(device_id: str, limit: int = 100):
    """Get SNMP trap events for a specific device."""
    _require_device(device_id)
    events = _events().query_traps(device_id=device_id, limit=limit)
    return {"traps": events, "count": len(events)}


@collector_router.get("/devices/{device_id}/metrics")
async def device_metrics(device_id: str):
    """Return the latest collected SNMP metrics for a device."""
    device = _require_device(device_id)
    if not _snmp_collector or not _profile_loader:
        raise HTTPException(503, "Collector system not ready")

    profile = _profile_loader.get(device.matched_profile or "generic")
    if not profile:
        profile = _profile_loader.get("generic")
    if not profile:
        raise HTTPException(500, "No profile available for device")

    data = await _snmp_collector.collect(device, profile)
    return {
        "device_id": device_id,
        "timestamp": data.timestamp,
        "cpu_pct": data.cpu_pct,
        "mem_pct": data.mem_pct,
        "uptime_seconds": data.uptime_seconds,
        "temperature": data.temperature,
        "interface_metrics": data.interface_metrics,
        "custom_metrics": data.custom_metrics,
        "metadata": data.metadata,
    }


@collector_router.get("/devices/{device_id}/metrics/history")
async def device_metrics_history(device_id: str, window: str = "1h"):
    """Return time-series metrics from InfluxDB for a device."""
    _require_device(device_id)
    store = _metrics()

    cpu = await store.query_device_metrics(device_id, "cpu_pct", range_str=window)
    mem = await store.query_device_metrics(device_id, "mem_pct", range_str=window)
    temp = await store.query_device_metrics(device_id, "temperature", range_str=window)

    return {
        "device_id": device_id,
        "window": window,
        "series": {
            "cpu_pct": cpu,
            "mem_pct": mem,
            "temperature": temp,
        },
    }


@collector_router.get("/devices/{device_id}/interfaces")
async def device_interfaces(device_id: str):
    """Return interface data from the last SNMP collection."""
    device = _require_device(device_id)
    if not _snmp_collector or not _profile_loader:
        raise HTTPException(503, "Collector system not ready")

    profile = _profile_loader.get(device.matched_profile or "generic")
    if not profile:
        profile = _profile_loader.get("generic")
    if not profile:
        raise HTTPException(500, "No profile available for device")

    data = await _snmp_collector.collect(device, profile)
    interfaces = []
    for iface_name, metrics in data.interface_metrics.items():
        interfaces.append({
            "name": iface_name,
            "metrics": metrics,
            "oper_status": "up" if metrics.get("ifOperStatus", 0) == 1.0 else "down",
        })

    return {
        "device_id": device_id,
        "interfaces": interfaces,
        "count": len(interfaces),
    }
