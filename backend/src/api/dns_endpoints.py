"""DNS monitoring API endpoints."""
from __future__ import annotations

import logging
from fastapi import APIRouter

from ..network.models import (
    DNSServerConfig, DNSWatchedHostname, DNSMonitorConfig, DNSRecordType,
)
from ..network.dns_monitor import DNSMonitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v4/dns", tags=["dns"])

# Module-level state — set at startup via init_dns_endpoints()
_dns_config = DNSMonitorConfig()
_dns_monitor: DNSMonitor | None = None
_metrics_store = None


def init_dns_endpoints(dns_monitor: DNSMonitor | None, metrics_store=None) -> None:
    """Called at app startup to wire in the live DNSMonitor instance."""
    global _dns_monitor, _dns_config, _metrics_store
    _dns_monitor = dns_monitor
    if dns_monitor:
        _dns_config = dns_monitor.config
    _metrics_store = metrics_store


@router.get("/config")
async def get_dns_config():
    return _dns_config.model_dump()


@router.put("/config")
async def update_dns_config(config: DNSMonitorConfig):
    global _dns_config, _dns_monitor
    _dns_config = config
    _dns_monitor = DNSMonitor(config)
    return _dns_config.model_dump()


@router.post("/servers")
async def add_dns_server(server: DNSServerConfig):
    _dns_config.servers.append(server)
    return {"status": "ok", "server_count": len(_dns_config.servers)}


@router.delete("/servers/{server_id}")
async def remove_dns_server(server_id: str):
    _dns_config.servers = [s for s in _dns_config.servers if s.id != server_id]
    return {"status": "ok", "server_count": len(_dns_config.servers)}


@router.post("/hostnames")
async def add_watched_hostname(hostname: DNSWatchedHostname):
    _dns_config.watched_hostnames.append(hostname)
    return {"status": "ok", "hostname_count": len(_dns_config.watched_hostnames)}


@router.delete("/hostnames/{hostname}")
async def remove_watched_hostname(hostname: str):
    _dns_config.watched_hostnames = [
        h for h in _dns_config.watched_hostnames if h.hostname != hostname
    ]
    return {"status": "ok", "hostname_count": len(_dns_config.watched_hostnames)}


@router.post("/query")
async def query_dns_now(body: dict):
    hostname = body.get("hostname", "")
    record_type = body.get("record_type", "A")
    server_ip = body.get("server_ip", "8.8.8.8")
    monitor = _dns_monitor or DNSMonitor(DNSMonitorConfig())
    server = DNSServerConfig(id="adhoc", name="Ad-hoc", ip=server_ip)
    watched = DNSWatchedHostname(hostname=hostname, record_type=DNSRecordType(record_type))
    result = await monitor.query_hostname(server, watched)
    return {
        "hostname": result.hostname,
        "record_type": result.record_type,
        "server_ip": result.server_ip,
        "values": result.values,
        "latency_ms": result.latency_ms,
        "success": result.success,
        "error": result.error,
    }


@router.get("/metrics")
async def get_dns_metrics(range: str = "1h", server_id: str = "", hostname: str = ""):
    if not _metrics_store:
        return []
    return await _metrics_store.query_dns_metrics(
        server_id=server_id, hostname=hostname, range_str=range,
    )


@router.get("/nxdomain")
async def get_nxdomain_counts():
    if not _dns_monitor:
        return {}
    return _dns_monitor.get_nxdomain_counts()
