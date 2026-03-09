"""Tests for InstanceStore SQLite persistence."""
import os
import tempfile
import pytest

from src.network.collectors.instance_store import InstanceStore
from src.network.collectors.models import (
    DeviceInstance, DeviceStatus, DiscoveryConfig, PingConfig,
    ProtocolConfig, SNMPCredentials, SNMPVersion,
)


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = InstanceStore(db_path=path)
    yield s
    os.unlink(path)


def _make_device(**kwargs) -> DeviceInstance:
    defaults = {
        "management_ip": "10.0.0.1",
        "hostname": "test-switch",
        "vendor": "cisco",
        "protocols": [ProtocolConfig(
            protocol="snmp", priority=5,
            snmp=SNMPCredentials(version=SNMPVersion.V2C, community="public"),
        )],
        "tags": ["env:test"],
        "ping_config": PingConfig(enabled=True),
    }
    defaults.update(kwargs)
    return DeviceInstance(**defaults)


def _make_config(**kwargs) -> DiscoveryConfig:
    defaults = {
        "cidr": "10.0.0.0/24",
        "community": "public",
    }
    defaults.update(kwargs)
    return DiscoveryConfig(**defaults)


class TestDeviceCRUD:
    def test_upsert_and_get(self, store):
        dev = _make_device()
        store.upsert_device(dev)
        fetched = store.get_device(dev.device_id)
        assert fetched is not None
        assert fetched.hostname == "test-switch"
        assert fetched.management_ip == "10.0.0.1"
        assert fetched.vendor == "cisco"

    def test_get_nonexistent(self, store):
        assert store.get_device("nonexistent") is None

    def test_get_by_ip(self, store):
        dev = _make_device()
        store.upsert_device(dev)
        fetched = store.get_device_by_ip("10.0.0.1")
        assert fetched is not None
        assert fetched.device_id == dev.device_id

    def test_list_devices(self, store):
        store.upsert_device(_make_device(management_ip="10.0.0.1"))
        store.upsert_device(_make_device(management_ip="10.0.0.2"))
        devices = store.list_devices()
        assert len(devices) == 2

    def test_upsert_updates_existing(self, store):
        dev = _make_device()
        store.upsert_device(dev)
        dev.hostname = "updated-switch"
        store.upsert_device(dev)
        fetched = store.get_device(dev.device_id)
        assert fetched.hostname == "updated-switch"
        assert len(store.list_devices()) == 1

    def test_delete_device(self, store):
        dev = _make_device()
        store.upsert_device(dev)
        assert store.delete_device(dev.device_id) is True
        assert store.get_device(dev.device_id) is None

    def test_delete_nonexistent(self, store):
        assert store.delete_device("nonexistent") is False

    def test_update_device_status(self, store):
        dev = _make_device()
        store.upsert_device(dev)
        store.update_device_status(dev.device_id, "up", 1234567890.0)
        fetched = store.get_device(dev.device_id)
        assert fetched.status == "up"
        assert fetched.last_collected == 1234567890.0

    def test_protocols_roundtrip(self, store):
        dev = _make_device()
        store.upsert_device(dev)
        fetched = store.get_device(dev.device_id)
        assert len(fetched.protocols) == 1
        assert fetched.protocols[0].protocol == "snmp"
        assert fetched.protocols[0].snmp.community == "public"

    def test_tags_roundtrip(self, store):
        dev = _make_device(tags=["env:prod", "site:dc1"])
        store.upsert_device(dev)
        fetched = store.get_device(dev.device_id)
        assert fetched.tags == ["env:prod", "site:dc1"]

    def test_ping_config_roundtrip(self, store):
        dev = _make_device(ping_config=PingConfig(enabled=True, count=8, timeout=5000))
        store.upsert_device(dev)
        fetched = store.get_device(dev.device_id)
        assert fetched.ping_config.count == 8
        assert fetched.ping_config.timeout == 5000

    def test_discovered_flag(self, store):
        dev = _make_device(discovered=True)
        store.upsert_device(dev)
        fetched = store.get_device(dev.device_id)
        assert fetched.discovered is True


class TestDiscoveryConfigCRUD:
    def test_upsert_and_get(self, store):
        cfg = _make_config()
        store.upsert_discovery_config(cfg)
        fetched = store.get_discovery_config(cfg.config_id)
        assert fetched is not None
        assert fetched.cidr == "10.0.0.0/24"
        assert fetched.community == "public"

    def test_list_configs(self, store):
        store.upsert_discovery_config(_make_config(cidr="10.0.0.0/24"))
        store.upsert_discovery_config(_make_config(cidr="192.168.1.0/24"))
        configs = store.list_discovery_configs()
        assert len(configs) == 2

    def test_delete_config(self, store):
        cfg = _make_config()
        store.upsert_discovery_config(cfg)
        assert store.delete_discovery_config(cfg.config_id) is True
        assert store.get_discovery_config(cfg.config_id) is None

    def test_upsert_updates_config(self, store):
        cfg = _make_config()
        store.upsert_discovery_config(cfg)
        cfg.interval_seconds = 600
        store.upsert_discovery_config(cfg)
        fetched = store.get_discovery_config(cfg.config_id)
        assert fetched.interval_seconds == 600

    def test_v3_creds_roundtrip(self, store):
        cfg = _make_config(
            snmp_version=SNMPVersion.V3,
            v3_user="monitor",
            v3_auth_protocol="SHA",
            v3_auth_key="authpass",
        )
        store.upsert_discovery_config(cfg)
        fetched = store.get_discovery_config(cfg.config_id)
        assert fetched.snmp_version == SNMPVersion.V3
        assert fetched.v3_user == "monitor"

    def test_excluded_ips_roundtrip(self, store):
        cfg = _make_config(excluded_ips=["10.0.0.1", "10.0.0.254"])
        store.upsert_discovery_config(cfg)
        fetched = store.get_discovery_config(cfg.config_id)
        assert fetched.excluded_ips == ["10.0.0.1", "10.0.0.254"]

    def test_tags_roundtrip(self, store):
        cfg = _make_config(tags=["site:dc1", "env:prod"])
        store.upsert_discovery_config(cfg)
        fetched = store.get_discovery_config(cfg.config_id)
        assert fetched.tags == ["site:dc1", "env:prod"]
