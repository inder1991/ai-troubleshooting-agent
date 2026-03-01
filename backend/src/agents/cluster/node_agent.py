"""Node & Capacity diagnostic agent node."""

from __future__ import annotations

import json
import time
from typing import Any

from src.agents.cluster.state import DomainReport, DomainStatus, DomainAnomaly, TruncationFlags, FailureReason
from src.agents.cluster.traced_node import traced_node
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are the Node & Capacity diagnostic agent for DebugDuck.
You analyze: node conditions (DiskPressure, MemoryPressure, PIDPressure, NotReady), resource utilization,
pod evictions, scheduling failures, resource quotas, and capacity planning.

Platform: {platform} {platform_version}
{platform_capabilities}

Analyze the provided node data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this node and capacity data and produce a JSON response:

## Data Collected
{data_json}

## Required JSON Response Format
{{
  "anomalies": [
    {{"domain": "node", "anomaly_id": "node-NNN", "description": "...", "evidence_ref": "ev-node-NNN", "severity": "high|medium|low"}}
  ],
  "ruled_out": ["list of things checked and found healthy"],
  "confidence": 0-100
}}

Rules:
- Only report anomalies you have evidence for
- DiskPressure at 97% is critical
- Pod evictions caused by node conditions are high severity
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage"""


async def _llm_analyze(system: str, prompt: str) -> dict:
    """Two-pass LLM call. Returns parsed JSON dict."""
    client = AnthropicClient(agent_name="cluster_node")
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
async def node_agent(state: dict, config: dict) -> dict:
    """LangGraph node: Node & Capacity diagnostics."""
    start_ms = time.monotonic()
    client = config.get("configurable", {}).get("cluster_client")
    if not client:
        return {"domain_reports": [DomainReport(
            domain="node", status=DomainStatus.FAILED,
            failure_reason=FailureReason.EXCEPTION,
        ).model_dump(mode="json")]}

    platform = state.get("platform", "kubernetes")
    platform_version = state.get("platform_version", "")

    # Gather data
    nodes = await client.list_nodes()

    # Namespace-scoped event fetching to avoid cluster-wide leakage
    scope = state.get("diagnostic_scope", {})
    ns_list = scope.get("namespaces", [])
    if ns_list:
        from src.agents.cluster_client.base import QueryResult, OBJECT_CAPS
        all_events: list = []
        for namespace in ns_list:
            result = await client.list_events(namespace=namespace)
            all_events.extend(result.data if hasattr(result, "data") else [])
        cap = OBJECT_CAPS["events"]
        events = QueryResult(
            data=all_events[:cap],
            total_available=len(all_events),
            returned=min(len(all_events), cap),
            truncated=len(all_events) > cap,
        )
    else:
        events = await client.list_events()

    pods = await client.list_pods()

    platform_caps = (
        "Full access: MachineSets, MachineConfigPools, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only. No MachineSets or MachineConfigPools."
    )

    data_payload = {
        "nodes": nodes.data,
        "events": events.data[:100],
        "top_pods": pods.data[:50],
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
        domain="node",
        status=DomainStatus.SUCCESS,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(
            events=events.truncated,
            nodes=nodes.truncated,
            pods=pods.truncated,
        ),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
