"""CRUD endpoints for core network resources (subnet, interface, route, zone)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.network.models import Device, Subnet, Interface, Route, Zone
from src.network.interface_validation import validate_device_interfaces
from src.utils.logger import get_logger

logger = get_logger(__name__)

resource_router = APIRouter(prefix="/api/v4/network/resources", tags=["resources"])

_topology_store = None


def init_resource_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


# ── Bulk Device Operations ────────────────────────────────────────────

@resource_router.post("/devices/bulk", status_code=201)
def bulk_create_devices(devices: list[Device]):
    store = _store()
    for device in devices:
        store.add_device(device)
    return {"created": len(devices)}


class _BulkDeleteRequest(BaseModel):
    ids: list[str]


@resource_router.delete("/devices/bulk")
def bulk_delete_devices(body: _BulkDeleteRequest):
    store = _store()
    for device_id in body.ids:
        store.delete_device(device_id)
    return {"deleted": len(body.ids)}


# ── Subnet CRUD ──────────────────────────────────────────────────────

@resource_router.post("/subnets/bulk", status_code=201)
def bulk_create_subnets(subnets: list[Subnet]):
    store = _store()
    for subnet in subnets:
        store.add_subnet(subnet)
    return {"created": len(subnets)}


@resource_router.post("/subnets", status_code=201)
def create_subnet(subnet: Subnet):
    _store().add_subnet(subnet)
    return subnet.model_dump()


@resource_router.get("/subnets")
def list_subnets():
    return _store().list_subnets()


# ── Interface CRUD ───────────────────────────────────────────────────

@resource_router.post("/interfaces/bulk", status_code=201)
def bulk_create_interfaces(interfaces: list[Interface]):
    store = _store()
    for iface in interfaces:
        store.add_interface(iface)
    return {"created": len(interfaces)}


@resource_router.post("/interfaces", status_code=201)
def create_interface(iface: Interface):
    _store().add_interface(iface)
    return iface.model_dump()


@resource_router.get("/interfaces")
def list_interfaces(device_id: str = None):
    return _store().list_interfaces(device_id=device_id)


# ── Route CRUD ───────────────────────────────────────────────────────

@resource_router.post("/routes/bulk", status_code=201)
def bulk_create_routes(routes: list[Route]):
    _store().bulk_add_routes(routes)
    return {"created": len(routes)}


@resource_router.post("/routes", status_code=201)
def create_route(route: Route):
    _store().add_route(route)
    return route.model_dump()


@resource_router.get("/routes")
def list_routes(device_id: str = None):
    return _store().list_routes(device_id=device_id)


# ── Zone CRUD ────────────────────────────────────────────────────────

@resource_router.post("/zones", status_code=201)
def create_zone(zone: Zone):
    _store().add_zone(zone)
    return zone.model_dump()


@resource_router.get("/zones")
def list_zones():
    return _store().list_zones()


# ── Interface Validation ────────────────────────────────────────────

class _BulkValidateRequest(BaseModel):
    device_ids: list[str]


def _validate_device(device_id: str) -> dict:
    """Run interface validation rules for a single device and return results."""
    store = _store()
    interfaces = store.list_interfaces(device_id=device_id)
    subnets = store.list_subnets()
    zones = store.list_zones()
    errors = validate_device_interfaces(device_id, interfaces, subnets, zones)
    return {"device_id": device_id, "errors": errors}


@resource_router.post("/validate/bulk")
def validate_bulk(body: _BulkValidateRequest):
    """Validate interfaces for multiple devices at once."""
    return [_validate_device(did) for did in body.device_ids]


@resource_router.get("/validate/{device_id}")
def validate_device(device_id: str):
    """Validate all interfaces for a single device."""
    return _validate_device(device_id)
