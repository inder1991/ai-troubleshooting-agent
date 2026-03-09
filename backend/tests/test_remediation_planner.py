"""Tests for AI remediation planner — findings → remediation plans."""
import os
import tempfile
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from src.database.remediation_store import RemediationStore
    from src.database.remediation_engine import RemediationEngine
    store = RemediationStore(db_path=path)
    e = RemediationEngine(
        plan_store=store,
        adapter_registry=MagicMock(),
        profile_store=MagicMock(),
        secret_key="test-key",
    )
    yield e
    os.unlink(path)


def test_planner_generates_vacuum_for_bloat(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f1", "category": "table_bloat", "severity": "medium",
            "title": "Table bloat detected", "detail": "orders has 35% bloat",
            "remediation_available": True,
            "evidence": ["orders: 35% bloat"],
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) >= 1
    assert any(p["action"] == "vacuum" for p in plans)


def test_planner_generates_index_for_slow_queries(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f2", "category": "slow_queries", "severity": "high",
            "title": "Slow queries detected", "detail": "Sequential scan on orders.customer_id",
            "remediation_available": True,
            "evidence": ["Seq Scan on orders filtering customer_id"],
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) >= 1
    assert any(p["action"] == "create_index" for p in plans)


def test_planner_generates_kill_for_deadlock(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f3", "category": "deadlocks", "severity": "high",
            "title": "Deadlocks detected", "detail": "PID 999 is blocking",
            "remediation_available": True,
            "evidence": ["blocking_pid: 999"],
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) >= 1
    assert any(p["action"] == "kill_query" for p in plans)


def test_planner_skips_non_remediable(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f4", "category": "info", "severity": "low",
            "title": "Database version", "detail": "PostgreSQL 16.1",
            "remediation_available": False,
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) == 0


def test_planner_graph_invocation(engine):
    from src.agents.database.remediation_planner import build_remediation_planner_graph
    graph = build_remediation_planner_graph()
    assert graph is not None
    state = {
        "profile_id": "prof-1",
        "findings": [
            {
                "finding_id": "f1", "category": "table_bloat", "severity": "medium",
                "title": "Bloat", "detail": "orders 35%", "remediation_available": True,
                "evidence": ["orders: 35% bloat"],
            }
        ],
        "plans": [],
        "_engine": engine,
    }
    result = graph.invoke(state)
    assert len(result.get("plans", [])) >= 1
