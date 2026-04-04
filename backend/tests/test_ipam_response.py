"""Tests for IPAM upload response contract — Task 2.

Verifies that the response from IPAM import matches the frontend's
expected shape (IPAMUploadDialog.tsx:54-61): devices_imported,
subnets_imported, nodes, edges, and warnings.
"""
import os
import pytest
from src.network.ipam_ingestion import parse_ipam_csv
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph


@pytest.fixture
def tmp_store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    return TopologyStore(db_path=db_path)


def _build_response(csv_content: str, store: TopologyStore) -> dict:
    """Simulate the ipam_upload endpoint: parse CSV, reload KG, build response."""
    stats = parse_ipam_csv(csv_content, store)
    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()
    rf_graph = kg.export_react_flow_graph()
    return {
        "status": "imported",
        "stats": stats,
        "devices_imported": stats["devices_added"],
        "subnets_imported": stats["subnets_added"],
        "nodes": rf_graph["nodes"],
        "edges": rf_graph["edges"],
        "warnings": stats.get("errors", []),
    }


VALID_CSV = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,Core router
10.0.0.2,10.0.0.0/24,Switch1,trust,100,Access switch
10.0.1.1,10.0.1.0/24,Firewall1,dmz,200,DMZ firewall"""


class TestResponseHasDevicesImportedField:
    """test_response_has_devices_imported_field -- devices_imported matches count."""

    def test_response_has_devices_imported_field(self, tmp_store):
        data = _build_response(VALID_CSV, tmp_store)
        assert "devices_imported" in data
        assert data["devices_imported"] == 3
        assert "subnets_imported" in data
        assert data["subnets_imported"] == 2
        # Also confirm they match the stats dict
        assert data["devices_imported"] == data["stats"]["devices_added"]
        assert data["subnets_imported"] == data["stats"]["subnets_added"]


class TestResponseHasNodesAndEdges:
    """test_response_has_nodes_and_edges -- nodes and edges are lists."""

    def test_response_has_nodes_and_edges(self, tmp_store):
        data = _build_response(VALID_CSV, tmp_store)
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        # Should have at least 3 device nodes (Router1, Switch1, Firewall1)
        device_nodes = [n for n in data["nodes"] if n.get("type") == "device"]
        assert len(device_nodes) == 3
        # Edges are present only if neighbor links were discovered (may be 0 for IPAM-only import)
        assert isinstance(data["edges"], list)


class TestNodesHaveReactFlowShape:
    """test_nodes_have_react_flow_shape -- each node has id, type, position, data."""

    def test_nodes_have_react_flow_shape(self, tmp_store):
        data = _build_response(VALID_CSV, tmp_store)
        for node in data["nodes"]:
            assert "id" in node, f"Node missing 'id': {node}"
            assert "type" in node, f"Node missing 'type': {node}"
            assert "position" in node, f"Node missing 'position': {node}"
            assert "data" in node, f"Node missing 'data': {node}"
            # Position must have x and y
            assert "x" in node["position"], f"Position missing 'x': {node}"
            assert "y" in node["position"], f"Position missing 'y': {node}"
            # Data must have label — group/env-label nodes only have 'label', device nodes also have 'entityId'
            assert "label" in node["data"], f"Data missing 'label': {node}"
            if node.get("type") == "device":
                assert "entityId" in node["data"], f"Data missing 'entityId': {node}"


class TestEdgesHaveReactFlowShape:
    """test_edges_have_react_flow_shape -- each edge has id, source, target."""

    def test_edges_have_react_flow_shape(self, tmp_store):
        data = _build_response(VALID_CSV, tmp_store)
        for edge in data["edges"]:
            assert "id" in edge, f"Edge missing 'id': {edge}"
            assert "source" in edge, f"Edge missing 'source': {edge}"
            assert "target" in edge, f"Edge missing 'target': {edge}"


class TestWarningsSurfaced:
    """test_warnings_surfaced -- invalid rows appear in data['warnings']."""

    def test_warnings_surfaced(self, tmp_store):
        csv_with_errors = """ip,subnet,device,zone,vlan,description
999.999.999.999,10.0.0.0/24,BadDevice,trust,100,Invalid IP
10.0.0.1,not-a-cidr,Device1,trust,100,Bad CIDR
10.0.0.2,10.0.0.0/24,GoodDevice,trust,100,Valid"""
        data = _build_response(csv_with_errors, tmp_store)
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
        assert len(data["warnings"]) == 2
        # Check that the warnings contain useful info
        warning_text = " ".join(data["warnings"])
        assert "999.999.999.999" in warning_text
        assert "not-a-cidr" in warning_text
