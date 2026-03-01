"""Tests for enhanced synthesizer with root candidates and causal search space."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.cluster.state import (
    DomainAnomaly,
    DomainReport,
    DomainStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(causal_json: dict | None = None, verdict_json: dict | None = None):
    """Return a patched AnthropicClient that records prompts."""
    if causal_json is None:
        causal_json = {"causal_chains": [], "uncorrelated_findings": []}

    mock_client = MagicMock()

    # Each call returns a new response; first call is causal, second is verdict
    causal_response = MagicMock()
    causal_response.text = json.dumps(causal_json)

    mock_client.chat = AsyncMock(return_value=causal_response)
    return mock_client


def _sample_anomalies():
    return [
        DomainAnomaly(
            domain="compute",
            anomaly_id="a1",
            description="High CPU on worker-1",
            evidence_ref="ev-cpu-1",
            severity="high",
        ),
    ]


def _sample_reports():
    return [
        DomainReport(
            domain="compute",
            status=DomainStatus.SUCCESS,
            confidence=80,
            anomalies=_sample_anomalies(),
        ),
    ]


# ---------------------------------------------------------------------------
# Test 1: Root candidates appear in the LLM prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.agents.cluster.synthesizer.AnthropicClient")
async def test_root_candidates_in_prompt(mock_client_cls):
    mock_client = _make_mock_client()
    mock_client_cls.return_value = mock_client

    from src.agents.cluster.synthesizer import _llm_causal_reasoning

    root_candidates = [
        {"resource_key": "node/worker-1", "hypothesis": "Node NotReady", "confidence": 0.85},
        {"resource_key": "pod/api-server-xyz", "hypothesis": "OOMKilled", "confidence": 0.7},
    ]

    await _llm_causal_reasoning(
        _sample_anomalies(),
        _sample_reports(),
        root_candidates=root_candidates,
    )

    prompt = mock_client.chat.call_args.kwargs["prompt"]
    assert "Root Cause Hypothesis Seeds" in prompt
    assert "node/worker-1" in prompt
    assert "Node NotReady" in prompt
    assert "pod/api-server-xyz" in prompt
    assert "do NOT invent new root causes" in prompt


# ---------------------------------------------------------------------------
# Test 2: Annotated links appear in the LLM prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.agents.cluster.synthesizer.AnthropicClient")
async def test_annotated_links_in_prompt(mock_client_cls):
    mock_client = _make_mock_client()
    mock_client_cls.return_value = mock_client

    from src.agents.cluster.synthesizer import _llm_causal_reasoning

    search_space = {
        "annotated_links": [
            {
                "from_resource": "node/worker-1",
                "to_resource": "pod/api-server-xyz",
                "confidence_hint": 0.4,
                "reason": "temporal correlation weak",
            },
        ],
        "total_blocked": 0,
        "issue_clusters_summary": [],
    }

    await _llm_causal_reasoning(
        _sample_anomalies(),
        _sample_reports(),
        search_space=search_space,
    )

    prompt = mock_client.chat.call_args.kwargs["prompt"]
    assert "Annotated Links" in prompt
    assert "low confidence" in prompt.lower() or "low confidence" in prompt
    assert "node/worker-1" in prompt
    assert "temporal correlation weak" in prompt


# ---------------------------------------------------------------------------
# Test 3: Blocked link resource keys do NOT appear in the prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.agents.cluster.synthesizer.AnthropicClient")
async def test_blocked_links_excluded_from_prompt(mock_client_cls):
    mock_client = _make_mock_client()
    mock_client_cls.return_value = mock_client

    from src.agents.cluster.synthesizer import _llm_causal_reasoning

    search_space = {
        "annotated_links": [],
        "total_blocked": 5,
        "issue_clusters_summary": [],
    }
    # Provide root_candidates so the cluster_section is generated
    root_candidates = [
        {"resource_key": "node/worker-1", "hypothesis": "disk full", "confidence": 0.8},
    ]

    await _llm_causal_reasoning(
        _sample_anomalies(),
        _sample_reports(),
        search_space=search_space,
        root_candidates=root_candidates,
    )

    prompt = mock_client.chat.call_args.kwargs["prompt"]
    # The blocked count should appear
    assert "5 causal links were blocked" in prompt
    assert "do NOT propose these" in prompt.upper() or "do NOT propose these" in prompt

    # Specific blocked link resources should NOT be in the prompt
    # (we only pass the count, not the actual blocked link details)
    assert "blocked_resource_a" not in prompt
    assert "blocked_resource_b" not in prompt


# ---------------------------------------------------------------------------
# Test 4: execution_metadata includes firewall counts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execution_metadata_includes_firewall_counts():
    state = {
        "diagnostic_id": "DIAG-FW-TEST",
        "platform": "kubernetes",
        "platform_version": "1.28",
        "domain_reports": [
            DomainReport(
                domain="compute",
                status=DomainStatus.SUCCESS,
                confidence=80,
                anomalies=[
                    DomainAnomaly(
                        domain="compute",
                        anomaly_id="a1",
                        description="High CPU",
                        evidence_ref="ev-1",
                        severity="high",
                    ),
                ],
            ).model_dump(mode="json"),
        ],
        "issue_clusters": [
            {
                "cluster_id": "ic-001",
                "alerts": [],
                "root_candidates": [
                    {"resource_key": "node/w1", "hypothesis": "overloaded", "supporting_signals": [], "confidence": 0.9},
                ],
                "confidence": 0.8,
                "correlation_basis": ["temporal"],
                "affected_resources": ["node/w1"],
            },
        ],
        "causal_search_space": {
            "valid_links": [],
            "annotated_links": [
                {"from_resource": "a", "to_resource": "b", "confidence_hint": 0.3, "reason": "weak"},
                {"from_resource": "c", "to_resource": "d", "confidence_hint": 0.4, "reason": "marginal"},
            ],
            "blocked_links": [],
            "total_evaluated": 10,
            "total_blocked": 3,
            "total_annotated": 2,
        },
        "re_dispatch_count": 0,
    }

    with patch("src.agents.cluster.synthesizer._llm_causal_reasoning", new_callable=AsyncMock) as mock_causal:
        mock_causal.return_value = {
            "causal_chains": [],
            "uncorrelated_findings": [],
        }
        with patch("src.agents.cluster.synthesizer._llm_verdict", new_callable=AsyncMock) as mock_verdict:
            mock_verdict.return_value = {
                "platform_health": "DEGRADED",
                "blast_radius": {"summary": "test", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
                "remediation": {"immediate": [], "long_term": []},
                "re_dispatch_needed": False,
            }
            from src.agents.cluster.synthesizer import synthesize

            result = await synthesize(state, {"configurable": {}})

    report = result["health_report"]
    metadata = report["execution_metadata"]
    assert metadata["blocked_count"] == 3
    assert metadata["annotated_count"] == 2


# ---------------------------------------------------------------------------
# Test 5: synthesize passes search_space and root_candidates to _llm_causal_reasoning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_passes_search_space_to_causal_reasoning():
    state = {
        "diagnostic_id": "DIAG-PASS-TEST",
        "platform": "kubernetes",
        "platform_version": "1.28",
        "domain_reports": [
            DomainReport(
                domain="compute",
                status=DomainStatus.SUCCESS,
                confidence=80,
                anomalies=[
                    DomainAnomaly(
                        domain="compute",
                        anomaly_id="a1",
                        description="High CPU",
                        evidence_ref="ev-1",
                        severity="high",
                    ),
                ],
            ).model_dump(mode="json"),
        ],
        "issue_clusters": [
            {
                "cluster_id": "ic-001",
                "alerts": [],
                "root_candidates": [
                    {"resource_key": "node/w1", "hypothesis": "overloaded", "supporting_signals": [], "confidence": 0.9},
                ],
                "confidence": 0.8,
                "correlation_basis": ["temporal"],
                "affected_resources": ["node/w1"],
            },
        ],
        "causal_search_space": {
            "valid_links": [],
            "annotated_links": [{"from": "x", "to": "y", "confidence_hint": 0.3}],
            "blocked_links": [],
            "total_evaluated": 5,
            "total_blocked": 2,
            "total_annotated": 1,
        },
        "re_dispatch_count": 0,
    }

    with patch("src.agents.cluster.synthesizer._llm_causal_reasoning", new_callable=AsyncMock) as mock_causal:
        mock_causal.return_value = {"causal_chains": [], "uncorrelated_findings": []}
        with patch("src.agents.cluster.synthesizer._llm_verdict", new_callable=AsyncMock) as mock_verdict:
            mock_verdict.return_value = {
                "platform_health": "HEALTHY",
                "blast_radius": {"summary": "", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
                "remediation": {"immediate": [], "long_term": []},
                "re_dispatch_needed": False,
            }
            from src.agents.cluster.synthesizer import synthesize

            await synthesize(state, {"configurable": {}})

    # Verify _llm_causal_reasoning was called with search_space and root_candidates
    call_kwargs = mock_causal.call_args.kwargs
    assert "search_space" in call_kwargs
    assert "root_candidates" in call_kwargs

    # root_candidates should be extracted from issue_clusters
    root_cands = call_kwargs["root_candidates"]
    assert len(root_cands) == 1
    assert root_cands[0]["resource_key"] == "node/w1"

    # search_space should be the causal_search_space dict
    assert call_kwargs["search_space"]["total_blocked"] == 2


# ---------------------------------------------------------------------------
# Test 6: When no search_space/root_candidates, prompt is unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.agents.cluster.synthesizer.AnthropicClient")
async def test_no_cluster_data_prompt_unchanged(mock_client_cls):
    mock_client = _make_mock_client()
    mock_client_cls.return_value = mock_client

    from src.agents.cluster.synthesizer import _llm_causal_reasoning

    await _llm_causal_reasoning(
        _sample_anomalies(),
        _sample_reports(),
    )

    prompt = mock_client.chat.call_args.kwargs["prompt"]
    # Without cluster data, none of the new sections should appear
    assert "Root Cause Hypothesis Seeds" not in prompt
    assert "Annotated Links" not in prompt
    assert "Blocked Links" not in prompt
    assert "Pre-Correlated Issue Clusters" not in prompt


# ---------------------------------------------------------------------------
# Test 7: Issue clusters summary appears in prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.agents.cluster.synthesizer.AnthropicClient")
async def test_issue_clusters_summary_in_prompt(mock_client_cls):
    mock_client = _make_mock_client()
    mock_client_cls.return_value = mock_client

    from src.agents.cluster.synthesizer import _llm_causal_reasoning

    search_space = {
        "annotated_links": [],
        "total_blocked": 0,
        "issue_clusters_summary": [
            {
                "cluster_id": "ic-001",
                "affected_resources": ["node/w1", "pod/api-xyz"],
                "correlation_basis": ["temporal", "topological"],
                "confidence": 0.85,
            },
        ],
    }
    root_candidates = [
        {"resource_key": "node/w1", "hypothesis": "disk pressure", "confidence": 0.9},
    ]

    await _llm_causal_reasoning(
        _sample_anomalies(),
        _sample_reports(),
        search_space=search_space,
        root_candidates=root_candidates,
    )

    prompt = mock_client.chat.call_args.kwargs["prompt"]
    assert "Pre-Correlated Issue Clusters" in prompt
    assert "ic-001" in prompt
    assert "temporal" in prompt
