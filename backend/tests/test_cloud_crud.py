"""Tests for cloud & connectivity resource CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))

    # Seed VPCs so RouteTable FK constraints are satisfied
    from src.network.models import VPC
    store.add_vpc(VPC(id="vpc-1", name="seed-vpc-1", region="us-east-1"))
    store.add_vpc(VPC(id="vpc-2", name="seed-vpc-2", region="us-west-2"))

    from src.api.main import app
    from src.api import cloud_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


# ── VPC CRUD ──────────────────────────────────────────────────────────


class TestVPCCRUD:
    def test_create_vpc(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/vpcs", json={
            "id": "vpc-1",
            "name": "prod-vpc",
            "cloud_provider": "aws",
            "region": "us-east-1",
            "cidr_blocks": ["10.0.0.0/16"],
            "account_id": "123456789012",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "vpc-1"
        assert data["name"] == "prod-vpc"
        assert data["cidr_blocks"] == ["10.0.0.0/16"]

    def test_list_vpcs(self, store_and_client):
        _, client = store_and_client
        # Two VPCs are seeded in the fixture
        resp = client.get("/api/v4/network/cloud/vpcs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2


# ── RouteTable CRUD ──────────────────────────────────────────────────


class TestRouteTableCRUD:
    def test_create_route_table(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/route-tables", json={
            "id": "rtb-1",
            "vpc_id": "vpc-1",
            "name": "main-rt",
            "is_main": True,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "rtb-1"
        assert data["vpc_id"] == "vpc-1"
        assert data["is_main"] is True

    def test_list_route_tables(self, store_and_client):
        store, client = store_and_client
        from src.network.models import RouteTable
        store.add_route_table(RouteTable(id="rtb-1", vpc_id="vpc-1", name="main"))
        store.add_route_table(RouteTable(id="rtb-2", vpc_id="vpc-2", name="custom"))
        resp = client.get("/api/v4/network/cloud/route-tables")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_route_tables_filter_by_vpc(self, store_and_client):
        store, client = store_and_client
        from src.network.models import RouteTable
        store.add_route_table(RouteTable(id="rtb-1", vpc_id="vpc-1", name="main"))
        store.add_route_table(RouteTable(id="rtb-2", vpc_id="vpc-2", name="custom"))
        resp = client.get("/api/v4/network/cloud/route-tables?vpc_id=vpc-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["vpc_id"] == "vpc-1"


# ── VPCPeering CRUD ──────────────────────────────────────────────────


class TestVPCPeeringCRUD:
    def test_create_vpc_peering(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/vpc-peerings", json={
            "id": "pcx-1",
            "requester_vpc_id": "vpc-1",
            "accepter_vpc_id": "vpc-2",
            "status": "active",
            "cidr_routes": ["10.0.0.0/16", "10.1.0.0/16"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "pcx-1"
        assert data["requester_vpc_id"] == "vpc-1"
        assert data["accepter_vpc_id"] == "vpc-2"

    def test_list_vpc_peerings(self, store_and_client):
        store, client = store_and_client
        from src.network.models import VPCPeering
        store.add_vpc_peering(VPCPeering(
            id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2",
        ))
        resp = client.get("/api/v4/network/cloud/vpc-peerings")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ── TransitGateway CRUD ──────────────────────────────────────────────


class TestTransitGatewayCRUD:
    def test_create_transit_gateway(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/transit-gateways", json={
            "id": "tgw-1",
            "name": "central-tgw",
            "cloud_provider": "aws",
            "region": "us-east-1",
            "attached_vpc_ids": ["vpc-1", "vpc-2"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "tgw-1"
        assert data["name"] == "central-tgw"
        assert data["attached_vpc_ids"] == ["vpc-1", "vpc-2"]

    def test_list_transit_gateways(self, store_and_client):
        store, client = store_and_client
        from src.network.models import TransitGateway
        store.add_transit_gateway(TransitGateway(id="tgw-1", name="central-tgw"))
        resp = client.get("/api/v4/network/cloud/transit-gateways")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ── VPNTunnel CRUD ───────────────────────────────────────────────────


class TestVPNTunnelCRUD:
    def test_create_vpn_tunnel(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/vpn-tunnels", json={
            "id": "vpn-1",
            "name": "site-to-cloud",
            "tunnel_type": "ipsec",
            "local_gateway_id": "gw-1",
            "remote_gateway_ip": "203.0.113.1",
            "local_cidrs": ["10.0.0.0/16"],
            "remote_cidrs": ["172.16.0.0/12"],
            "encryption": "AES-256-GCM",
            "ike_version": "IKEv2",
            "status": "up",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "vpn-1"
        assert data["tunnel_type"] == "ipsec"
        assert data["local_cidrs"] == ["10.0.0.0/16"]

    def test_list_vpn_tunnels(self, store_and_client):
        store, client = store_and_client
        from src.network.models import VPNTunnel
        store.add_vpn_tunnel(VPNTunnel(id="vpn-1", name="site-to-cloud"))
        resp = client.get("/api/v4/network/cloud/vpn-tunnels")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ── DirectConnect CRUD ───────────────────────────────────────────────


class TestDirectConnectCRUD:
    def test_create_direct_connect(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/direct-connects", json={
            "id": "dx-1",
            "name": "dc-primary",
            "provider": "aws_dx",
            "bandwidth_mbps": 10000,
            "location": "Equinix DC6",
            "vlan_id": 100,
            "bgp_asn": 65000,
            "status": "up",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "dx-1"
        assert data["bandwidth_mbps"] == 10000
        assert data["provider"] == "aws_dx"

    def test_list_direct_connects(self, store_and_client):
        store, client = store_and_client
        from src.network.models import DirectConnect
        store.add_direct_connect(DirectConnect(id="dx-1", name="dc-primary"))
        resp = client.get("/api/v4/network/cloud/direct-connects")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
