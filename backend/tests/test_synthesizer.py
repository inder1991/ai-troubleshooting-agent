import pytest
from unittest.mock import AsyncMock, patch
from src.agents.cluster.synthesizer import synthesize, _merge_reports, _compute_data_completeness
from src.agents.cluster.state import (
    DomainReport, DomainStatus, DomainAnomaly, CausalChain, ClusterHealthReport,
)


def test_data_completeness_all_success():
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=80),
        DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=90),
        DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=85),
        DomainReport(domain="storage", status=DomainStatus.SUCCESS, confidence=70),
    ]
    score = _compute_data_completeness(reports)
    assert score == 1.0


def test_data_completeness_partial():
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=80),
        DomainReport(domain="node", status=DomainStatus.FAILED, confidence=0),
        DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=85),
        DomainReport(domain="storage", status=DomainStatus.FAILED, confidence=0),
    ]
    score = _compute_data_completeness(reports)
    assert score == 0.5


def test_merge_deduplicates():
    reports = [
        DomainReport(
            domain="node", status=DomainStatus.SUCCESS, confidence=80,
            anomalies=[DomainAnomaly(domain="node", anomaly_id="n-001", description="infra-node-03 NotReady", evidence_ref="ev-1")],
        ),
        DomainReport(
            domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=75,
            anomalies=[DomainAnomaly(domain="ctrl_plane", anomaly_id="cp-001", description="infra-node-03 NotReady", evidence_ref="ev-2")],
        ),
    ]
    merged = _merge_reports(reports)
    # Duplicate description should be deduplicated
    assert len(merged["all_anomalies"]) == 1


@pytest.mark.asyncio
async def test_synthesize_produces_health_report():
    state = {
        "diagnostic_id": "DIAG-TEST",
        "platform": "openshift",
        "platform_version": "4.14.2",
        "domain_reports": [
            DomainReport(domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=80,
                anomalies=[DomainAnomaly(domain="ctrl_plane", anomaly_id="cp-001", description="DNS operator degraded", evidence_ref="ev-1")],
            ).model_dump(mode="json"),
            DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=90,
                anomalies=[DomainAnomaly(domain="node", anomaly_id="n-001", description="disk 97%", evidence_ref="ev-2")],
            ).model_dump(mode="json"),
            DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=85).model_dump(mode="json"),
            DomainReport(domain="storage", status=DomainStatus.SUCCESS, confidence=70).model_dump(mode="json"),
        ],
        "causal_chains": [],
        "re_dispatch_count": 0,
    }

    with patch("src.agents.cluster.synthesizer._llm_causal_reasoning", new_callable=AsyncMock) as mock_causal:
        mock_causal.return_value = {
            "causal_chains": [{
                "chain_id": "cc-001", "confidence": 0.85,
                "root_cause": {"domain": "node", "anomaly_id": "n-001", "description": "disk 97%", "evidence_ref": "ev-2"},
                "cascading_effects": [],
            }],
            "uncorrelated_findings": [],
        }
        with patch("src.agents.cluster.synthesizer._llm_verdict", new_callable=AsyncMock) as mock_verdict:
            mock_verdict.return_value = {
                "platform_health": "DEGRADED",
                "blast_radius": {"summary": "1 node affected", "affected_namespaces": 1, "affected_pods": 5, "affected_nodes": 1},
                "remediation": {"immediate": [], "long_term": []},
                "re_dispatch_needed": False,
            }
            result = await synthesize(state, {"configurable": {}})

    assert "health_report" in result
    report = result["health_report"]
    assert report["platform_health"] == "DEGRADED"
    assert result["data_completeness"] == 1.0
