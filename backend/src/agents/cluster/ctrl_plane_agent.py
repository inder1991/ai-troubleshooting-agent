"""Control Plane & Etcd diagnostic agent node."""

from __future__ import annotations

import json
import time
from typing import Any

from src.agents.cluster.state import DomainReport, DomainStatus, DomainAnomaly, TruncationFlags, FailureReason
from src.agents.cluster.traced_node import traced_node
from src.agents.cluster_client.base import QueryResult, OBJECT_CAPS
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are the Control Plane & Etcd diagnostic agent for DebugDuck.
You analyze: degraded operators, API server latency, etcd sync/health, certificate expiry, leader election.

Platform: {platform} {platform_version}
{platform_capabilities}

Analyze the provided cluster data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this control plane data and produce a JSON response:

## Data Collected
{data_json}

## Required JSON Response Format
{{
  "anomalies": [
    {{"domain": "ctrl_plane", "anomaly_id": "cp-NNN", "description": "...", "evidence_ref": "ev-ctrl-NNN", "severity": "high|medium|low"}}
  ],
  "ruled_out": ["list of things checked and found healthy"],
  "confidence": 0-100
}}

Rules:
- Only report anomalies you have evidence for
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage
- ruled_out is important -- shows thoroughness"""


async def _llm_analyze(system: str, prompt: str) -> dict:
    """Two-pass LLM call. Returns parsed JSON dict."""
    client = AnthropicClient(agent_name="cluster_ctrl_plane")
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


@traced_node(timeout_seconds=30)
async def ctrl_plane_agent(state: dict, config: dict) -> dict:
    """LangGraph node: Control Plane & Etcd diagnostics."""
    start_ms = time.monotonic()
    client = config.get("configurable", {}).get("cluster_client")
    if not client:
        return {"domain_reports": [DomainReport(
            domain="ctrl_plane", status=DomainStatus.FAILED,
            failure_reason=FailureReason.EXCEPTION,
        ).model_dump(mode="json")]}

    platform = state.get("platform", "kubernetes")
    platform_version = state.get("platform_version", "")

    # Gather data
    api_health = await client.get_api_health()
    operators = await client.get_cluster_operators()

    # Namespace-scoped event fetching to avoid cluster-wide leakage
    scope = state.get("diagnostic_scope", {})
    ns_list = scope.get("namespaces", [])
    if ns_list:

        all_events: list = []
        for namespace in ns_list:
            result = await client.list_events(
                namespace=namespace,
                field_selector="involvedObject.kind=Node",
            )
            all_events.extend(result.data if hasattr(result, "data") else [])
        cap = OBJECT_CAPS["events"]
        events = QueryResult(
            data=all_events[:cap],
            total_available=len(all_events),
            returned=min(len(all_events), cap),
            truncated=len(all_events) > cap,
        )
    else:
        events = await client.list_events(field_selector="involvedObject.kind=Node")

    platform_caps = (
        "Full access: ClusterOperators, Routes, SCCs, MachineSets, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only. No Routes, SCCs, ClusterOperators."
    )

    data_payload = {
        "api_health": api_health,
        "cluster_operators": operators.data,
        "events": events.data[:100],
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
        domain="ctrl_plane",
        status=DomainStatus.SUCCESS,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(events=events.truncated),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
