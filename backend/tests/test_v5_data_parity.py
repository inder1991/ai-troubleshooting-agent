import pytest
from src.api.topology_v5 import build_topology_export
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import Device as PD, DeviceType, Interface as PI


@pytest.fixture
def repo(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    store.add_device(PD(
        id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1", vendor="cisco", model="ISR4451",
        role="core", site_id="dc-east", location="DC-East",
        os_version="IOS-XE 17.6", ha_role="active",
    ))
    store.add_interface(PI(
        id="rtr-01:Gi0/0", device_id="rtr-01", name="Gi0/0",
        ip="10.0.0.1", role="core", zone_id="zone-trust",
        oper_status="up", admin_status="up",
    ))
    return repo


def _first_device(result):
    """Return the first device node from the result (skip group/label nodes)."""
    return next(n for n in result["nodes"] if n.get("type") == "device")


class TestV5NodeParity:
    def test_node_has_label(self, repo):
        result = build_topology_export(repo)
        node = _first_device(result)
        assert "data" in node
        assert node["data"]["label"] == "rtr-01"

    def test_node_has_entity_id(self, repo):
        result = build_topology_export(repo)
        assert _first_device(result)["data"]["entityId"] == "rtr-01"

    def test_node_has_ip(self, repo):
        result = build_topology_export(repo)
        assert _first_device(result)["data"]["ip"] == "10.0.0.1"

    def test_node_has_role(self, repo):
        result = build_topology_export(repo)
        assert _first_device(result)["data"]["role"] == "core"

    def test_node_has_location(self, repo):
        result = build_topology_export(repo)
        assert _first_device(result)["data"]["location"] == "DC-East"

    def test_node_has_os_version(self, repo):
        result = build_topology_export(repo)
        assert _first_device(result)["data"]["osVersion"] == "IOS-XE 17.6"

    def test_node_has_interfaces(self, repo):
        result = build_topology_export(repo)
        ifaces = _first_device(result)["data"]["interfaces"]
        assert len(ifaces) >= 1
        assert ifaces[0]["name"] == "Gi0/0"
        assert ifaces[0]["ip"] == "10.0.0.1"

    def test_node_has_ha_role(self, repo):
        result = build_topology_export(repo)
        assert _first_device(result)["data"]["haRole"] == "active"

    def test_node_has_metric_placeholders(self, repo):
        result = build_topology_export(repo)
        data = _first_device(result)["data"]
        for key in ["cpuPct", "memoryPct", "sessionCount", "poolHealth", "bgpPeers"]:
            assert key in data


class TestV5EdgeParity:
    def test_edge_has_smoothstep_type(self, repo):
        repo._store.add_device(PD(
            id="sw-01", name="sw-01", device_type=DeviceType.SWITCH,
            management_ip="10.0.0.2", vendor="cisco",
        ))
        repo._store.upsert_neighbor_link(
            link_id="rtr-01:Gi0/0--sw-01:Gi0/48",
            device_id="rtr-01", local_interface="Gi0/0",
            remote_device="sw-01", remote_interface="Gi0/48",
            protocol="lldp", confidence=0.95,
        )
        result = build_topology_export(repo)
        matching = [e for e in result["edges"] if {e["source"], e["target"]} == {"rtr-01", "sw-01"}]
        assert len(matching) >= 1
        edge = matching[0]
        assert edge["type"] == "smoothstep"
        assert "style" in edge
        assert "stroke" in edge["style"]
        assert "data" in edge
        assert "edgeType" in edge["data"]

    def test_edge_has_label_style(self, repo):
        repo._store.add_device(PD(
            id="sw-01", name="sw-01", device_type=DeviceType.SWITCH,
            management_ip="10.0.0.2", vendor="cisco",
        ))
        repo._store.upsert_neighbor_link(
            link_id="l1", device_id="rtr-01", local_interface="Gi0/0",
            remote_device="sw-01", remote_interface="Gi0/48",
            protocol="lldp", confidence=0.95,
        )
        result = build_topology_export(repo)
        edge = [e for e in result["edges"] if "rtr-01" in (e["source"], e["target"])][0]
        assert "labelStyle" in edge
        assert "labelBgStyle" in edge
        assert "labelBgPadding" in edge
