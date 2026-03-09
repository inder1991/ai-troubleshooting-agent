"""Tests for EventStore — CRUD, time-range queries, retention pruning, batch insert."""
import os
import time
import pytest

from src.network.collectors.event_store import EventStore


@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test_events.db")
    return EventStore(db_path=db_path)


# ── Trap CRUD ──

def test_insert_and_query_trap(store):
    event = {
        "event_id": "t1",
        "device_ip": "10.0.0.1",
        "device_id": "dev-1",
        "oid": "1.3.6.1.6.3.1.1.5.3",
        "value": "ifIndex=2",
        "severity": "critical",
        "timestamp": time.time(),
        "raw_json": '{"test": true}',
    }
    store.insert_trap(event)

    results = store.query_traps()
    assert len(results) == 1
    assert results[0]["event_id"] == "t1"
    assert results[0]["severity"] == "critical"
    assert results[0]["oid"] == "1.3.6.1.6.3.1.1.5.3"


def test_insert_trap_batch(store):
    events = [
        {"event_id": f"t{i}", "device_ip": "10.0.0.1", "device_id": "dev-1",
         "oid": "1.2.3", "value": str(i), "severity": "info", "timestamp": time.time() + i}
        for i in range(10)
    ]
    store.insert_trap_batch(events)

    results = store.query_traps()
    assert len(results) == 10


def test_query_traps_filter_device(store):
    store.insert_trap({"event_id": "t1", "device_id": "dev-1", "severity": "info", "timestamp": time.time()})
    store.insert_trap({"event_id": "t2", "device_id": "dev-2", "severity": "info", "timestamp": time.time()})

    results = store.query_traps(device_id="dev-1")
    assert len(results) == 1
    assert results[0]["device_id"] == "dev-1"


def test_query_traps_filter_severity(store):
    store.insert_trap({"event_id": "t1", "severity": "critical", "timestamp": time.time()})
    store.insert_trap({"event_id": "t2", "severity": "info", "timestamp": time.time()})

    results = store.query_traps(severity="critical")
    assert len(results) == 1
    assert results[0]["severity"] == "critical"


def test_query_traps_filter_oid(store):
    store.insert_trap({"event_id": "t1", "oid": "1.2.3", "severity": "info", "timestamp": time.time()})
    store.insert_trap({"event_id": "t2", "oid": "4.5.6", "severity": "info", "timestamp": time.time()})

    results = store.query_traps(oid="1.2.3")
    assert len(results) == 1


def test_query_traps_time_range(store):
    now = time.time()
    store.insert_trap({"event_id": "t1", "severity": "info", "timestamp": now - 100})
    store.insert_trap({"event_id": "t2", "severity": "info", "timestamp": now})

    results = store.query_traps(time_from=now - 50)
    assert len(results) == 1
    assert results[0]["event_id"] == "t2"


def test_query_traps_limit(store):
    for i in range(20):
        store.insert_trap({"event_id": f"t{i}", "severity": "info", "timestamp": time.time() + i})

    results = store.query_traps(limit=5)
    assert len(results) == 5


# ── Syslog CRUD ──

def test_insert_and_query_syslog(store):
    event = {
        "event_id": "s1",
        "device_ip": "10.0.0.1",
        "device_id": "dev-1",
        "facility": "kern",
        "severity": "error",
        "hostname": "switch-01",
        "app_name": "kernel",
        "message": "Interface eth0 down",
        "timestamp": time.time(),
    }
    store.insert_syslog(event)

    results = store.query_syslog()
    assert len(results) == 1
    assert results[0]["event_id"] == "s1"
    assert results[0]["facility"] == "kern"
    assert results[0]["message"] == "Interface eth0 down"


def test_insert_syslog_batch(store):
    events = [
        {"event_id": f"s{i}", "facility": "daemon", "severity": "info",
         "hostname": "host-1", "app_name": "app", "message": f"msg {i}",
         "timestamp": time.time() + i}
        for i in range(15)
    ]
    store.insert_syslog_batch(events)

    results = store.query_syslog()
    assert len(results) == 15


def test_query_syslog_filter_severity(store):
    store.insert_syslog({"event_id": "s1", "severity": "error", "facility": "kern", "timestamp": time.time()})
    store.insert_syslog({"event_id": "s2", "severity": "info", "facility": "kern", "timestamp": time.time()})

    results = store.query_syslog(severity="error")
    assert len(results) == 1


def test_query_syslog_filter_facility(store):
    store.insert_syslog({"event_id": "s1", "severity": "info", "facility": "kern", "timestamp": time.time()})
    store.insert_syslog({"event_id": "s2", "severity": "info", "facility": "auth", "timestamp": time.time()})

    results = store.query_syslog(facility="auth")
    assert len(results) == 1
    assert results[0]["facility"] == "auth"


def test_query_syslog_search(store):
    store.insert_syslog({"event_id": "s1", "severity": "info", "message": "interface eth0 up", "timestamp": time.time()})
    store.insert_syslog({"event_id": "s2", "severity": "info", "message": "disk space low", "timestamp": time.time()})

    results = store.query_syslog(search="eth0")
    assert len(results) == 1
    assert "eth0" in results[0]["message"]


# ── Summaries ──

def test_trap_summary(store):
    store.insert_trap({"event_id": "t1", "oid": "1.2.3", "severity": "critical", "timestamp": time.time()})
    store.insert_trap({"event_id": "t2", "oid": "1.2.3", "severity": "critical", "timestamp": time.time()})
    store.insert_trap({"event_id": "t3", "oid": "4.5.6", "severity": "info", "timestamp": time.time()})

    summary = store.trap_summary()
    assert summary["counts_by_severity"]["critical"] == 2
    assert summary["counts_by_severity"]["info"] == 1
    assert len(summary["top_oids"]) == 2
    assert summary["top_oids"][0]["oid"] == "1.2.3"  # most frequent
    assert summary["top_oids"][0]["count"] == 2


def test_syslog_summary(store):
    store.insert_syslog({"event_id": "s1", "severity": "error", "facility": "kern", "timestamp": time.time()})
    store.insert_syslog({"event_id": "s2", "severity": "error", "facility": "auth", "timestamp": time.time()})
    store.insert_syslog({"event_id": "s3", "severity": "info", "facility": "kern", "timestamp": time.time()})

    summary = store.syslog_summary()
    assert summary["counts_by_severity"]["error"] == 2
    assert summary["counts_by_severity"]["info"] == 1
    assert summary["counts_by_facility"]["kern"] == 2
    assert summary["counts_by_facility"]["auth"] == 1


# ── Retention Pruning ──

def test_prune_old_events(store):
    now = time.time()
    old_time = now - (31 * 86400)  # 31 days ago

    store.insert_trap({"event_id": "old1", "severity": "info", "timestamp": old_time})
    store.insert_trap({"event_id": "new1", "severity": "info", "timestamp": now})
    store.insert_syslog({"event_id": "old2", "severity": "info", "facility": "kern", "timestamp": old_time})
    store.insert_syslog({"event_id": "new2", "severity": "info", "facility": "kern", "timestamp": now})

    result = store.prune_old_events(days=30)
    assert result["traps_deleted"] == 1
    assert result["syslog_deleted"] == 1

    assert len(store.query_traps()) == 1
    assert len(store.query_syslog()) == 1


def test_prune_no_old_events(store):
    store.insert_trap({"event_id": "t1", "severity": "info", "timestamp": time.time()})
    result = store.prune_old_events(days=30)
    assert result["traps_deleted"] == 0
    assert result["syslog_deleted"] == 0
