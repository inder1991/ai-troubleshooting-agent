"""Storage & Persistence diagnostic agent node."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from anthropic import RateLimitError, APITimeoutError

from src.agents.cluster.state import DomainReport, DomainStatus, DomainAnomaly, TruncationFlags, FailureReason
from src.agents.cluster.traced_node import traced_node
from src.agents.cluster.tools import get_tools_for_agent, get_version_context
from src.agents.cluster.tool_executor import execute_tool_call
from src.agents.cluster_client.base import QueryResult, OBJECT_CAPS
from src.utils.llm_client import AnthropicClient
from src.utils.llm_telemetry import LLMCallRecord
from src.utils.logger import get_logger

logger = get_logger(__name__)

def _safe_store_write(store, record: dict) -> None:
    """Fire-and-forget store write with error logging."""
    if store is None:
        return
    task = asyncio.ensure_future(store.log_llm_call(record))
    task.add_done_callback(
        lambda t: logger.warning("Store write failed: %s", t.exception()) if t.exception() else None
    )


MAX_TOOL_CALLS = 5
TOOL_CALL_TIMEOUT = 60  # seconds

_SYSTEM_PROMPT = """You are the Storage & Persistence diagnostic agent for DebugDuck.
You analyze: PVC capacity and usage, storage class configuration,
volume attach/detach latency, and stuck volumes.
For CSI driver health and IOPS metrics, analyze if available in the provided data.

Platform: {platform} {platform_version}
{platform_capabilities}
{version_context}

Analyze the provided storage data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this storage and persistence data and produce a JSON response:

## Data Collected
{data_json}
{truncation_note}

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


async def _llm_analyze(system: str, prompt: str, session_id: str = "") -> dict:
    """Single-pass LLM call using structured tool output. Returns findings dict."""
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    client = AnthropicClient(agent_name="cluster_storage", session_id=session_id)
    response = await client.chat_with_tools(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[SUBMIT_DOMAIN_FINDINGS_TOOL],
        max_tokens=2000,
        temperature=0.1,
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_domain_findings":
            return block.input
    logger.warning("LLM did not call submit_domain_findings tool", extra={"action": "parse_error"})
    return {"anomalies": [], "ruled_out": [], "confidence": 0}


async def _heuristic_analyze(data_payload: dict, domain: str = "storage") -> dict:
    """Deterministic rule-based analysis for storage. No LLM calls."""
    anomalies = []
    ruled_out = []

    # Check PVCs for Pending status and capacity
    for pvc in data_payload.get("pvcs", []):
        pvc_name = pvc.get("name", "unknown")
        ns = pvc.get("namespace", "default")
        status = pvc.get("status", pvc.get("phase", ""))
        if status == "Pending":
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"PVC {ns}/{pvc_name} is in Pending state (not bound)",
                "evidence_ref": f"pvc/{ns}/{pvc_name}",
                "severity": "high",
            })
        elif status == "Bound":
            ruled_out.append(f"PVC {ns}/{pvc_name} bound OK")

    # Check volume metrics for capacity > 90%
    for metric in data_payload.get("volume_metrics", []):
        pvc_name = metric.get("pvc", metric.get("persistentvolumeclaim", "unknown"))
        ns = metric.get("namespace", "default")
        used = metric.get("used_bytes", 0)
        capacity = metric.get("capacity_bytes", 0)
        if capacity > 0:
            usage_pct = (used / capacity) * 100
            if usage_pct > 90:
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"PVC {ns}/{pvc_name} at {usage_pct:.0f}% capacity",
                    "evidence_ref": f"pvc/{ns}/{pvc_name}",
                    "severity": "high",
                })
            elif usage_pct > 80:
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"PVC {ns}/{pvc_name} at {usage_pct:.0f}% capacity (approaching limit)",
                    "evidence_ref": f"pvc/{ns}/{pvc_name}",
                    "severity": "medium",
                })
            else:
                ruled_out.append(f"PVC {ns}/{pvc_name} capacity OK ({usage_pct:.0f}%)")

    confidence = 50 if anomalies else 70
    return {"anomalies": anomalies, "ruled_out": ruled_out, "confidence": confidence}


async def _tool_calling_loop(system: str, initial_context: str, cluster_client,
                              budget=None, telemetry=None, store=None, session_id: str = "") -> dict | None:
    """ReAct tool-calling loop for storage agent. Returns parsed findings dict or None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    llm = AnthropicClient(agent_name="cluster_storage", model="claude-haiku-4-5-20251001", session_id=session_id)
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    base_tools = get_tools_for_agent("storage")
    # Replace unschema'd submit_findings with SUBMIT_DOMAIN_FINDINGS_TOOL (schema-enforced)
    tools = [t for t in base_tools if t.get("name") != "submit_findings"]
    tools.append(SUBMIT_DOMAIN_FINDINGS_TOOL)

    messages = [{"role": "user", "content": initial_context}]
    tool_call_count = 0
    retry_count = 0

    for iteration in range(MAX_TOOL_CALLS + 1):
        call_start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                llm.chat_with_tools(
                    system=system,
                    messages=messages,
                    tools=tools,
                    max_tokens=2000,
                    temperature=0.1,
                ),
                timeout=15,
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.monotonic() - call_start) * 1000)
            if telemetry:
                telemetry.record_call(LLMCallRecord(
                    agent_name="cluster_storage", model="claude-haiku-4-5-20251001",
                    call_type="tool_calling", latency_ms=latency_ms,
                    error="timeout", success=False,
                ))
            return None
        except RateLimitError:
            if retry_count < 3:
                await asyncio.sleep(2 ** retry_count)
                retry_count += 1
                continue
            if telemetry:
                telemetry.record_call(LLMCallRecord(
                    agent_name="cluster_storage", model="claude-haiku-4-5-20251001",
                    call_type="tool_calling", error="rate_limit", success=False,
                ))
            return None

        latency_ms = int((time.monotonic() - call_start) * 1000)
        usage = getattr(response, "usage", None)
        in_tok = usage.input_tokens if usage else 0
        out_tok = usage.output_tokens if usage else 0

        if budget:
            budget.record(input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency_ms)
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_storage", model="claude-haiku-4-5-20251001",
                call_type="tool_calling", input_tokens=in_tok, output_tokens=out_tok,
                latency_ms=latency_ms, success=True,
            ))

        # Log to DiagnosticStore (fire-and-forget)
        if store is not None and session_id:
            _safe_store_write(store, {
                "session_id": session_id,
                "agent_name": "cluster_storage",
                "model": "claude-haiku-4-5-20251001",
                "call_type": "tool_calling",
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "latency_ms": latency_ms,
                "success": True,
                "error": None,
                "fallback_used": False,
                "response_json": json.dumps([{"type": getattr(b, "type", "unknown"), **({"text": b.text} if hasattr(b, "text") else {"name": b.name, "input": b.input} if hasattr(b, "name") else {})} for b in response.content], default=str)[:2000],
                "created_at": time.time(),
            })

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            # LLM responded without calling any tool — treat as no findings
            logger.warning("LLM iteration produced no tool calls — falling back",
                           extra={"action": "no_tool_call", "iteration": iteration})
            return None

        # Check for submit_domain_findings tool
        for tu in tool_uses:
            if tu.name == "submit_domain_findings":
                return tu.input

        if tool_call_count >= MAX_TOOL_CALLS:
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_uses[0].id,
                 "content": "Tool budget exhausted. Please submit your findings now using submit_domain_findings."}
            ]})
            continue

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_uses:
            result_str = await execute_tool_call(tu.name, tu.input, cluster_client, tool_call_count)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
            })
            tool_call_count += 1

        messages.append({"role": "user", "content": tool_results})

    return None


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

    # Gather data — namespace-scoped to avoid cluster-wide leakage
    scope = state.get("diagnostic_scope", {})
    ns_list = scope.get("namespaces", [])
    if ns_list:

        all_pvcs: list = []
        for namespace in ns_list:
            result = await client.list_pvcs(namespace=namespace)
            all_pvcs.extend(result.data if hasattr(result, "data") else [])
        cap = OBJECT_CAPS["pvcs"]
        pvcs = QueryResult(
            data=all_pvcs[:cap],
            total_available=len(all_pvcs),
            returned=min(len(all_pvcs), cap),
            truncated=len(all_pvcs) > cap,
        )
    else:
        pvcs = await client.list_pvcs()

    # Enrich with Prometheus volume utilization metrics if client is available
    prometheus_client = config.get("configurable", {}).get("prometheus_client")
    volume_metrics_raw: list = []
    if prometheus_client:
        try:
            used_result = await prometheus_client.query_instant(
                "kubelet_volume_stats_used_bytes"
            )
            for item in used_result.get("data", {}).get("result", []):
                pvc_name = item["metric"].get("persistentvolumeclaim", "unknown")
                namespace = item["metric"].get("namespace", "default")
                try:
                    used_bytes = float(item["value"][1])
                except (IndexError, TypeError, ValueError):
                    used_bytes = 0.0
                volume_metrics_raw.append({
                    "pvc": pvc_name,
                    "namespace": namespace,
                    "used_bytes": used_bytes,
                })
        except Exception as exc:
            logger.debug("Prometheus volume used bytes query failed: %s", exc)
        try:
            capacity_result = await prometheus_client.query_instant(
                "kubelet_volume_stats_capacity_bytes"
            )
            capacity_map: dict = {}
            for item in capacity_result.get("data", {}).get("result", []):
                pvc_name = item["metric"].get("persistentvolumeclaim", "unknown")
                namespace = item["metric"].get("namespace", "default")
                try:
                    capacity_map[(pvc_name, namespace)] = float(item["value"][1])
                except (IndexError, TypeError, ValueError):
                    capacity_map[(pvc_name, namespace)] = 0.0
            for entry in volume_metrics_raw:
                entry["capacity_bytes"] = capacity_map.get((entry["pvc"], entry["namespace"]), 0.0)
        except Exception as exc:
            logger.debug("Prometheus volume capacity bytes query failed: %s", exc)

    # Check for RBAC permission denials
    rbac_anomalies = []
    rbac_denied = False
    rbac_counter = 0
    for result, resource_name in [(pvcs, "persistentvolumeclaims")]:
        if result.permission_denied:
            rbac_denied = True
            rbac_counter += 1
            rbac_anomalies.append(DomainAnomaly(
                domain="storage",
                anomaly_id=f"rbac-storage-{rbac_counter:03d}",
                description=f"Insufficient RBAC permissions to access {resource_name}. Required ClusterRole: view",
                evidence_ref=f"rbac/{resource_name}",
                severity="high",
            ))

    platform_caps = (
        "Full access: StorageClasses, CSI drivers, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only."
    )

    data_payload = {
        "pvcs": pvcs.data,
        "volume_metrics": volume_metrics_raw,
    }

    version_context = get_version_context(platform_version)
    truncation_note = ""
    if pvcs.truncated:
        truncation_note += f"\nNOTE: PVCs truncated — {pvcs.total_available} total, {pvcs.returned} analyzed."

    system = _SYSTEM_PROMPT.format(
        platform=platform,
        platform_version=platform_version,
        platform_capabilities=platform_caps,
        version_context=version_context,
    )
    prompt = _ANALYSIS_PROMPT.format(
        data_json=json.dumps(data_payload, indent=2, default=str),
        truncation_note=truncation_note,
    )

    # Extract budget, telemetry, store, and session_id from config
    budget = config.get("configurable", {}).get("budget")
    telemetry = config.get("configurable", {}).get("telemetry")
    store = config.get("configurable", {}).get("store")
    diagnostic_id = state.get("diagnostic_id", "")

    # Check budget before attempting LLM
    analysis = None
    if budget and not budget.can_call():
        logger.info("Budget exhausted for storage, using heuristic")
        analysis = await _heuristic_analyze(data_payload, "storage")
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_storage", call_type="heuristic",
                fallback_used=True, success=True,
            ))
        if store is not None and diagnostic_id:
            _safe_store_write(store, {
                "session_id": diagnostic_id,
                "agent_name": "cluster_storage",
                "model": "heuristic",
                "call_type": "heuristic",
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 0,
                "success": True,
                "error": None,
                "fallback_used": True,
                "response_json": analysis,
                "created_at": time.time(),
            })
    else:
        # Try tool-calling ReAct loop first, fall back to heuristic single-pass
        try:
            prefetch_summary = (
                f"Here is data already collected for your analysis:\n\n"
                f"## Pre-Fetched Data Summary\n"
                f"- PVCs: {len(pvcs.data)} found\n"
                f"- Volume metrics: {len(volume_metrics_raw)} series\n"
                f"{truncation_note}\n\n"
                f"Use tools to investigate specific anomalies in depth. "
                f"Do NOT re-fetch data that is already provided above.\n"
                f"Start by examining the most critical anomalies and call submit_domain_findings when done."
            )
            initial_context = (
                f"Analyze this Kubernetes cluster for storage and persistence issues.\n\n"
                f"Platform: {platform} {platform_version}\n\n"
                f"{prefetch_summary}"
            )
            analysis = await asyncio.wait_for(
                _tool_calling_loop(system, initial_context, client,
                                   budget=budget, telemetry=telemetry,
                                   store=store, session_id=diagnostic_id),
                timeout=TOOL_CALL_TIMEOUT,
            )
        except Exception as e:
            logger.warning("Tool-calling failed for storage, falling back to heuristic: %s", e)

        if not analysis:
            if budget and not budget.can_call():
                analysis = await _heuristic_analyze(data_payload, "storage")
                if telemetry:
                    telemetry.record_call(LLMCallRecord(
                        agent_name="cluster_storage", call_type="heuristic",
                        fallback_used=True, success=True,
                    ))
                if store is not None and diagnostic_id:
                    _safe_store_write(store, {
                        "session_id": diagnostic_id,
                        "agent_name": "cluster_storage",
                        "model": "heuristic",
                        "call_type": "heuristic",
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_ms": 0,
                        "success": True,
                        "error": None,
                        "fallback_used": True,
                        "response_json": analysis,
                        "created_at": time.time(),
                    })
            else:
                analysis = await _llm_analyze(system, prompt, session_id=diagnostic_id)

    anomalies = [
        DomainAnomaly(**a) for a in analysis.get("anomalies", [])
        if isinstance(a, dict) and "domain" in a
    ]
    anomalies.extend(rbac_anomalies)

    elapsed = int((time.monotonic() - start_ms) * 1000)
    report = DomainReport(
        domain="storage",
        status=DomainStatus.PARTIAL if rbac_denied else DomainStatus.SUCCESS,
        failure_reason=FailureReason.RBAC_DENIED if rbac_denied else None,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(pvcs=pvcs.truncated),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
