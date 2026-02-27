"""3-stage synthesis pipeline: Merge -> Causal Reasoning -> Verdict."""

from __future__ import annotations

import json
from typing import Any

from src.agents.cluster.state import (
    DomainReport, DomainStatus, DomainAnomaly, CausalChain, CausalLink,
    BlastRadius, ClusterHealthReport,
)
from src.agents.cluster.traced_node import traced_node
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

CONSTRAINED_LINK_TYPES = [
    "resource_exhaustion -> pod_eviction",
    "resource_exhaustion -> throttling",
    "pod_eviction -> service_degradation",
    "node_failure -> workload_rescheduling",
    "dns_failure -> api_unreachable",
    "certificate_expiry -> tls_handshake_failure",
    "config_drift -> unexpected_behavior",
    "storage_detach -> container_stuck",
    "network_partition -> split_brain",
    "api_latency -> timeout_cascade",
    "quota_exceeded -> scheduling_failure",
    "image_pull_failure -> pod_pending",
    "unknown",
]

CAUSAL_RULES = """
Six Causal Reasoning Rules:
1. TEMPORAL: A can only cause B if A started before B. Check timestamps.
2. MECHANISM: Must name HOW A caused B (link_type). "Same time" is correlation, not causation.
3. DOMAIN BOUNDARY: Explain the infrastructure mechanism for cross-domain links.
4. SINGLE ROOT: Each chain has exactly one root cause. Two independent roots = two chains.
5. WEAKEST LINK: Chain confidence = minimum of individual link confidences.
6. OBSERVABILITY CONFIRMATION: For cross-domain causality, require evidence in effect domain referencing cause resource.
"""


def _compute_data_completeness(reports: list[DomainReport]) -> float:
    """Fraction of domains that returned SUCCESS or PARTIAL."""
    if not reports:
        return 0.0
    succeeded = sum(1 for r in reports if r.status in (DomainStatus.SUCCESS, DomainStatus.PARTIAL))
    return succeeded / len(reports)


def _merge_reports(reports: list[DomainReport]) -> dict:
    """Stage 1: Deterministic merge and deduplication."""
    all_anomalies: list[DomainAnomaly] = []
    all_ruled_out: list[str] = []
    seen_descriptions: set[str] = set()

    for report in reports:
        for anomaly in report.anomalies:
            desc_key = anomaly.description.lower().strip()
            if desc_key not in seen_descriptions:
                seen_descriptions.add(desc_key)
                all_anomalies.append(anomaly)
        all_ruled_out.extend(report.ruled_out)

    return {
        "all_anomalies": all_anomalies,
        "all_ruled_out": list(set(all_ruled_out)),
    }


async def _llm_causal_reasoning(anomalies: list[DomainAnomaly], reports: list[DomainReport]) -> dict:
    """Stage 2: LLM identifies cross-domain causal chains."""
    client = AnthropicClient(agent_name="cluster_synthesizer")

    anomaly_data = [a.model_dump(mode="json") for a in anomalies]
    report_summaries = [
        {"domain": r.domain, "status": r.status.value, "confidence": r.confidence, "anomaly_count": len(r.anomalies)}
        for r in reports
    ]

    prompt = f"""Analyze these cross-domain anomalies and identify causal chains.

## Anomalies Found
{json.dumps(anomaly_data, indent=2)}

## Domain Report Summaries
{json.dumps(report_summaries, indent=2)}

## Allowed Link Types
{json.dumps(CONSTRAINED_LINK_TYPES)}

{CAUSAL_RULES}

## Required JSON Response
{{
  "causal_chains": [
    {{
      "chain_id": "cc-NNN",
      "confidence": 0.0-1.0,
      "root_cause": {{"domain": "...", "anomaly_id": "...", "description": "...", "evidence_ref": "..."}},
      "cascading_effects": [
        {{"order": 1, "domain": "...", "anomaly_id": "...", "description": "...", "link_type": "...", "evidence_ref": "..."}}
      ]
    }}
  ],
  "uncorrelated_findings": [
    {{"domain": "...", "anomaly_id": "...", "description": "...", "evidence_ref": "...", "severity": "..."}}
  ]
}}"""

    response = await client.chat(
        prompt=prompt,
        system="You are a causal reasoning engine for cluster diagnostics. Be precise and evidence-based.",
        max_tokens=3000,
        temperature=0.1,
    )
    text = response.text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"causal_chains": [], "uncorrelated_findings": []}


async def _llm_verdict(
    causal_chains: list[dict],
    reports: list[DomainReport],
    data_completeness: float,
) -> dict:
    """Stage 3: LLM produces verdict and remediation."""
    client = AnthropicClient(agent_name="cluster_synthesizer")

    report_summaries = json.dumps([
        {"domain": r.domain, "status": r.status.value, "confidence": r.confidence}
        for r in reports
    ], indent=2)

    prompt = f"""Based on the causal analysis, produce a cluster health verdict.

## Causal Chains
{json.dumps(causal_chains, indent=2)}

## Data Completeness: {data_completeness:.0%}

## Domain Report Statuses
{report_summaries}

## Required JSON Response
{{
  "platform_health": "HEALTHY|DEGRADED|CRITICAL",
  "blast_radius": {{
    "summary": "...",
    "affected_namespaces": 0,
    "affected_pods": 0,
    "affected_nodes": 0
  }},
  "remediation": {{
    "immediate": [{{"command": "...", "description": "...", "risk_level": "low|medium|high"}}],
    "long_term": [{{"description": "...", "effort_estimate": "..."}}]
  }},
  "re_dispatch_needed": false
}}"""

    response = await client.chat(
        prompt=prompt,
        system="You are a cluster health verdict engine. Be actionable and precise.",
        max_tokens=2000,
        temperature=0.1,
    )
    text = response.text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "platform_health": "UNKNOWN",
            "blast_radius": {"summary": "Unable to determine", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
            "remediation": {"immediate": [], "long_term": []},
            "re_dispatch_needed": False,
        }


@traced_node(timeout_seconds=60)
async def synthesize(state: dict, config: dict) -> dict:
    """LangGraph node: 3-stage synthesis pipeline."""
    diagnostic_id = state.get("diagnostic_id", "")
    platform = state.get("platform", "")
    platform_version = state.get("platform_version", "")

    # Reconstruct DomainReports from state
    reports = [DomainReport(**r) for r in state.get("domain_reports", [])]

    # Stage 1: Merge
    merged = _merge_reports(reports)
    data_completeness = _compute_data_completeness(reports)

    # Stage 2: Causal Reasoning (skip if no anomalies)
    causal_result: dict = {"causal_chains": [], "uncorrelated_findings": []}
    if merged["all_anomalies"]:
        causal_result = await _llm_causal_reasoning(merged["all_anomalies"], reports)

    # Stage 3: Verdict
    verdict = await _llm_verdict(causal_result.get("causal_chains", []), reports, data_completeness)

    # Build health report
    health_report = ClusterHealthReport(
        diagnostic_id=diagnostic_id,
        platform=platform,
        platform_version=platform_version,
        platform_health=verdict.get("platform_health", "UNKNOWN"),
        data_completeness=data_completeness,
        blast_radius=BlastRadius(**verdict.get("blast_radius", {})),
        causal_chains=[CausalChain(**c) for c in causal_result.get("causal_chains", []) if isinstance(c, dict) and "chain_id" in c],
        uncorrelated_findings=[DomainAnomaly(**f) for f in causal_result.get("uncorrelated_findings", []) if isinstance(f, dict) and "domain" in f],
        domain_reports=reports,
        remediation=verdict.get("remediation", {}),
        execution_metadata={
            "re_dispatch_count": state.get("re_dispatch_count", 0),
            "agents_succeeded": sum(1 for r in reports if r.status == DomainStatus.SUCCESS),
            "agents_failed": sum(1 for r in reports if r.status == DomainStatus.FAILED),
        },
    )

    return {
        "health_report": health_report.model_dump(mode="json"),
        "causal_chains": [c.model_dump(mode="json") for c in health_report.causal_chains],
        "uncorrelated_findings": [f.model_dump(mode="json") for f in health_report.uncorrelated_findings],
        "data_completeness": data_completeness,
        "phase": "complete",
        "re_dispatch_domains": verdict.get("re_dispatch_domains", []) if verdict.get("re_dispatch_needed") else [],
    }
