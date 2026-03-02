"""Tests for IPAM ingestion."""
import os
import pytest
from src.network.ipam_ingestion import parse_ipam_csv
from src.network.topology_store import TopologyStore


@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    return TopologyStore(db_path=db_path)


class TestIPAMIngestion:
    def test_basic_csv(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,Core router
10.0.0.2,10.0.0.0/24,Switch1,trust,100,Access switch
10.0.1.1,10.0.1.0/24,Firewall1,dmz,200,DMZ firewall"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["devices_added"] == 3
        assert stats["subnets_added"] == 2
        assert stats["interfaces_added"] == 3
        assert len(stats["errors"]) == 0

    def test_dedup_devices(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,
10.0.0.2,10.0.0.0/24,Router1,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["devices_added"] == 1
        assert stats["interfaces_added"] == 2

    def test_dedup_subnets(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,
10.0.0.2,10.0.0.0/24,Switch1,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["subnets_added"] == 1

    def test_empty_rows_skipped(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
,,,,,,
10.0.0.1,10.0.0.0/24,Router1,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["devices_added"] == 1

    def test_missing_device_no_interface(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["subnets_added"] == 1
        assert stats["devices_added"] == 0
        assert stats["interfaces_added"] == 0

    def test_data_persisted(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,Core"""
        parse_ipam_csv(csv_content, store)
        devices = store.list_devices()
        assert len(devices) == 1
        assert devices[0].name == "Router1"
        subnets = store.list_subnets()
        assert len(subnets) == 1
        interfaces = store.list_interfaces()
        assert len(interfaces) == 1
        assert interfaces[0].ip == "10.0.0.1"
