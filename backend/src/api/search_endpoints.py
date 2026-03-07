"""Device search with filters and network statistics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from src.network.models import Device, DeviceType
from src.utils.logger import get_logger

logger = get_logger(__name__)

search_router = APIRouter(prefix="/api/v4/network/search", tags=["search"])

_topology_store = None


def init_search_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


@search_router.get("/devices")
def search_devices(
    name: str = None,
    device_type: str = None,
    vendor: str = None,
    location: str = None,
    offset: int = 0,
    limit: int = 50,
):
    """Search devices with optional filters (name LIKE, others exact match).

    Returns paginated results with total count.
    """
    store = _store()
    conditions: list[str] = []
    params: list = []

    if name:
        conditions.append("name LIKE ?")
        params.append(f"%{name}%")
    if device_type:
        conditions.append("device_type = ?")
        params.append(device_type)
    if vendor:
        conditions.append("vendor = ?")
        params.append(vendor)
    if location:
        conditions.append("location = ?")
        params.append(location)

    where = " AND ".join(conditions) if conditions else "1=1"

    conn = store._conn()
    try:
        # Get total count matching the filters
        count_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM devices WHERE {where}", params
        ).fetchone()
        total = count_row["cnt"]

        # Get paginated results
        rows = conn.execute(
            f"SELECT * FROM devices WHERE {where} LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

        devices = []
        for r in rows:
            d = dict(r)
            devices.append(Device(
                id=d["id"], name=d["name"], vendor=d.get("vendor") or "",
                device_type=DeviceType(d["device_type"]) if d.get("device_type") else DeviceType.HOST,
                management_ip=d.get("management_ip") or "", model=d.get("model") or "",
                location=d.get("location") or "",
                zone_id=d.get("zone_id") or "",
                vlan_id=d.get("vlan_id") or 0,
                description=d.get("description") or "",
                ha_group_id=d.get("ha_group_id") or "",
                ha_role=d.get("ha_role") or "",
            ).model_dump())
    finally:
        conn.close()

    return {"devices": devices, "total": total, "offset": offset, "limit": limit}


@search_router.get("/stats")
def get_stats():
    """Aggregate network statistics: total counts and breakdowns by type/vendor."""
    store = _store()
    conn = store._conn()
    try:
        # Total counts
        total_devices = conn.execute("SELECT COUNT(*) AS cnt FROM devices").fetchone()["cnt"]
        total_interfaces = conn.execute("SELECT COUNT(*) AS cnt FROM interfaces").fetchone()["cnt"]
        total_subnets = conn.execute("SELECT COUNT(*) AS cnt FROM subnets").fetchone()["cnt"]

        # Breakdown by device_type
        by_type: dict[str, int] = {}
        for row in conn.execute(
            "SELECT device_type, COUNT(*) AS cnt FROM devices GROUP BY device_type"
        ).fetchall():
            dtype = row["device_type"]
            if dtype:
                by_type[dtype] = row["cnt"]

        # Breakdown by vendor
        by_vendor: dict[str, int] = {}
        for row in conn.execute(
            "SELECT vendor, COUNT(*) AS cnt FROM devices WHERE vendor != '' GROUP BY vendor"
        ).fetchall():
            by_vendor[row["vendor"]] = row["cnt"]
    finally:
        conn.close()

    return {
        "total_devices": total_devices,
        "total_interfaces": total_interfaces,
        "total_subnets": total_subnets,
        "by_type": by_type,
        "by_vendor": by_vendor,
    }
