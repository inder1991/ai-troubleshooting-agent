"""Tests for dispatch_router, domain agent wrapper, re-dispatch scope filtering,
and synthesizer SKIPPED exclusion (Task 5)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.agents.cluster.graph import (
    dispatch_router,
    _wrap_domain_agent,
    _should_redispatch,
    ALL_DOMAINS,
)
from src.agents.cluster.synthesizer import _compute_data_completeness
from src.agents.cluster.state import DiagnosticScope, DomainReport, DomainStatus


# ---------------------------------------------------------------------------
# Helper: build state with a DiagnosticScope
# ---------------------------------------------------------------------------

def _state_with_scope(**scope_kwargs) -> dict:
    """Return a minimal graph state dict containing a serialized DiagnosticScope."""
    scope = DiagnosticScope(**scope_kwargs)
    return {"diagnostic_scope": scope.model_dump(mode="json")}


# ===========================================================================
# dispatch_router — domain selection per scope level
# ===========================================================================


def test_dispatch_router_cluster_all_domains():
    """Cluster-level scope dispatches all 4 domains."""
    state = _state_with_scope(level="cluster")
    result = dispatch_router(state)
    assert set(result["dispatch_domains"]) == {"ctrl_plane", "node", "network", "storage"}
    assert result["scope_coverage"] == 1.0


def test_dispatch_router_namespace_with_ctrl_plane():
    """Namespace scope with include_control_plane=True keeps all domains."""
    state = _state_with_scope(level="namespace", namespaces=["prod"], include_control_plane=True)
    result = dispatch_router(state)
    assert "ctrl_plane" in result["dispatch_domains"]
    assert set(result["dispatch_domains"]) == {"ctrl_plane", "node", "network", "storage"}


def test_dispatch_router_namespace_without_ctrl_plane():
    """Namespace scope with include_control_plane=False removes ctrl_plane."""
    state = _state_with_scope(level="namespace", namespaces=["prod"], include_control_plane=False)
    result = dispatch_router(state)
    assert "ctrl_plane" not in result["dispatch_domains"]
    expected = {"node", "network", "storage"}
    assert set(result["dispatch_domains"]) == expected
    assert result["scope_coverage"] == len(expected) / len(ALL_DOMAINS)


def test_dispatch_router_workload_domains():
    """Workload scope limits to node + network (+ ctrl_plane if included)."""
    state = _state_with_scope(
        level="workload",
        namespaces=["prod"],
        workload_key="Deployment/my-app",
        include_control_plane=True,
    )
    result = dispatch_router(state)
    assert "node" in result["dispatch_domains"]
    assert "network" in result["dispatch_domains"]
    assert "ctrl_plane" in result["dispatch_domains"]
    # storage should NOT be included for workload scope
    assert "storage" not in result["dispatch_domains"]
    assert result["scope_coverage"] == 3 / 4


def test_dispatch_router_workload_no_ctrl_plane():
    """Workload scope without ctrl_plane includes only node + network."""
    state = _state_with_scope(
        level="workload",
        namespaces=["prod"],
        workload_key="Deployment/my-app",
        include_control_plane=False,
    )
    result = dispatch_router(state)
    assert set(result["dispatch_domains"]) == {"node", "network"}
    assert result["scope_coverage"] == 2 / 4


def test_dispatch_router_component_domains():
    """Component scope dispatches exactly the specified domains."""
    state = _state_with_scope(level="component", domains=["network"])
    result = dispatch_router(state)
    assert result["dispatch_domains"] == ["network"]
    assert result["scope_coverage"] == 1 / 4


def test_dispatch_router_scope_coverage_calculation():
    """Scope coverage is len(domains) / len(ALL_DOMAINS)."""
    state = _state_with_scope(level="component", domains=["node", "storage"])
    result = dispatch_router(state)
    assert result["scope_coverage"] == pytest.approx(2 / 4)

    state_full = _state_with_scope(level="cluster")
    result_full = dispatch_router(state_full)
    assert result_full["scope_coverage"] == pytest.approx(1.0)


def test_dispatch_router_no_scope_defaults_all():
    """When no diagnostic_scope is in state, dispatch all domains."""
    result = dispatch_router({})
    assert set(result["dispatch_domains"]) == set(ALL_DOMAINS)
    assert result["scope_coverage"] == 1.0


# ===========================================================================
# _wrap_domain_agent — SKIP / RUN behaviour
# ===========================================================================


@pytest.mark.asyncio
async def test_wrapped_agent_skips_inactive_domain():
    """Agent wrapper returns SKIPPED report when domain is not in dispatch_domains."""
    fake_agent = AsyncMock(return_value={"domain_reports": [{"domain": "storage", "status": "SUCCESS"}]})
    wrapped = _wrap_domain_agent("storage", fake_agent)

    state = {"dispatch_domains": ["node", "network"]}  # storage not included
    result = await wrapped(state, {})

    assert len(result["domain_reports"]) == 1
    report = result["domain_reports"][0]
    assert report["domain"] == "storage"
    assert report["status"] == "SKIPPED"
    assert report["confidence"] == 0
    assert report["anomalies"] == []
    assert report["duration_ms"] == 0
    fake_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrapped_agent_runs_active_domain():
    """Agent wrapper delegates to the real agent when domain is in dispatch_domains."""
    expected_result = {"domain_reports": [{"domain": "node", "status": "SUCCESS", "confidence": 85}]}
    fake_agent = AsyncMock(return_value=expected_result)
    wrapped = _wrap_domain_agent("node", fake_agent)

    state = {"dispatch_domains": ["node", "network", "ctrl_plane", "storage"]}
    result = await wrapped(state, {"configurable": {}})

    assert result == expected_result
    fake_agent.assert_awaited_once_with(state, {"configurable": {}})


@pytest.mark.asyncio
async def test_wrapped_agent_defaults_to_all_domains():
    """If dispatch_domains is missing from state, treat all domains as active."""
    expected = {"domain_reports": [{"domain": "ctrl_plane", "status": "SUCCESS"}]}
    fake_agent = AsyncMock(return_value=expected)
    wrapped = _wrap_domain_agent("ctrl_plane", fake_agent)

    result = await wrapped({}, {})
    assert result == expected
    fake_agent.assert_awaited_once()


# ===========================================================================
# _should_redispatch — respects dispatch_domains
# ===========================================================================


def test_redispatch_respects_dispatch_domains():
    """Only re-dispatches domains that are in the active dispatch set."""
    state = {
        "re_dispatch_domains": ["ctrl_plane", "storage"],
        "re_dispatch_count": 0,
        "dispatch_domains": ["node", "network", "storage"],  # ctrl_plane excluded
    }
    targets = _should_redispatch(state)
    # ctrl_plane should be filtered out; only storage re-dispatched
    assert "dispatch_storage" in targets
    assert "dispatch_ctrl_plane" not in targets


def test_redispatch_skipped_domain_not_redispatched():
    """If all re_dispatch_domains are outside dispatch_domains, go to guard_formatter."""
    state = {
        "re_dispatch_domains": ["ctrl_plane"],
        "re_dispatch_count": 0,
        "dispatch_domains": ["node", "network"],  # ctrl_plane not active
    }
    targets = _should_redispatch(state)
    assert targets == ["to_guard_formatter"]


def test_redispatch_no_redispatch_needed():
    """When re_dispatch_domains is empty, go directly to guard_formatter."""
    state = {
        "re_dispatch_domains": [],
        "re_dispatch_count": 0,
        "dispatch_domains": ["ctrl_plane", "node", "network", "storage"],
    }
    targets = _should_redispatch(state)
    assert targets == ["to_guard_formatter"]


def test_redispatch_count_exceeded():
    """When re_dispatch_count >= 1, skip re-dispatch regardless."""
    state = {
        "re_dispatch_domains": ["node", "network"],
        "re_dispatch_count": 1,
        "dispatch_domains": ["ctrl_plane", "node", "network", "storage"],
    }
    targets = _should_redispatch(state)
    assert targets == ["to_guard_formatter"]


# ===========================================================================
# synthesizer — _compute_data_completeness excludes SKIPPED
# ===========================================================================


def test_synthesizer_excludes_skipped():
    """SKIPPED reports should not count in data completeness calculation."""
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SKIPPED, confidence=0),
        DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=85),
        DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=80),
        DomainReport(domain="storage", status=DomainStatus.SKIPPED, confidence=0),
    ]
    score = _compute_data_completeness(reports)
    # 2 active (node=SUCCESS, network=SUCCESS), both completed => 2/2 = 1.0
    assert score == pytest.approx(1.0)


def test_synthesizer_all_skipped_returns_zero():
    """If all reports are SKIPPED, completeness is 0.0."""
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SKIPPED, confidence=0),
        DomainReport(domain="node", status=DomainStatus.SKIPPED, confidence=0),
    ]
    score = _compute_data_completeness(reports)
    assert score == 0.0


def test_synthesizer_mixed_active_statuses():
    """Active reports: 1 SUCCESS + 1 FAILED => completeness = 0.5."""
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SKIPPED, confidence=0),
        DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=85),
        DomainReport(domain="network", status=DomainStatus.FAILED, confidence=0),
        DomainReport(domain="storage", status=DomainStatus.SKIPPED, confidence=0),
    ]
    score = _compute_data_completeness(reports)
    # 2 active (node=SUCCESS, network=FAILED) => 1/2 = 0.5
    assert score == pytest.approx(0.5)
