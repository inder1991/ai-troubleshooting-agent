"""CRUD endpoints for cloud & connectivity resources."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from src.network.models import (
    VPC, RouteTable, VPCPeering, TransitGateway, VPNTunnel, DirectConnect,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

cloud_router = APIRouter(prefix="/api/v4/network/cloud", tags=["cloud"])

_topology_store = None


def init_cloud_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


# ── VPC CRUD ──────────────────────────────────────────────────────────

@cloud_router.post("/vpcs", status_code=201)
def create_vpc(vpc: VPC):
    _store().add_vpc(vpc)
    return vpc.model_dump()


@cloud_router.get("/vpcs")
def list_vpcs():
    return _store().list_vpcs()


# ── RouteTable CRUD ──────────────────────────────────────────────────

@cloud_router.post("/route-tables", status_code=201)
def create_route_table(rt: RouteTable):
    _store().add_route_table(rt)
    return rt.model_dump()


@cloud_router.get("/route-tables")
def list_route_tables(vpc_id: str = None):
    return _store().list_route_tables(vpc_id=vpc_id)


# ── VPCPeering CRUD ──────────────────────────────────────────────────

@cloud_router.post("/vpc-peerings", status_code=201)
def create_vpc_peering(peering: VPCPeering):
    _store().add_vpc_peering(peering)
    return peering.model_dump()


@cloud_router.get("/vpc-peerings")
def list_vpc_peerings():
    return _store().list_vpc_peerings()


# ── TransitGateway CRUD ──────────────────────────────────────────────

@cloud_router.post("/transit-gateways", status_code=201)
def create_transit_gateway(tgw: TransitGateway):
    _store().add_transit_gateway(tgw)
    return tgw.model_dump()


@cloud_router.get("/transit-gateways")
def list_transit_gateways():
    return _store().list_transit_gateways()


# ── VPNTunnel CRUD ───────────────────────────────────────────────────

@cloud_router.post("/vpn-tunnels", status_code=201)
def create_vpn_tunnel(vpn: VPNTunnel):
    _store().add_vpn_tunnel(vpn)
    return vpn.model_dump()


@cloud_router.get("/vpn-tunnels")
def list_vpn_tunnels():
    return _store().list_vpn_tunnels()


# ── DirectConnect CRUD ───────────────────────────────────────────────

@cloud_router.post("/direct-connects", status_code=201)
def create_direct_connect(dx: DirectConnect):
    _store().add_direct_connect(dx)
    return dx.model_dump()


@cloud_router.get("/direct-connects")
def list_direct_connects():
    return _store().list_direct_connects()
