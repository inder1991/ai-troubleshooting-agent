"""Network & Ingress diagnostic agent node."""

from __future__ import annotations

import json
import time
from typing import Any

from src.agents.cluster.state import DomainReport, DomainStatus, DomainAnomaly, TruncationFlags, FailureReason
from src.agents.cluster.traced_node import traced_node
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are the Network & Ingress diagnostic agent for DebugDuck.
You analyze: DNS resolution failures, ingress controller health, network policies,
service mesh connectivity, CoreDNS pod status, and ingress 5xx rates.

Platform: {platform} {platform_version}
{platform_capabilities}

Analyze the provided network data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this network and ingress data and produce a JSON response:

## Data Collected
{data_json}

## Required JSON Response Format
{{
  "anomalies": [
    {{"domain": "network", "anomaly_id": "net-NNN", "description": "...", "evidence_ref": "ev-net-NNN", "severity": "high|medium|low"}}
  ],
  "ruled_out": ["list of things checked and found healthy"],
  "confidence": 0-100
}}

Rules:
- Only report anomalies you have evidence for
- DNS failures above 10% are high severity
- Correlate CoreDNS pod status with DNS resolution metrics
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage"""


async def _llm_analyze(system: str, prompt: str) -> dict:
    """Two-pass LLM call. Returns parsed JSON dict."""
    client = AnthropicClient(agent_name="cluster_network")
    response = await client.chat(
        prompt=prompt,
        system=system,
        max_tokens=2000,
        temperature=0.1,
    )
    text = response.text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse LLM response as JSON", extra={"action": "parse_error"})
        return {"anomalies": [], "ruled_out": [], "confidence": 0}


@traced_node(timeout_seconds=45)
async def network_agent(state: dict, config: dict) -> dict:
    """LangGraph node: Network & Ingress diagnostics."""
    start_ms = time.monotonic()
    client = config.get("configurable", {}).get("cluster_client")
    if not client:
        return {"domain_reports": [DomainReport(
            domain="network", status=DomainStatus.FAILED,
            failure_reason=FailureReason.EXCEPTION,
        ).model_dump(mode="json")]}

    platform = state.get("platform", "kubernetes")
    platform_version = state.get("platform_version", "")

    # Gather data - DNS pods, ingress, metrics, logs
    dns_metrics = await client.query_prometheus("coredns_dns_requests_total")
    ingress_metrics = await client.query_prometheus("ingress_5xx_rate")
    logs = await client.query_logs("cluster-logs", {"query": "coredns OR ingress"})

    platform_caps = (
        "Full access: Routes, IngressControllers, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only. No Routes or IngressControllers."
    )

    data_payload = {
        "dns_metrics": dns_metrics.data,
        "ingress_metrics": ingress_metrics.data,
        "logs": logs.data[:50],
    }

    system = _SYSTEM_PROMPT.format(
        platform=platform,
        platform_version=platform_version,
        platform_capabilities=platform_caps,
    )
    prompt = _ANALYSIS_PROMPT.format(data_json=json.dumps(data_payload, indent=2, default=str))

    analysis = await _llm_analyze(system, prompt)

    anomalies = [
        DomainAnomaly(**a) for a in analysis.get("anomalies", [])
        if isinstance(a, dict) and "domain" in a
    ]

    elapsed = int((time.monotonic() - start_ms) * 1000)
    report = DomainReport(
        domain="network",
        status=DomainStatus.SUCCESS,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(log_lines=logs.truncated),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
