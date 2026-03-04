"""Tests for Network Observatory state store tables."""
import os
import pytest
from src.network.topology_store import TopologyStore


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


class TestDeviceStatus:
    def test_upsert_and_get(self, store):
        store.upsert_device_status("d1", "up", 2.5, 0.0, "icmp")
        result = store.get_device_status("d1")
        assert result is not None
        assert result["status"] == "up"
        assert result["latency_ms"] == 2.5

    def test_upsert_updates_existing(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        store.upsert_device_status("d1", "down", 0.0, 1.0, "icmp")
        result = store.get_device_status("d1")
        assert result["status"] == "down"
        assert result["packet_loss"] == 1.0

    def test_status_change_tracks_timestamp(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        first = store.get_device_status("d1")
        store.upsert_device_status("d1", "down", 0.0, 1.0, "icmp")
        second = store.get_device_status("d1")
        assert second["last_status_change"] != first["last_status_change"]

    def test_same_status_preserves_change_timestamp(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        first = store.get_device_status("d1")
        store.upsert_device_status("d1", "up", 3.0, 0.0, "icmp")
        second = store.get_device_status("d1")
        assert second["last_status_change"] == first["last_status_change"]

    def test_list_all(self, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        store.upsert_device_status("d2", "down", 0.0, 1.0, "tcp")
        results = store.list_device_statuses()
        assert len(results) == 2

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_device_status("nope") is None


class TestLinkMetrics:
    def test_upsert_and_list(self, store):
        store.upsert_link_metric("d1", "d2", 5.0, 1_000_000, 0.01, 0.45)
        results = store.list_link_metrics()
        assert len(results) == 1
        assert results[0]["latency_ms"] == 5.0
        assert results[0]["utilization"] == 0.45

    def test_upsert_updates(self, store):
        store.upsert_link_metric("d1", "d2", 5.0, 1_000_000, 0.01, 0.45)
        store.upsert_link_metric("d1", "d2", 10.0, 2_000_000, 0.02, 0.80)
        results = store.list_link_metrics()
        assert len(results) == 1
        assert results[0]["latency_ms"] == 10.0


class TestMetricHistory:
    def test_append_and_query(self, store):
        store.append_metric("device", "d1", "latency_ms", 2.5)
        store.append_metric("device", "d1", "latency_ms", 3.0)
        rows = store.query_metric_history("device", "d1", "latency_ms", since="2000-01-01")
        assert len(rows) == 2
        assert rows[0]["value"] == 2.5

    def test_prune_old_data(self, store):
        store.append_metric("device", "d1", "latency_ms", 2.5)
        # Manually backdate the row
        conn = store._conn()
        try:
            conn.execute("UPDATE metric_history SET recorded_at='2020-01-01T00:00:00'")
            conn.commit()
        finally:
            conn.close()
        store.prune_metric_history(older_than_days=1)
        rows = store.query_metric_history("device", "d1", "latency_ms", since="2000-01-01")
        assert len(rows) == 0


class TestDriftEvents:
    def test_upsert_and_list_active(self, store):
        store.upsert_drift_event("route", "rt1", "missing", "destination_cidr",
                                  "10.0.0.0/8", "(not present)", "critical")
        events = store.list_active_drift_events()
        assert len(events) == 1
        assert events[0]["drift_type"] == "missing"

    def test_resolve_removes_from_active(self, store):
        store.upsert_drift_event("route", "rt1", "missing", "destination_cidr",
                                  "10.0.0.0/8", "(not present)", "critical")
        events = store.list_active_drift_events()
        store.resolve_drift_event(events[0]["id"])
        assert len(store.list_active_drift_events()) == 0

    def test_unique_constraint_upserts(self, store):
        store.upsert_drift_event("route", "rt1", "missing", "next_hop",
                                  "10.0.0.1", "(not present)", "warning")
        store.upsert_drift_event("route", "rt1", "missing", "next_hop",
                                  "10.0.0.1", "(not present)", "critical")
        events = store.list_active_drift_events()
        assert len(events) == 1
        assert events[0]["severity"] == "critical"


class TestDiscoveryCandidates:
    def test_upsert_and_list(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "aa:bb:cc:dd:ee:ff",
                                          "printer-1", "probe", "")
        candidates = store.list_discovery_candidates()
        assert len(candidates) == 1
        assert candidates[0]["hostname"] == "printer-1"

    def test_promote(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "", "", "probe", "")
        store.promote_candidate("10.1.1.50", "device-printer")
        candidates = store.list_discovery_candidates()
        assert len(candidates) == 0  # promoted candidates are no longer listed

    def test_dismiss(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "", "", "probe", "")
        store.dismiss_candidate("10.1.1.50")
        candidates = store.list_discovery_candidates()
        assert len(candidates) == 0  # dismissed = hidden from list

    def test_dismissed_not_in_list(self, store):
        store.upsert_discovery_candidate("10.1.1.50", "", "", "probe", "")
        store.upsert_discovery_candidate("10.1.1.51", "", "", "probe", "")
        store.dismiss_candidate("10.1.1.50")
        candidates = store.list_discovery_candidates()
        assert len(candidates) == 1
        assert candidates[0]["ip"] == "10.1.1.51"
