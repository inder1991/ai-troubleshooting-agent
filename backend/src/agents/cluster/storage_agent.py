"""Storage & Persistence diagnostic agent node."""

from __future__ import annotations

import json
import time
from typing import Any

from src.agents.cluster.state import DomainReport, DomainStatus, DomainAnomaly, TruncationFlags, FailureReason
from src.agents.cluster.traced_node import traced_node
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are the Storage & Persistence diagnostic agent for DebugDuck.
You analyze: PVC capacity and usage, CSI driver health, storage class configuration,
volume attach/detach latency, IOPS throttling, and stuck volumes.

Platform: {platform} {platform_version}
{platform_capabilities}

Analyze the provided storage data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this storage and persistence data and produce a JSON response:

## Data Collected
{data_json}

## Required JSON Response Format
{{
  "anomalies": [
    {{"domain": "storage", "anomaly_id": "stor-NNN", "description": "...", "evidence_ref": "ev-stor-NNN", "severity": "high|medium|low"}}
  ],
  "ruled_out": ["list of things checked and found healthy"],
  "confidence": 0-100
}}

Rules:
- Only report anomalies you have evidence for
- PVC usage above 90% is high severity
- IOPS throttling is medium severity
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage"""


async def _llm_analyze(system: str, prompt: str) -> dict:
    """Two-pass LLM call. Returns parsed JSON dict."""
    client = AnthropicClient(agent_name="cluster_storage")
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


@traced_node(timeout_seconds=60)
async def storage_agent(state: dict, config: dict) -> dict:
    """LangGraph node: Storage & Persistence diagnostics."""
    start_ms = time.monotonic()
    client = config.get("configurable", {}).get("cluster_client")
    if not client:
        return {"domain_reports": [DomainReport(
            domain="storage", status=DomainStatus.FAILED,
            failure_reason=FailureReason.EXCEPTION,
        ).model_dump(mode="json")]}

    platform = state.get("platform", "kubernetes")
    platform_version = state.get("platform_version", "")

    # Gather data
    pvcs = await client.list_pvcs()
    volume_metrics = await client.query_prometheus("kubelet_volume_stats_used_bytes")

    platform_caps = (
        "Full access: StorageClasses, CSI drivers, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only."
    )

    data_payload = {
        "pvcs": pvcs.data,
        "volume_metrics": volume_metrics.data,
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
        domain="storage",
        status=DomainStatus.SUCCESS,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(pvcs=pvcs.truncated),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
