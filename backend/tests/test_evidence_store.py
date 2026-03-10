# backend/tests/test_evidence_store.py
import pytest
from src.database.evidence_store import EvidenceStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    return EvidenceStore(db_path)


def test_create_and_get_artifact(store):
    artifact = store.create(
        session_id="S-1",
        evidence_id="e-9001",
        source_agent="query_analyst",
        artifact_type="explain_plan",
        summary_json={"rows_estimated": 12000000, "scan_type": "Seq Scan"},
        full_content='{"Plan": {"Node Type": "Seq Scan", "Rows": 12000000}}',
        preview="Seq Scan on orders (rows=12M)",
    )
    assert artifact["artifact_id"].startswith("art-")
    assert artifact["source_agent"] == "query_analyst"

    fetched = store.get(artifact["artifact_id"])
    assert fetched is not None
    assert fetched["evidence_id"] == "e-9001"
    assert fetched["preview"] == "Seq Scan on orders (rows=12M)"


def test_list_by_session(store):
    store.create(session_id="S-1", evidence_id="e-1", source_agent="query_analyst",
                 artifact_type="pg_stat", summary_json={}, full_content="raw1", preview="p1")
    store.create(session_id="S-1", evidence_id="e-2", source_agent="health_analyst",
                 artifact_type="conn_pool", summary_json={}, full_content="raw2", preview="p2")
    store.create(session_id="S-2", evidence_id="e-3", source_agent="query_analyst",
                 artifact_type="pg_stat", summary_json={}, full_content="raw3", preview="p3")

    results = store.list_by_session("S-1")
    assert len(results) == 2


def test_get_nonexistent_returns_none(store):
    assert store.get("art-does-not-exist") is None
