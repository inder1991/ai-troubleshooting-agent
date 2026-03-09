"""Tests for aggregate device metrics endpoint."""
import time
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import Device


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=str(tmp_path / "test.db"))


def test_aggregate_metrics_empty(store):
    result = store.aggregate_device_metrics([])
    assert result == {"avg_cpu": 0, "avg_mem": 0, "avg_temp": 0, "device_count": 0}


def test_aggregate_metrics_with_data(store):
    store.add_device(Device(id="d1", name="sw1", vendor="cisco", device_type="switch", management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="sw2", vendor="cisco", device_type="switch", management_ip="10.0.0.2"))
    now = time.time()
    store.add_metric_history("d1", now, {"cpu_pct": 40.0, "mem_pct": 60.0, "temperature": 35.0})
    store.add_metric_history("d2", now, {"cpu_pct": 60.0, "mem_pct": 80.0, "temperature": 45.0})

    result = store.aggregate_device_metrics(["d1", "d2"])
    assert result["avg_cpu"] == pytest.approx(50.0)
    assert result["avg_mem"] == pytest.approx(70.0)
    assert result["avg_temp"] == pytest.approx(40.0)
    assert result["device_count"] == 2


def test_aggregate_metrics_filters_by_device_ids(store):
    store.add_device(Device(id="d1", name="sw1", vendor="cisco", device_type="switch", management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="sw2", vendor="cisco", device_type="switch", management_ip="10.0.0.2"))
    now = time.time()
    store.add_metric_history("d1", now, {"cpu_pct": 80.0, "mem_pct": 90.0})
    store.add_metric_history("d2", now, {"cpu_pct": 20.0, "mem_pct": 30.0})

    result = store.aggregate_device_metrics(["d1"])
    assert result["avg_cpu"] == pytest.approx(80.0)
    assert result["device_count"] == 1
