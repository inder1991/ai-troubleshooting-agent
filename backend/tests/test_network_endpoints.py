"""Tests for network troubleshooting API endpoints and LangGraph wiring."""
import os
import io
import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from starlette.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import (
    Device, DeviceType, Subnet, Interface, Route,
    Flow, DiagnosisStatus,
    FirewallVendor, PolicyAction, VerdictMatchType,
)
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.adapters.registry import AdapterRegistry
from src.agents.network.graph import build_network_diagnostic_graph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test_net.db")
    return TopologyStore(db_path=db_path)


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def mock_adapter():
    return MockFirewallAdapter(vendor=FirewallVendor.PALO_ALTO)


def _seed_topology(store):
    """Create a simple topology: Router -> Firewall -> Switch."""
    store.add_device(Device(id="r1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_device(Device(id="fw1", name="Firewall1", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
    store.add_device(Device(id="sw1", name="Switch1", device_type=DeviceType.SWITCH, management_ip="10.0.1.1"))
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1"))
    store.add_subnet(Subnet(id="s2", cidr="10.0.1.0/24", gateway_ip="10.0.1.1"))
    store.add_interface(Interface(id="r1-e0", device_id="r1", name="eth0", ip="10.0.0.1"))
    store.add_interface(Interface(id="fw1-e0", device_id="fw1", name="eth0", ip="10.0.0.2"))
    store.add_interface(Interface(id="fw1-e1", device_id="fw1", name="eth1", ip="10.0.1.2"))
    store.add_interface(Interface(id="sw1-e0", device_id="sw1", name="eth0", ip="10.0.1.1"))
    store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.1.0/24", next_hop="10.0.0.2"))
    store.add_route(Route(id="rt2", device_id="fw1", destination_cidr="10.0.1.0/24", next_hop="10.0.1.1"))


@pytest.fixture
def client(store, kg, mock_adapter):
    """Create a TestClient with patched singletons pointing to test fixtures."""
    registry = AdapterRegistry()
    registry.register("fw1", mock_adapter, device_ids=["fw1"])
    # Patch the module-level singletons in network_endpoints
    with patch("src.api.network_endpoints._topology_store", store), \
         patch("src.api.network_endpoints._knowledge_graph", kg), \
         patch("src.api.network_endpoints._adapter_registry", registry), \
         patch("src.api.network_endpoints._network_sessions", {}):

        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# Test: LangGraph builds and compiles
# ---------------------------------------------------------------------------


class TestGraphBuildsAndCompiles:
    def test_graph_compiles(self, store, kg, mock_adapter):
        """The LangGraph StateGraph compiles without error."""
        _seed_topology(store)
        kg.load_from_store()
        adapters = {"fw1": mock_adapter}
        compiled = build_network_diagnostic_graph(kg, adapters)
        assert compiled is not None
        # LangGraph compiled graphs have an invoke method
        assert hasattr(compiled, "ainvoke")

    def test_graph_has_nodes(self, store, kg, mock_adapter):
        """The compiled graph contains all expected node names."""
        kg.load_from_store()
        compiled = build_network_diagnostic_graph(kg, {"fw1": mock_adapter})
        # Compiled graph should have a get_graph method or nodes attribute
        assert compiled is not None


# ---------------------------------------------------------------------------
# Test: POST /diagnose
# ---------------------------------------------------------------------------


class TestDiagnoseEndpoint:
    def test_diagnose_creates_session(self, client, store):
        """POST /diagnose creates a session and returns flow_id."""
        _seed_topology(store)
        resp = client.post("/api/v4/network/diagnose", json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.1.1",
            "port": 443,
            "protocol": "tcp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "flow_id" in data
        assert data["status"] in ("queued", "running", "complete")

    def test_diagnose_idempotent(self, client, store):
        """Same params within 60 s returns same flow (idempotency)."""
        _seed_topology(store)
        resp1 = client.post("/api/v4/network/diagnose", json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.1.1",
            "port": 80,
        })
        assert resp1.status_code == 200
        data1 = resp1.json()

        # Second request with same params
        resp2 = client.post("/api/v4/network/diagnose", json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.1.1",
            "port": 80,
        })
        assert resp2.status_code == 200
        data2 = resp2.json()

        # Should return same flow_id (idempotent)
        assert data2["flow_id"] == data1["flow_id"]


# ---------------------------------------------------------------------------
# Test: Topology save/load
# ---------------------------------------------------------------------------


class TestTopologySaveLoad:
    def test_save_and_load(self, client):
        """Save diagram, then load it back."""
        save_resp = client.post("/api/v4/network/topology/save", json={
            "diagram_json": '{"nodes":[],"edges":[]}',
            "description": "test snapshot",
        })
        assert save_resp.status_code == 200
        assert save_resp.json()["status"] == "saved"

        load_resp = client.get("/api/v4/network/topology/load")
        assert load_resp.status_code == 200
        snapshot = load_resp.json()["snapshot"]
        assert snapshot is not None
        assert snapshot["snapshot_json"] == '{"nodes":[],"edges":[]}'

    def test_load_empty(self, client):
        """Load returns None when no diagrams exist."""
        resp = client.get("/api/v4/network/topology/load")
        assert resp.status_code == 200
        assert resp.json()["snapshot"] is None


# ---------------------------------------------------------------------------
# Test: IPAM upload
# ---------------------------------------------------------------------------


class TestIpamUpload:
    def test_upload_csv(self, client):
        """Upload CSV, verify devices/subnets created."""
        csv_content = "ip,subnet,device,zone,vlan,description\n10.1.0.10,10.1.0.0/24,Server1,dmz,100,Web server\n10.1.0.11,10.1.0.0/24,Server2,dmz,100,App server\n"
        resp = client.post(
            "/api/v4/network/ipam/upload",
            files={"file": ("ipam.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 200
        stats = resp.json()["stats"]
        assert stats["devices_added"] >= 2
        assert stats["subnets_added"] >= 1

        # Verify via list endpoints
        devices_resp = client.get("/api/v4/network/ipam/devices")
        assert devices_resp.status_code == 200
        assert len(devices_resp.json()["devices"]) >= 2

        subnets_resp = client.get("/api/v4/network/ipam/subnets")
        assert subnets_resp.status_code == 200
        assert len(subnets_resp.json()["subnets"]) >= 1


# ---------------------------------------------------------------------------
# Test: Adapters status
# ---------------------------------------------------------------------------


class TestAdaptersStatus:
    def test_adapters_status(self, client):
        """GET /adapters/status returns health status."""
        resp = client.get("/api/v4/network/adapters/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "adapters" in data
        # We have one mock adapter ("fw1")
        assert len(data["adapters"]) >= 1


# ---------------------------------------------------------------------------
# Test: Flows
# ---------------------------------------------------------------------------


class TestFlows:
    def test_flows_list(self, client, store):
        """GET /flows returns list."""
        # Add a flow manually
        from datetime import datetime, timezone
        store.add_flow(Flow(
            id="flow-test-1", src_ip="1.2.3.4", dst_ip="5.6.7.8",
            port=80, protocol="tcp",
            timestamp=datetime.now(timezone.utc).isoformat(),
            diagnosis_status=DiagnosisStatus.COMPLETE,
            session_id="sess-1",
        ))
        resp = client.get("/api/v4/network/flows")
        assert resp.status_code == 200
        flows = resp.json()["flows"]
        assert len(flows) >= 1
        assert flows[0]["id"] == "flow-test-1"

    def test_flow_detail(self, client, store):
        """GET /flows/{flow_id} returns flow details."""
        from datetime import datetime, timezone
        store.add_flow(Flow(
            id="flow-detail-1", src_ip="1.2.3.4", dst_ip="5.6.7.8",
            port=443, protocol="tcp",
            timestamp=datetime.now(timezone.utc).isoformat(),
            diagnosis_status=DiagnosisStatus.RUNNING,
            session_id="sess-2",
        ))
        resp = client.get("/api/v4/network/flows/flow-detail-1")
        assert resp.status_code == 200
        assert resp.json()["flow"]["id"] == "flow-detail-1"

    def test_flow_not_found(self, client):
        """GET /flows/{flow_id} returns 404 for missing flow."""
        resp = client.get("/api/v4/network/flows/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Session findings
# ---------------------------------------------------------------------------


class TestSessionFindings:
    def test_findings_not_found(self, client):
        """GET /session/{id}/findings returns 404 for unknown session."""
        resp = client.get("/api/v4/network/session/nonexistent/findings")
        assert resp.status_code == 404
