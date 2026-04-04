"""Network & Ingress diagnostic agent node."""

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
from src.agents.cluster_client.base import QueryResult
from src.utils.llm_client import AnthropicClient
from src.utils.llm_telemetry import LLMCallRecord
from src.utils.logger import get_logger

logger = get_logger(__name__)

MAX_TOOL_CALLS = 5
TOOL_CALL_TIMEOUT = 60  # seconds

_SYSTEM_PROMPT = """You are the Network & Ingress diagnostic agent for DebugDuck.
You analyze: DNS resolution failures, ingress controller health, network policies,
service mesh connectivity, CoreDNS pod status, and ingress 5xx rates.

Platform: {platform} {platform_version}
{platform_capabilities}
{version_context}

Analyze the provided network data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this network and ingress data and produce a JSON response:

## Data Collected
{data_json}
{truncation_note}

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
- Service with 0 ready endpoints = no backends, traffic will fail (high severity)
- Service selector matching no pods = orphaned service (medium severity)
- LoadBalancer service with external_ip "<Pending>" = external access unavailable (high severity)
- Endpoints with not_ready_addresses > 0 = backends unhealthy (medium severity)
- Default deny NetworkPolicy blocking all traffic = note for review (low severity unless critical namespace)
- NetworkPolicy with empty ingress/egress rules = blocks all traffic for that direction (high severity if affects critical namespaces)
- NetworkPolicy targeting pods that match no running pods = dead policy (low severity)
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage"""


async def _llm_analyze(system: str, prompt: str) -> dict:
    """Heuristic single-pass LLM call (fallback). Returns parsed JSON dict."""
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


async def _heuristic_analyze(data_payload: dict, domain: str = "network") -> dict:
    """Deterministic rule-based analysis for network. No LLM calls."""
    anomalies = []
    ruled_out = []

    # Check services for missing endpoints
    for svc in data_payload.get("services", []):
        svc_name = svc.get("name", "unknown")
        ns = svc.get("namespace", "default")
        svc_type = svc.get("type", "ClusterIP")
        if svc.get("ready_endpoints", -1) == 0:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Service {ns}/{svc_name} has 0 ready endpoints",
                "evidence_ref": f"service/{ns}/{svc_name}",
                "severity": "high",
            })
        if svc_type == "LoadBalancer" and svc.get("external_ip") in (None, "", "<Pending>"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"LoadBalancer service {ns}/{svc_name} has pending external IP",
                "evidence_ref": f"service/{ns}/{svc_name}",
                "severity": "high",
            })

    # Check for DNS-related warning events
    dns_warnings = []
    ingress_warnings = []
    for log_entry in data_payload.get("logs", []):
        msg = str(log_entry.get("message", "")).lower()
        if "dns" in msg or "coredns" in msg or "nxdomain" in msg:
            dns_warnings.append(log_entry)
        if "5xx" in msg or "502" in msg or "503" in msg or "504" in msg:
            ingress_warnings.append(log_entry)

    if len(dns_warnings) > 5:
        anomalies.append({
            "domain": domain,
            "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
            "description": f"Elevated DNS-related log entries ({len(dns_warnings)} occurrences)",
            "evidence_ref": "logs/dns",
            "severity": "high",
        })
    else:
        ruled_out.append("DNS log entries within normal range")

    if len(ingress_warnings) > 3:
        anomalies.append({
            "domain": domain,
            "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
            "description": f"Ingress 5xx errors detected ({len(ingress_warnings)} occurrences in logs)",
            "evidence_ref": "logs/ingress",
            "severity": "high",
        })
    else:
        ruled_out.append("No significant ingress 5xx errors in logs")

    # Check network policies for overly broad deny
    for np in data_payload.get("network_policies", []):
        np_name = np.get("name", "unknown")
        ns = np.get("namespace", "default")
        if np.get("policy_types") and not np.get("ingress") and not np.get("egress"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"NetworkPolicy {ns}/{np_name} has empty rules (blocks all traffic)",
                "evidence_ref": f"networkpolicy/{ns}/{np_name}",
                "severity": "high",
            })

    confidence = 50 if anomalies else 70
    return {"anomalies": anomalies, "ruled_out": ruled_out, "confidence": confidence}


async def _tool_calling_loop(system: str, initial_context: str, cluster_client,
                              budget=None, telemetry=None) -> dict | None:
    """ReAct tool-calling loop for network agent. Returns parsed findings dict or None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    llm = AnthropicClient(agent_name="cluster_network", model="claude-haiku-4-5-20251001")
    tools = get_tools_for_agent("network")

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
                    agent_name="cluster_network", model="claude-haiku-4-5-20251001",
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
                    agent_name="cluster_network", model="claude-haiku-4-5-20251001",
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
                agent_name="cluster_network", model="claude-haiku-4-5-20251001",
                call_type="tool_calling", input_tokens=in_tok, output_tokens=out_tok,
                latency_ms=latency_ms, success=True,
            ))

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if not tool_uses:
            text = "".join(b.text for b in text_blocks)
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                if telemetry:
                    telemetry.record_call(LLMCallRecord(
                        agent_name="cluster_network", call_type="tool_calling",
                        error="parse_error", success=False,
                    ))
                return None

        for tu in tool_uses:
            if tu.name == "submit_findings":
                return tu.input

        if tool_call_count >= MAX_TOOL_CALLS:
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_uses[0].id,
                 "content": "Tool budget exhausted. Please submit your findings now using submit_findings."}
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

    prometheus_client = config.get("configurable", {}).get("prometheus_client")
    elk_client = config.get("configurable", {}).get("elk_client")
    elk_index = config.get("configurable", {}).get("elk_index", "")

    # Gather Prometheus metrics via PrometheusClient if available
    dns_metrics_raw: list = []
    ingress_metrics_raw: list = []
    if prometheus_client:
        try:
            dns_resp = await prometheus_client.query_instant("coredns_dns_requests_total")
            dns_metrics_raw = dns_resp.get("data", {}).get("result", []) if isinstance(dns_resp, dict) else []
        except Exception as exc:
            logger.debug("Prometheus DNS query failed: %s", exc)
            dns_metrics_raw = []
        try:
            ingress_resp = await prometheus_client.query_instant("ingress_5xx_rate")
            ingress_metrics_raw = ingress_resp.get("data", {}).get("result", []) if isinstance(ingress_resp, dict) else []
        except Exception as exc:
            logger.debug("Prometheus ingress query failed: %s", exc)
            ingress_metrics_raw = []

    # Gather logs via ElasticsearchClient if available
    logs_raw: list = []
    logs_total: int = 0
    if elk_client and elk_index:
        try:
            logs_resp = await elk_client.search(
                index=elk_index,
                body={"query": {"query_string": {"query": "coredns OR ingress"}}, "size": 50},
            )
            logs_raw = logs_resp.get("hits", {}).get("hits", [])[:50]
            logs_total = logs_resp.get("hits", {}).get("total", {}).get("value", 0)
        except Exception as exc:
            logger.debug("ELK search failed: %s", exc)
            logs_raw = []
            logs_total = 0

    # Gather data - services, endpoints, network policies via cluster_client
    services = await client.list_services()
    endpoints = await client.list_endpoints()
    network_policies = await client.list_network_policies()

    # Check for RBAC permission denials — only on cluster_client QueryResult objects
    rbac_anomalies = []
    rbac_denied = False
    rbac_counter = 0
    for result, resource_name in [
        (services, "services"), (endpoints, "endpoints"), (network_policies, "networkpolicies"),
    ]:
        if result.permission_denied:
            rbac_denied = True
            rbac_counter += 1
            rbac_anomalies.append(DomainAnomaly(
                domain="network",
                anomaly_id=f"rbac-network-{rbac_counter:03d}",
                description=f"Insufficient RBAC permissions to access {resource_name}. Required ClusterRole: view",
                evidence_ref=f"rbac/{resource_name}",
                severity="high",
            ))

    platform_caps = (
        "Full access: Routes, IngressControllers, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only. No Routes or IngressControllers."
    )

    data_payload = {
        "dns_metrics": dns_metrics_raw,
        "ingress_metrics": ingress_metrics_raw,
        "logs": logs_raw[:50],
        "services": services.data,
        "endpoints": endpoints.data,
        "network_policies": network_policies.data,
    }

    version_context = get_version_context(platform_version)
    truncation_note = ""

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
        logger.info("Budget exhausted for network, using heuristic")
        analysis = await _heuristic_analyze(data_payload, "network")
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_network", call_type="heuristic",
                fallback_used=True, success=True,
            ))
    else:
        # Try tool-calling ReAct loop first, fall back to heuristic single-pass
        try:
            initial_context = (
                "Analyze this Kubernetes cluster for network and ingress issues. "
                "Start by examining services, endpoints, network policies, and DNS/ingress metrics.\n\n"
                f"Platform: {platform} {platform_version}"
            )
            analysis = await asyncio.wait_for(
                _tool_calling_loop(system, initial_context, client,
                                   budget=budget, telemetry=telemetry),
                timeout=TOOL_CALL_TIMEOUT,
            )
        except Exception as e:
            logger.warning("Tool-calling failed for network, falling back to heuristic: %s", e)

        if not analysis:
            if budget and not budget.can_call():
                analysis = await _heuristic_analyze(data_payload, "network")
                if telemetry:
                    telemetry.record_call(LLMCallRecord(
                        agent_name="cluster_network", call_type="heuristic",
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
        domain="network",
        status=DomainStatus.PARTIAL if rbac_denied else DomainStatus.SUCCESS,
        failure_reason=FailureReason.RBAC_DENIED if rbac_denied else None,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(log_lines=logs_total > 50),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
