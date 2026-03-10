"""Tests for database diagnostics Pydantic models."""
import pytest
from datetime import datetime


def test_db_profile_creation():
    from src.database.models import DBProfile
    p = DBProfile(
        id="test-1", name="prod-pg", engine="postgresql",
        host="localhost", port=5432, database="mydb",
        username="admin", password="secret",
    )
    assert p.engine == "postgresql"
    assert p.port == 5432


def test_db_profile_invalid_engine():
    from src.database.models import DBProfile
    with pytest.raises(Exception):
        DBProfile(
            id="x", name="x", engine="redis",
            host="x", port=1, database="x",
            username="x", password="x",
        )


def test_diagnostic_run_defaults():
    from src.database.models import DiagnosticRun
    r = DiagnosticRun(run_id="r1", profile_id="p1")
    assert r.status == "running"
    assert r.findings == []
    assert r.summary == ""


def test_db_finding_fields():
    from src.database.models import DBFinding
    f = DBFinding(
        finding_id="f1", category="query_performance",
        severity="high", confidence=0.85,
        title="Slow query", detail="SELECT took 12s",
    )
    assert f.confidence == 0.85
    assert f.remediation_available is False


def test_perf_snapshot():
    from src.database.models import PerfSnapshot
    s = PerfSnapshot(
        connections_active=12, connections_idle=5, connections_max=100,
        cache_hit_ratio=0.94, transactions_per_sec=150.0,
        deadlocks=0, uptime_seconds=86400,
    )
    assert s.cache_hit_ratio == 0.94


def test_active_query():
    from src.database.models import ActiveQuery
    q = ActiveQuery(
        pid=1234, query="SELECT 1", duration_ms=500,
        state="active", user="admin", database="mydb",
    )
    assert q.pid == 1234


def test_replication_snapshot():
    from src.database.models import ReplicationSnapshot
    r = ReplicationSnapshot(
        is_replica=False, replicas=[], replication_lag_bytes=0,
    )
    assert r.is_replica is False


def test_query_plan_node_recursive():
    from src.database.models import QueryPlanNode
    node = QueryPlanNode(
        node_type="Seq Scan", relation="orders",
        children=[QueryPlanNode(node_type="Index Scan", relation="users")],
    )
    assert len(node.children) == 1
    assert node.children[0].node_type == "Index Scan"


def test_query_result_with_error():
    from src.database.models import QueryResult
    r = QueryResult(query="SELECT bad", error="syntax error")
    assert r.error == "syntax error"
    assert r.rows_returned == 0


def test_column_info():
    from src.database.models import ColumnInfo
    c = ColumnInfo(name="id", data_type="integer", nullable=False, is_pk=True)
    assert c.is_pk is True
    assert c.nullable is False


def test_index_info():
    from src.database.models import IndexInfo
    i = IndexInfo(name="pk_orders", columns=["id"], unique=True, size_bytes=8192)
    assert i.unique is True


def test_table_detail():
    from src.database.models import TableDetail, ColumnInfo, IndexInfo
    td = TableDetail(
        name="orders", schema_name="public",
        columns=[ColumnInfo(name="id", data_type="integer", nullable=False, is_pk=True)],
        indexes=[IndexInfo(name="pk_orders", columns=["id"], unique=True, size_bytes=8192)],
        row_estimate=120000, total_size_bytes=256000000, bloat_ratio=0.05,
    )
    assert td.row_estimate == 120000
    assert len(td.columns) == 1
    assert td.bloat_ratio == 0.05


def test_remediation_plan():
    from src.database.models import RemediationPlan
    p = RemediationPlan(
        plan_id="plan-1", profile_id="prof-1", action="vacuum",
        params={"table": "orders", "full": False},
        sql_preview="VACUUM ANALYZE orders",
        impact_assessment="~30s, no locks",
        status="pending", created_at="2026-03-09T00:00:00",
    )
    assert p.action == "vacuum"
    assert p.requires_downtime is False
    assert p.rollback_sql is None


def test_audit_log_entry():
    from src.database.models import AuditLogEntry
    e = AuditLogEntry(
        entry_id="aud-1", plan_id="plan-1", profile_id="prof-1",
        action="vacuum", sql_executed="VACUUM ANALYZE orders",
        status="success", timestamp="2026-03-09T00:00:00",
    )
    assert e.status == "success"
    assert e.error is None


def test_config_recommendation():
    from src.database.models import ConfigRecommendation
    r = ConfigRecommendation(
        param="shared_buffers", current_value="128MB",
        recommended_value="1GB", reason="25% of 4GB RAM",
    )
    assert r.requires_restart is False


# --- V2 Model Tests ---

def test_finding_v2_with_evidence():
    from src.database.models import DBFindingV2, EvidenceSnippet
    snippet = EvidenceSnippet(
        id="e-9001",
        summary="pg_stat_statements: total_time=1.47E6ms calls=820",
        artifact_id="art-9001",
    )
    finding = DBFindingV2(
        finding_id="f-0001",
        agent="query_analyst",
        category="slow_query",
        title="High p95 latency for SQL sha:0xabc",
        severity="high",
        confidence_raw=0.86,
        confidence_calibrated=0.78,
        detail="Query scanning 12M rows",
        evidence_ids=["e-9001"],
        evidence_snippets=[snippet],
        affected_entities={"database": "orders_db", "tables": ["orders"]},
        recommendation="Add covering index",
        remediation_available=True,
        remediation_plan_id="p-77",
        rule_check="index_suggested: explain.rows_estimated > 100000",
        meta={"sql_sha": "0xabc", "agent_version": "query_analyst-v2"},
    )
    assert finding.confidence_calibrated == 0.78
    assert finding.evidence_snippets[0].artifact_id == "art-9001"


def test_plan_v2_with_steps():
    from src.database.models import RemediationPlanV2, PlanStep
    step = PlanStep(
        step_id="s1",
        type="create_index",
        description="Create index on replica",
        command="CREATE INDEX CONCURRENTLY idx_orders_user ON orders (user_id);",
        run_target="replica1",
        estimated_time_minutes=8,
    )
    plan = RemediationPlanV2(
        plan_id="p-77",
        profile_id="prof-1",
        created_by="query_analyst",
        summary="Create index to reduce seq scans",
        scope={"type": "schema_change", "database": "orders_db"},
        steps=[step],
        prechecks=[{"id": "p1", "type": "replica_available", "required": True}],
        required_approvals=[{"role": "dba", "min_count": 1}],
        policy_tags=["safe-index", "no-downtime"],
        estimated_risk="low",
        immutable_hash="sha256:abc123",
    )
    assert plan.steps[0].run_target == "replica1"
    assert plan.estimated_risk == "low"
    assert plan.status == "created"


def test_finding_v2_rejects_invalid_severity():
    from src.database.models import DBFindingV2
    with pytest.raises(Exception):
        DBFindingV2(
            finding_id="f-bad",
            agent="test",
            category="slow_query",
            title="Bad",
            severity="mega_critical",
            confidence_raw=0.5,
            detail="test",
        )
