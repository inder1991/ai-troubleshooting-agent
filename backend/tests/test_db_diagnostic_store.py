"""Tests for diagnostic run history store."""
import pytest
import os
import tempfile


@pytest.fixture
def store():
    from src.database.diagnostic_store import DiagnosticRunStore
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DiagnosticRunStore(db_path=path)
    yield s
    os.unlink(path)


class TestDiagnosticRunStore:
    def test_create_and_get(self, store):
        run = store.create(profile_id="p1")
        assert run["run_id"]
        assert run["status"] == "running"
        fetched = store.get(run["run_id"])
        assert fetched["profile_id"] == "p1"

    def test_update_status(self, store):
        run = store.create(profile_id="p1")
        store.update(run["run_id"], status="completed", summary="All good")
        fetched = store.get(run["run_id"])
        assert fetched["status"] == "completed"
        assert fetched["summary"] == "All good"

    def test_add_finding(self, store):
        run = store.create(profile_id="p1")
        store.add_finding(run["run_id"], {
            "finding_id": "f1", "category": "query_performance",
            "severity": "high", "confidence": 0.9,
            "title": "Slow query", "detail": "SELECT took 12s",
        })
        fetched = store.get(run["run_id"])
        assert len(fetched["findings"]) == 1
        assert fetched["findings"][0]["title"] == "Slow query"

    def test_list_by_profile(self, store):
        store.create(profile_id="p1")
        store.create(profile_id="p1")
        store.create(profile_id="p2")
        runs = store.list_by_profile("p1")
        assert len(runs) == 2

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None
