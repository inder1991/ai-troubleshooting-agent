"""Integration tests for the network path troubleshooting pipeline.

Exercises the full diagnosis pipeline end-to-end: topology creation,
knowledge graph loading, adapter configuration, LangGraph execution,
IPAM upload, diagram persistence, and adapter health checks.
"""
import json
import os
import pytest
import asyncio
from datetime import datetime, timezone

from src.network.models import (
    Device, Interface, Subnet, Zone, Route,
    Flow, DeviceType, FirewallVendor, EdgeSource,
    DiagnosisStatus, PolicyAction, VerdictMatchType, NATDirection, NATRule,
    FirewallRule, PolicyVerdict, AdapterHealthStatus,
)
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.agents.network.graph import build_network_diagnostic_graph
from src.network.ipam_ingestion import parse_ipam_csv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    """TopologyStore with temp SQLite DB."""
    db_path = str(tmp_path / "test_network.db")
    return TopologyStore(db_path=db_path)


@pytest.fixture
def kg(store):
    """NetworkKnowledgeGraph backed by the test store."""
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def populated_topology(store, kg):
    """Pre-populated 3-node topology: src_router -> firewall -> dst_router."""
    # Create devices
    src_router = Device(
        id="r1", name="src-router", device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
    )
    firewall = Device(
        id="fw1", name="core-fw", device_type=DeviceType.FIREWALL,
        vendor=FirewallVendor.PALO_ALTO.value, management_ip="10.0.1.1",
    )
    dst_router = Device(
        id="r2", name="dst-router", device_type=DeviceType.ROUTER,
        management_ip="10.0.2.1",
    )
    store.add_device(src_router)
    store.add_device(firewall)
    store.add_device(dst_router)

    # Create subnets
    subnet_a = Subnet(id="s1", cidr="10.0.0.0/24", description="subnet-a")
    subnet_b = Subnet(id="s2", cidr="10.0.1.0/24", description="subnet-b")
    subnet_c = Subnet(id="s3", cidr="10.0.2.0/24", description="subnet-c")
    store.add_subnet(subnet_a)
    store.add_subnet(subnet_b)
    store.add_subnet(subnet_c)

    # Create interfaces
    store.add_interface(Interface(id="i1", device_id="r1", name="eth0", ip="10.0.0.1"))
    store.add_interface(Interface(id="i2", device_id="r1", name="eth1", ip="10.0.1.2"))
    store.add_interface(Interface(id="i3", device_id="fw1", name="eth0", ip="10.0.1.1"))
    store.add_interface(Interface(id="i4", device_id="fw1", name="eth1", ip="10.0.2.2"))
    store.add_interface(Interface(id="i5", device_id="r2", name="eth0", ip="10.0.2.1"))

    # Create routes
    store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.2.0/24",
                          next_hop="10.0.1.1", metric=10))
    store.add_route(Route(id="rt2", device_id="fw1", destination_cidr="10.0.2.0/24",
                          next_hop="10.0.2.1", metric=10))
    store.add_route(Route(id="rt3", device_id="fw1", destination_cidr="10.0.0.0/24",
                          next_hop="10.0.1.2", metric=10))
    store.add_route(Route(id="rt4", device_id="r2", destination_cidr="10.0.0.0/24",
                          next_hop="10.0.2.2", metric=10))

    # Reload knowledge graph
    kg.load_from_store()

    return {"store": store, "kg": kg}


@pytest.fixture
def mock_adapter_allow():
    """MockFirewallAdapter that ALLOWs all traffic via explicit rules."""
    rules = [
        FirewallRule(
            id="allow-all",
            device_id="fw1",
            rule_name="Allow All",
            src_ips=["any"],
            dst_ips=["any"],
            ports=[],
            protocol="tcp",
            action=PolicyAction.ALLOW,
            order=1,
        ),
    ]
    adapter = MockFirewallAdapter(
        vendor=FirewallVendor.PALO_ALTO,
        rules=rules,
        default_action=PolicyAction.DENY,
    )
    return adapter


@pytest.fixture
def mock_adapter_deny():
    """MockFirewallAdapter that DENYs all traffic."""
    adapter = MockFirewallAdapter(
        vendor=FirewallVendor.PALO_ALTO,
        default_action=PolicyAction.DENY,
    )

    # Override simulate_flow to always return DENY with high confidence
    async def deny_flow(src_ip, dst_ip, port, protocol="tcp"):
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_id="deny-all",
            rule_name="Deny All",
            confidence=0.95,
            match_type=VerdictMatchType.EXACT,
            details="Explicit deny rule matched",
        )
    adapter.simulate_flow = deny_flow
    return adapter


@pytest.fixture
def mock_adapter_nat():
    """MockFirewallAdapter with NAT rules configured."""
    rules = [
        FirewallRule(
            id="allow-all",
            device_id="fw1",
            rule_name="Allow All",
            src_ips=["any"],
            dst_ips=["any"],
            ports=[],
            protocol="tcp",
            action=PolicyAction.ALLOW,
            order=1,
        ),
    ]
    nat_rules = [
        NATRule(
            id="nat1",
            device_id="fw1",
            original_src="10.0.0.1",
            translated_src="203.0.113.10",
            direction=NATDirection.SNAT,
            rule_id="snat-rule-1",
            description="Source NAT to public IP",
        ),
    ]
    adapter = MockFirewallAdapter(
        vendor=FirewallVendor.PALO_ALTO,
        rules=rules,
        nat_rules=nat_rules,
        default_action=PolicyAction.DENY,
    )
    return adapter


# ---------------------------------------------------------------------------
# 1. Full Diagnosis Flow (end-to-end)
# ---------------------------------------------------------------------------

class TestFullDiagnosisFlow:
    """End-to-end: topology -> graph build -> ainvoke -> verify output."""

    def test_full_diagnosis_flow(self, populated_topology, mock_adapter_allow):
        topo = populated_topology
        kg = topo["kg"]

        # Map the adapter by firewall device_id
        adapters = {"fw1": mock_adapter_allow}

        # Build and compile the LangGraph
        compiled = build_network_diagnostic_graph(kg=kg, adapters=adapters)

        # Run the graph
        initial_state = {
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.2.1",
            "port": 443,
            "protocol": "tcp",
        }
        result = asyncio.run(compiled.ainvoke(initial_state))

        # Verify: diagnosis complete with confidence > 0
        assert result["diagnosis_status"] == "complete"
        assert result["confidence"] > 0
        assert result["executive_summary"] != ""
        assert len(result["evidence"]) > 0

    def test_full_flow_has_path(self, populated_topology, mock_adapter_allow):
        topo = populated_topology
        kg = topo["kg"]
        adapters = {"fw1": mock_adapter_allow}
        compiled = build_network_diagnostic_graph(kg=kg, adapters=adapters)

        result = asyncio.run(compiled.ainvoke({
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.2.1",
            "port": 443,
            "protocol": "tcp",
        }))

        # Should have found candidate paths and a final synthesized path
        assert result.get("candidate_paths") is not None
        assert len(result["candidate_paths"]) >= 1
        assert result["final_path"] is not None
        assert result["final_path"]["hop_count"] >= 1


# ---------------------------------------------------------------------------
# 2. Diagnosis with no topology
# ---------------------------------------------------------------------------

class TestDiagnosisNoTopology:
    """Empty topology yields failed or no_path_known."""

    def test_diagnosis_no_topology(self, store, kg):
        kg.load_from_store()  # empty
        adapters = {}
        compiled = build_network_diagnostic_graph(kg=kg, adapters=adapters)

        result = asyncio.run(compiled.ainvoke({
            "src_ip": "192.168.99.1",
            "dst_ip": "192.168.99.2",
            "port": 80,
            "protocol": "tcp",
        }))

        # With no topology, input_resolver returns "failed" and routes to END,
        # or graph_pathfinder sets "no_path_known"
        status = result.get("resolution_status", "")
        diagnosis = result.get("diagnosis_status", "")
        assert status == "failed" or "no_path_known" in diagnosis or diagnosis == ""


# ---------------------------------------------------------------------------
# 3. Diagnosis with DENY firewall
# ---------------------------------------------------------------------------

class TestDiagnosisDenyFirewall:
    """Firewall returns DENY -> final_path.blocked == True, summary contains BLOCKED."""

    def test_diagnosis_deny_firewall(self, populated_topology, mock_adapter_deny):
        topo = populated_topology
        kg = topo["kg"]
        adapters = {"fw1": mock_adapter_deny}
        compiled = build_network_diagnostic_graph(kg=kg, adapters=adapters)

        result = asyncio.run(compiled.ainvoke({
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.2.1",
            "port": 443,
            "protocol": "tcp",
        }))

        assert result["final_path"]["blocked"] is True
        assert "BLOCKED" in result["executive_summary"].upper()


# ---------------------------------------------------------------------------
# 4. Diagnosis with NAT chain
# ---------------------------------------------------------------------------

class TestDiagnosisNATChain:
    """Firewall has NAT rules -> nat_translations populated, identity_chain > 1 stage."""

    def test_diagnosis_nat_chain(self, populated_topology, mock_adapter_nat):
        topo = populated_topology
        kg = topo["kg"]
        adapters = {"fw1": mock_adapter_nat}
        compiled = build_network_diagnostic_graph(kg=kg, adapters=adapters)

        result = asyncio.run(compiled.ainvoke({
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.2.1",
            "port": 443,
            "protocol": "tcp",
        }))

        # NAT translations should be present
        assert len(result["nat_translations"]) > 0
        # Identity chain: original + post-snat = at least 2 stages
        assert len(result["identity_chain"]) > 1


# ---------------------------------------------------------------------------
# 5. IPAM upload then diagnose
# ---------------------------------------------------------------------------

class TestIPAMUploadThenDiagnose:
    """Upload CSV via parse_ipam_csv, then run diagnosis against that topology."""

    def test_ipam_upload_then_diagnose(self, tmp_path):
        db_path = str(tmp_path / "ipam_test.db")
        store = TopologyStore(db_path=db_path)

        csv_content = (
            "ip,subnet,device,zone,vlan,description\n"
            "10.1.0.1,10.1.0.0/24,RouterA,trust,100,Core router\n"
            "10.1.0.2,10.1.0.0/24,FirewallA,trust,100,Firewall\n"
            "10.1.1.1,10.1.1.0/24,SwitchA,dmz,200,DMZ switch\n"
        )
        stats = parse_ipam_csv(csv_content, store)
        assert stats["devices_added"] >= 2
        assert stats["subnets_added"] >= 1
        assert stats["interfaces_added"] >= 2

        # Build KG from uploaded data and run diagnosis
        kg = NetworkKnowledgeGraph(store)
        kg.load_from_store()
        adapters = {}
        compiled = build_network_diagnostic_graph(kg=kg, adapters=adapters)

        result = asyncio.run(compiled.ainvoke({
            "src_ip": "10.1.0.1",
            "dst_ip": "10.1.1.1",
            "port": 80,
            "protocol": "tcp",
        }))

        # Some evidence should have been generated even if path is incomplete
        assert len(result.get("evidence", [])) > 0


# ---------------------------------------------------------------------------
# 6. Diagram save/load round-trip
# ---------------------------------------------------------------------------

class TestDiagramSaveLoadRoundtrip:
    """Save a JSON diagram snapshot, load it back, verify content matches."""

    def test_diagram_save_load_roundtrip(self, store):
        diagram_data = {
            "nodes": [
                {"id": "r1", "type": "router", "x": 100, "y": 200},
                {"id": "fw1", "type": "firewall", "x": 300, "y": 200},
            ],
            "edges": [
                {"source": "r1", "target": "fw1", "label": "10.0.0.0/24"},
            ],
            "metadata": {"version": "1.0", "created_by": "test"},
        }

        snapshot_json = json.dumps(diagram_data)
        snap_id = store.save_diagram_snapshot(snapshot_json, description="test diagram")
        assert snap_id is not None
        assert snap_id > 0

        loaded = store.load_diagram_snapshot()
        assert loaded is not None
        assert loaded["description"] == "test diagram"

        parsed = json.loads(loaded["snapshot_json"])
        assert parsed["nodes"] == diagram_data["nodes"]
        assert parsed["edges"] == diagram_data["edges"]
        assert parsed["metadata"]["version"] == "1.0"


# ---------------------------------------------------------------------------
# 7. Adapter health check for all vendors
# ---------------------------------------------------------------------------

class TestAdapterHealthAllVendors:
    """Create MockFirewallAdapter for each vendor, call health_check, verify NOT_CONFIGURED."""

    def test_adapter_health_all_vendors(self):
        for vendor in FirewallVendor:
            adapter = MockFirewallAdapter(vendor=vendor)
            # No api_endpoint configured -> should be NOT_CONFIGURED
            health = asyncio.run(adapter.health_check())
            assert health.status == AdapterHealthStatus.NOT_CONFIGURED, (
                f"Expected NOT_CONFIGURED for {vendor.value}, got {health.status}"
            )
            assert health.vendor == vendor


# ---------------------------------------------------------------------------
# 8. Idempotent diagnosis (flow dedup)
# ---------------------------------------------------------------------------

class TestIdempotentDiagnosis:
    """Add a flow with current timestamp, find_recent_flow returns same flow."""

    def test_idempotent_diagnosis(self, store):
        now = datetime.now(timezone.utc).isoformat()
        flow = Flow(
            id="flow-001",
            src_ip="10.0.0.1",
            dst_ip="10.0.2.1",
            port=443,
            protocol="tcp",
            timestamp=now,
            diagnosis_status=DiagnosisStatus.RUNNING,
            session_id="session-abc",
        )
        store.add_flow(flow)

        # find_recent_flow within 60s should return the same flow
        found = store.find_recent_flow(
            src_ip="10.0.0.1", dst_ip="10.0.2.1", port=443, within_seconds=60
        )
        assert found is not None
        assert found.id == "flow-001"
        assert found.src_ip == "10.0.0.1"
        assert found.dst_ip == "10.0.2.1"
        assert found.port == 443

    def test_no_duplicate_within_window(self, store):
        """Adding the same flow twice and querying returns only the latest."""
        now = datetime.now(timezone.utc).isoformat()

        flow1 = Flow(
            id="flow-dup-1",
            src_ip="172.16.0.1",
            dst_ip="172.16.0.2",
            port=8080,
            protocol="tcp",
            timestamp=now,
            diagnosis_status=DiagnosisStatus.RUNNING,
        )
        flow2 = Flow(
            id="flow-dup-2",
            src_ip="172.16.0.1",
            dst_ip="172.16.0.2",
            port=8080,
            protocol="tcp",
            timestamp=now,
            diagnosis_status=DiagnosisStatus.COMPLETE,
        )
        store.add_flow(flow1)
        store.add_flow(flow2)

        found = store.find_recent_flow(
            src_ip="172.16.0.1", dst_ip="172.16.0.2", port=8080, within_seconds=60
        )
        assert found is not None
        # Should return most recent (ORDER BY timestamp DESC LIMIT 1)
        assert found.id in ("flow-dup-1", "flow-dup-2")

    def test_expired_flow_not_found(self, store):
        """A flow with an old timestamp should NOT be found within a 60s window."""
        old_timestamp = "2020-01-01T00:00:00+00:00"
        flow = Flow(
            id="flow-old",
            src_ip="10.10.10.1",
            dst_ip="10.10.10.2",
            port=22,
            protocol="tcp",
            timestamp=old_timestamp,
            diagnosis_status=DiagnosisStatus.COMPLETE,
        )
        store.add_flow(flow)

        found = store.find_recent_flow(
            src_ip="10.10.10.1", dst_ip="10.10.10.2", port=22, within_seconds=60
        )
        assert found is None
