"""Tests for TTL-based in-memory caching in TopologyStore."""
import os
import pytest

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType, Interface


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test_cache.db")
    return TopologyStore(db_path=db_path)


def _make_device(dev_id: str = "r1", name: str = "Router1") -> Device:
    return Device(
        id=dev_id, name=name, device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
    )


def _make_interface(iface_id: str = "r1-e0", device_id: str = "r1") -> Interface:
    return Interface(
        id=iface_id, device_id=device_id, name="eth0", ip="10.0.0.1",
    )


# ---------------------------------------------------------------------------
# list_devices caching
# ---------------------------------------------------------------------------

class TestListDevicesCache:
    def test_consecutive_calls_return_same_object(self, store):
        """list_devices() should return the exact same cached object on repeat calls."""
        store.add_device(_make_device())
        result1 = store.list_devices()
        result2 = store.list_devices()
        assert result1 is result2

    def test_cache_invalidated_on_add_device(self, store):
        """Adding a device invalidates the list_devices cache."""
        store.add_device(_make_device("r1"))
        result1 = store.list_devices()
        assert len(result1) == 1

        store.add_device(_make_device("r2", "Router2"))
        result2 = store.list_devices()
        assert len(result2) == 2
        assert result1 is not result2

    def test_cache_invalidated_on_delete_device(self, store):
        """Deleting a device invalidates the list_devices cache."""
        store.add_device(_make_device("r1"))
        result1 = store.list_devices()

        store.delete_device("r1")
        result2 = store.list_devices()
        assert result1 is not result2
        assert len(result2) == 0

    def test_cache_invalidated_on_update_device(self, store):
        """Updating a device invalidates the list_devices cache."""
        store.add_device(_make_device("r1"))
        result1 = store.list_devices()

        store.update_device("r1", name="UpdatedRouter")
        result2 = store.list_devices()
        assert result1 is not result2


# ---------------------------------------------------------------------------
# list_interfaces caching
# ---------------------------------------------------------------------------

class TestListInterfacesCache:
    def test_consecutive_calls_return_same_object(self, store):
        """list_interfaces(device_id) returns the cached object on repeat calls."""
        store.add_device(_make_device("r1"))
        store.add_interface(_make_interface("r1-e0", "r1"))
        result1 = store.list_interfaces("r1")
        result2 = store.list_interfaces("r1")
        assert result1 is result2

    def test_different_device_ids_cached_separately(self, store):
        """Each device_id gets its own cache entry."""
        store.add_device(_make_device("r1"))
        store.add_device(_make_device("r2", "Router2"))
        store.add_interface(_make_interface("r1-e0", "r1"))
        store.add_interface(_make_interface("r2-e0", "r2"))

        r1_ifaces = store.list_interfaces("r1")
        r2_ifaces = store.list_interfaces("r2")
        assert r1_ifaces is not r2_ifaces
        assert len(r1_ifaces) == 1
        assert len(r2_ifaces) == 1

    def test_cache_invalidated_on_add_interface(self, store):
        """Adding an interface invalidates the cache for that device."""
        store.add_device(_make_device("r1"))
        store.add_interface(_make_interface("r1-e0", "r1"))
        result1 = store.list_interfaces("r1")
        assert len(result1) == 1

        store.add_interface(Interface(
            id="r1-e1", device_id="r1", name="eth1", ip="10.0.0.2",
        ))
        result2 = store.list_interfaces("r1")
        assert len(result2) == 2
        assert result1 is not result2

    def test_cache_invalidated_on_delete_interface(self, store):
        """Deleting an interface invalidates the cache for that device."""
        store.add_device(_make_device("r1"))
        store.add_interface(_make_interface("r1-e0", "r1"))
        result1 = store.list_interfaces("r1")

        store.delete_interface("r1-e0")
        result2 = store.list_interfaces("r1")
        assert result1 is not result2
        assert len(result2) == 0


# ---------------------------------------------------------------------------
# list_device_statuses caching
# ---------------------------------------------------------------------------

class TestListDeviceStatusesCache:
    def test_consecutive_calls_return_same_object(self, store):
        """list_device_statuses() returns the cached object on repeat calls."""
        store.add_device(_make_device("r1"))
        store.upsert_device_status("r1", "up", 5.0, 0.0, "icmp")
        result1 = store.list_device_statuses()
        result2 = store.list_device_statuses()
        assert result1 is result2

    def test_cache_invalidated_on_upsert_device_status(self, store):
        """Upserting a device status invalidates the cache."""
        store.add_device(_make_device("r1"))
        store.upsert_device_status("r1", "up", 5.0, 0.0, "icmp")
        result1 = store.list_device_statuses()
        assert len(result1) == 1

        store.upsert_device_status("r1", "down", 999.0, 100.0, "icmp")
        result2 = store.list_device_statuses()
        assert result1 is not result2
        assert result2[0]["status"] == "down"
