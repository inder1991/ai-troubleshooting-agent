"""Control Plane & Etcd diagnostic agent node."""

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

MAX_TOOL_CALLS = 5
TOOL_CALL_TIMEOUT = 60  # seconds

_SYSTEM_PROMPT = """You are the Control Plane & Etcd diagnostic agent for DebugDuck.
You analyze: degraded operators, API server latency, etcd sync/health, certificate expiry, leader election.
For OpenShift clusters, you also analyze MachineConfigPool health, SCC restrictions, and operator lifecycle.

Platform: {platform} {platform_version}
{platform_capabilities}
{version_context}

Analyze the provided cluster data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this control plane data and produce a JSON response:

## Data Collected
{data_json}
{truncation_note}

## Required JSON Response Format
{{
  "anomalies": [
    {{"domain": "ctrl_plane", "anomaly_id": "cp-NNN", "description": "...", "evidence_ref": "ev-ctrl-NNN", "severity": "high|medium|low"}}
  ],
  "ruled_out": ["list of things checked and found healthy"],
  "confidence": 0-100
}}

DIAGNOSTIC RULES — report an anomaly for each of the following when you find evidence:

1. ClusterOperator Degraded: Any operator with conditions[type=Degraded].status == "True"
2. ClusterOperator Unavailable: Any operator with conditions[type=Available].status == "False"
3. API Server unhealthy: `api_health.status` is not 'ok' or 'healthy', or HTTP response is non-200
4. Node NotReady: Warning events with reason NodeNotReady
5. OOMKilling: Any Warning event with reason OOMKilling
6. High Warning count: Total Warning events > 10 in any namespace indicates system instability
7. MachineConfigPool degraded (OpenShift): status.degradedMachineCount > 0
8. MachineConfigPool mismatch (OpenShift): status.machineCount != status.updatedMachineCount

General rules:
- Only report anomalies you have evidence for
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage
- ruled_out is important -- shows thoroughness"""


async def _llm_analyze(system: str, prompt: str) -> dict:
    """Single-pass LLM call using structured tool output. Returns findings dict."""
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    client = AnthropicClient(agent_name="cluster_ctrl_plane")
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


async def _heuristic_analyze(data_payload: dict, domain: str = "ctrl_plane") -> dict:
    """Deterministic rule-based analysis for ctrl_plane. No LLM calls."""
    anomalies = []
    ruled_out = []

    # Check cluster operators for degraded status
    for op in data_payload.get("cluster_operators", []):
        op_name = op.get("name", "unknown")
        if op.get("degraded"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Operator {op_name} is degraded",
                "evidence_ref": f"operator/{op_name}",
                "severity": "high",
            })
        elif op.get("available") is False:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Operator {op_name} is unavailable",
                "evidence_ref": f"operator/{op_name}",
                "severity": "high",
            })
        else:
            ruled_out.append(f"Operator {op_name} healthy")

    # Check API health
    api_health = data_payload.get("api_health", {})
    if api_health.get("status") not in (None, "ok", "healthy"):
        anomalies.append({
            "domain": domain,
            "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
            "description": f"API server health check returned: {api_health.get('status', 'unknown')}",
            "evidence_ref": "api-server/health",
            "severity": "high",
        })
    else:
        ruled_out.append("API server health OK")

    # Check events for warnings
    warning_events = [e for e in data_payload.get("events", []) if e.get("type") == "Warning"]
    if len(warning_events) > 10:
        anomalies.append({
            "domain": domain,
            "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
            "description": f"High volume of warning events ({len(warning_events)} warnings in control plane events)",
            "evidence_ref": "events/warnings",
            "severity": "medium",
        })

    # Check MachineConfigPools (OpenShift)
    for mcp in data_payload.get("machine_config_pools", []):
        mcp_name = mcp.get("name", "unknown")
        if mcp.get("degraded"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"MachineConfigPool {mcp_name} is degraded",
                "evidence_ref": f"mcp/{mcp_name}",
                "severity": "high",
            })

    confidence = 50 if anomalies else 70
    return {"anomalies": anomalies, "ruled_out": ruled_out, "confidence": confidence}


async def _tool_calling_loop(system: str, initial_context: str, cluster_client,
                              budget=None, telemetry=None) -> dict | None:
    """ReAct tool-calling loop for ctrl_plane agent. Returns parsed findings dict or None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    llm = AnthropicClient(agent_name="cluster_ctrl_plane", model="claude-haiku-4-5-20251001")
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    base_tools = get_tools_for_agent("ctrl_plane")
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
                    agent_name="cluster_ctrl_plane", model="claude-haiku-4-5-20251001",
                    call_type="tool_calling", latency_ms=latency_ms,
                    error="timeout", success=False,
                ))
            return None  # Triggers heuristic fallback
        except RateLimitError:
            if retry_count < 3:
                await asyncio.sleep(2 ** retry_count)
                retry_count += 1
                continue
            if telemetry:
                telemetry.record_call(LLMCallRecord(
                    agent_name="cluster_ctrl_plane", model="claude-haiku-4-5-20251001",
                    call_type="tool_calling", error="rate_limit", success=False,
                ))
            return None  # Triggers heuristic fallback

        latency_ms = int((time.monotonic() - call_start) * 1000)
        input_tokens = getattr(response, "usage", None)
        in_tok = input_tokens.input_tokens if input_tokens else 0
        out_tok = input_tokens.output_tokens if input_tokens else 0

        if budget:
            budget.record(input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency_ms)
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_ctrl_plane", model="claude-haiku-4-5-20251001",
                call_type="tool_calling", input_tokens=in_tok, output_tokens=out_tok,
                latency_ms=latency_ms, success=True,
            ))

        # Check if the model wants to use tools
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if not tool_uses:
            # LLM responded without calling any tool — treat as no findings
            logger.warning("LLM iteration produced no tool calls — falling back",
                           extra={"action": "no_tool_call", "iteration": iteration})
            return None

        # Check for submit_domain_findings tool
        for tu in tool_uses:
            if tu.name == "submit_domain_findings":
                return tu.input

        # Budget exhausted -- force the model to respond
        if tool_call_count >= MAX_TOOL_CALLS:
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_uses[0].id,
                 "content": "Tool budget exhausted. Please submit your findings now using submit_findings."}
            ]})
            continue

        # Execute tool calls
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

    return None  # Exhausted iterations


@traced_node(timeout_seconds=60)
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

    # Check for RBAC permission denials
    rbac_anomalies = []
    rbac_denied = False
    for result, resource_name in [(events, "events")]:
        if result.permission_denied:
            rbac_denied = True
            rbac_anomalies.append(DomainAnomaly(
                domain="ctrl_plane",
                anomaly_id=f"rbac-ctrl_plane-001",
                description=f"Insufficient RBAC permissions to access {resource_name}. Required ClusterRole: view",
                evidence_ref=f"rbac/{resource_name}",
                severity="high",
            ))

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

    # OpenShift-specific data
    if platform == "openshift":
        machine_config_pools = await client.get_machine_config_pools()
        sccs = await client.get_security_context_constraints()
        if machine_config_pools.data:
            data_payload["machine_config_pools"] = machine_config_pools.data
        if sccs.data:
            data_payload["security_context_constraints"] = sccs.data

    version_context = get_version_context(platform_version)
    truncation_note = ""
    if events.truncated:
        truncation_note += f"\nNOTE: Events truncated — {events.total_available} total, {events.returned} analyzed."

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

    # Extract budget and telemetry from config
    budget = config.get("configurable", {}).get("budget")
    telemetry = config.get("configurable", {}).get("telemetry")

    # Check budget before attempting LLM
    analysis = None
    if budget and not budget.can_call():
        logger.info("Budget exhausted for ctrl_plane, using heuristic")
        analysis = await _heuristic_analyze(data_payload, "ctrl_plane")
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_ctrl_plane", call_type="heuristic",
                fallback_used=True, success=True,
            ))
    else:
        # Try tool-calling ReAct loop first, fall back to heuristic single-pass
        try:
            initial_context = (
                "Analyze this Kubernetes cluster for control plane issues. "
                "Start by examining nodes and events for API server, etcd, and operator health.\n\n"
                f"Platform: {platform} {platform_version}"
            )
            analysis = await asyncio.wait_for(
                _tool_calling_loop(system, initial_context, client,
                                   budget=budget, telemetry=telemetry),
                timeout=TOOL_CALL_TIMEOUT,
            )
        except Exception as e:
            logger.warning("Tool-calling failed for ctrl_plane, falling back to heuristic: %s", e)

        if not analysis:
            # Try single-pass LLM if budget allows, otherwise heuristic
            if budget and not budget.can_call():
                analysis = await _heuristic_analyze(data_payload, "ctrl_plane")
                if telemetry:
                    telemetry.record_call(LLMCallRecord(
                        agent_name="cluster_ctrl_plane", call_type="heuristic",
                        fallback_used=True, success=True,
                    ))
            else:
                analysis = await _llm_analyze(system, prompt)

    anomalies = [
        DomainAnomaly(**a) for a in analysis.get("anomalies", [])
        if isinstance(a, dict) and "domain" in a
    ]
    anomalies.extend(rbac_anomalies)

    elapsed = int((time.monotonic() - start_ms) * 1000)
    report = DomainReport(
        domain="ctrl_plane",
        status=DomainStatus.PARTIAL if rbac_denied else DomainStatus.SUCCESS,
        failure_reason=FailureReason.RBAC_DENIED if rbac_denied else None,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(events=events.truncated),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
