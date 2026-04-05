"""Node & Capacity diagnostic agent node."""

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

_SYSTEM_PROMPT = """You are the Node & Capacity diagnostic agent for DebugDuck.
You analyze: node conditions (DiskPressure, MemoryPressure, PIDPressure, NotReady), resource utilization,
pod evictions, scheduling failures, resource quotas, and capacity planning.

You also analyze workload health: Deployment replica mismatches, stuck rollouts, StatefulSet ordered pod
failures, DaemonSet unavailable nodes, HPA scaling limits, Job failures, and CronJob scheduling issues.

For OpenShift, you also analyze BuildConfig failures and ImageStream import issues.

Platform: {platform} {platform_version}
{platform_capabilities}
{version_context}

Analyze the provided node and workload data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this node and capacity data and produce a JSON response:

## Data Collected
{data_json}
{truncation_note}

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
- Deployment replicas_ready < replicas_desired = stuck rollout (high severity)
- DaemonSet number_unavailable > 0 = not running on all nodes (medium severity)
- HPA at max replicas with unmet target = scaling bottleneck (high severity)
- StatefulSet replicas_ready < replicas_desired = ordered pod failure (high severity)
- PDB with disruptionsAllowed=0 blocks all voluntary disruptions (high severity)
- Pods without resource requests = unpredictable scheduling (medium severity)
- Pods without resource limits = unlimited consumption risk (medium severity)
- Pods with requests > limits = invalid config (high severity)
- Check node resource overcommit ratio
- Cluster autoscaler pod not running = scaling disabled (high severity if pending pods exist)
- High number of pending pods with no autoscaler = capacity issue (high severity)
- Failed jobs with backoffLimit exceeded = high severity
- CronJobs with suspend=true — note for awareness (low severity)
- CronJobs not running on schedule — medium severity
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage"""


async def _llm_analyze(system: str, prompt: str, session_id: str = "") -> dict:
    """Single-pass LLM call using structured tool output. Returns findings dict."""
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    client = AnthropicClient(agent_name="cluster_node", session_id=session_id)
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


async def _heuristic_analyze(data_payload: dict, domain: str = "node") -> dict:
    """Deterministic rule-based analysis for node/capacity. No LLM calls."""
    anomalies = []
    ruled_out = []

    # Check nodes
    for node in data_payload.get("nodes", []):
        node_name = node.get("name", "unknown")
        if node.get("status") == "NotReady":
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Node {node_name} is NotReady",
                "evidence_ref": f"node/{node_name}",
                "severity": "high",
            })
        else:
            ruled_out.append(f"Node {node_name} status OK")

        if node.get("disk_pressure"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Node {node_name} has DiskPressure",
                "evidence_ref": f"node/{node_name}",
                "severity": "high",
            })
        else:
            ruled_out.append(f"Node {node_name} disk pressure OK")

        if node.get("memory_pressure"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Node {node_name} has MemoryPressure",
                "evidence_ref": f"node/{node_name}",
                "severity": "high",
            })
        if node.get("pid_pressure"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Node {node_name} has PIDPressure",
                "evidence_ref": f"node/{node_name}",
                "severity": "medium",
            })

    # Check deployments for stuck rollouts
    for dep in data_payload.get("deployments", []):
        dep_name = dep.get("name", "unknown")
        ns = dep.get("namespace", "default")
        desired = dep.get("replicas_desired", dep.get("replicas", 0))
        ready = dep.get("replicas_ready", dep.get("ready_replicas", 0))
        if desired and ready < desired:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Deployment {ns}/{dep_name} has {ready}/{desired} replicas ready (stuck rollout)",
                "evidence_ref": f"deployment/{ns}/{dep_name}",
                "severity": "high",
            })
        if dep.get("stuck_rollout"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Deployment {ns}/{dep_name} has a stuck rollout",
                "evidence_ref": f"deployment/{ns}/{dep_name}",
                "severity": "high",
            })

    # Check daemonsets
    for ds in data_payload.get("daemonsets", []):
        ds_name = ds.get("name", "unknown")
        ns = ds.get("namespace", "default")
        unavailable = ds.get("number_unavailable", 0)
        if unavailable and unavailable > 0:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"DaemonSet {ns}/{ds_name} has {unavailable} unavailable nodes",
                "evidence_ref": f"daemonset/{ns}/{ds_name}",
                "severity": "medium",
            })

    # Check warning events volume
    warning_events = [e for e in data_payload.get("events", []) if e.get("type") == "Warning"]
    if len(warning_events) > 20:
        anomalies.append({
            "domain": domain,
            "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
            "description": f"High volume of warning events ({len(warning_events)} warnings)",
            "evidence_ref": "events/warnings",
            "severity": "medium",
        })

    confidence = 50 if anomalies else 70
    return {"anomalies": anomalies, "ruled_out": ruled_out, "confidence": confidence}


async def _tool_calling_loop(system: str, initial_context: str, cluster_client,
                              budget=None, telemetry=None, store=None, session_id: str = "") -> dict | None:
    """ReAct tool-calling loop for node agent. Returns parsed findings dict or None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    llm = AnthropicClient(agent_name="cluster_node", model="claude-haiku-4-5-20251001", session_id=session_id)
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    base_tools = get_tools_for_agent("node")
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
                    agent_name="cluster_node", model="claude-haiku-4-5-20251001",
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
                    agent_name="cluster_node", model="claude-haiku-4-5-20251001",
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
                agent_name="cluster_node", model="claude-haiku-4-5-20251001",
                call_type="tool_calling", input_tokens=in_tok, output_tokens=out_tok,
                latency_ms=latency_ms, success=True,
            ))

        # Log to DiagnosticStore (fire-and-forget)
        if store is not None and session_id:
            _safe_store_write(store, {
                "session_id": session_id,
                "agent_name": "cluster_node",
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

    # Workload health
    deployments = await client.list_deployments()
    statefulsets = await client.list_statefulsets()
    daemonsets = await client.list_daemonsets()
    hpas = await client.list_hpas()
    pdbs = await client.list_pdbs()
    jobs = await client.list_jobs()
    cronjobs = await client.list_cronjobs()

    # Check for RBAC permission denials
    rbac_anomalies = []
    rbac_denied = False
    rbac_counter = 0
    for result, resource_name in [
        (nodes, "nodes"), (events, "events"), (pods, "pods"),
        (deployments, "deployments"), (statefulsets, "statefulsets"),
        (daemonsets, "daemonsets"), (hpas, "horizontalpodautoscalers"),
        (pdbs, "poddisruptionbudgets"),
        (jobs, "jobs"), (cronjobs, "cronjobs"),
    ]:
        if result.permission_denied:
            rbac_denied = True
            rbac_counter += 1
            rbac_anomalies.append(DomainAnomaly(
                domain="node",
                anomaly_id=f"rbac-node-{rbac_counter:03d}",
                description=f"Insufficient RBAC permissions to access {resource_name}. Required ClusterRole: view",
                evidence_ref=f"rbac/{resource_name}",
                severity="high",
            ))

    platform_caps = (
        "Full access: MachineSets, MachineConfigPools, BuildConfigs, ImageStreams, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only. No MachineSets, MachineConfigPools, BuildConfigs, or ImageStreams."
    )

    # Cluster autoscaler detection
    autoscaler_pods = [p for p in pods.data if "autoscaler" in p.get("name", "")]
    pending_metrics = await client.query_prometheus("kube_pod_status_phase{phase='Pending'}")

    events_total = len(events.data)
    events_capped = events.data[:100]
    pods_total = len(pods.data)
    pods_capped = pods.data[:50]

    data_payload = {
        "nodes": nodes.data,
        "events": events_capped,
        "top_pods": pods_capped,
        "deployments": deployments.data,
        "statefulsets": statefulsets.data,
        "daemonsets": daemonsets.data,
        "hpas": hpas.data,
        "pdbs": pdbs.data,
        "jobs": jobs.data,
        "cronjobs": cronjobs.data,
        "autoscaler_pods": autoscaler_pods,
        "pending_pod_metrics": pending_metrics.data,
    }

    # Enrich with Prometheus utilization metrics if client is available
    prometheus_client = config.get("configurable", {}).get("prometheus_client")
    if prometheus_client:
        try:
            cpu_result = await prometheus_client.query_instant(
                'sum by (node) (rate(node_cpu_seconds_total{mode!="idle"}[5m])) / '
                'sum by (node) (machine_cpu_cores) * 100'
            )
            data_payload["prometheus_node_cpu"] = cpu_result.get("data", {}).get("result", [])
        except Exception as exc:
            logger.debug("Prometheus node CPU query failed: %s", exc)
        try:
            mem_result = await prometheus_client.query_instant(
                '(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / '
                'node_memory_MemTotal_bytes * 100'
            )
            data_payload["prometheus_node_memory"] = mem_result.get("data", {}).get("result", [])
        except Exception as exc:
            logger.debug("Prometheus node memory query failed: %s", exc)

    # OpenShift-specific data
    if platform == "openshift":
        build_configs = await client.get_build_configs()
        image_streams = await client.get_image_streams()
        if build_configs.data:
            data_payload["build_configs"] = build_configs.data
        if image_streams.data:
            data_payload["image_streams"] = image_streams.data

    version_context = get_version_context(platform_version)
    truncation_parts = []
    if events_total > 100:
        truncation_parts.append(f"events truncated to 100 of {events_total}")
    if events.truncated:
        truncation_parts.append(f"events pre-truncated by API ({events.total_available} total, {events.returned} returned)")
    if pods_total > 50:
        truncation_parts.append(f"pods truncated to 50 of {pods_total}")
    if pods.truncated:
        truncation_parts.append(f"pods pre-truncated by API ({pods.total_available} total, {pods.returned} returned)")
    if nodes.truncated:
        truncation_parts.append(f"nodes pre-truncated by API ({nodes.total_available} total, {nodes.returned} returned)")
    truncation_note = ""
    if truncation_parts:
        truncation_note = "\n⚠️ Data truncation: " + "; ".join(truncation_parts)

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
        logger.info("Budget exhausted for node, using heuristic")
        analysis = await _heuristic_analyze(data_payload, "node")
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_node", call_type="heuristic",
                fallback_used=True, success=True,
            ))
        if store is not None and diagnostic_id:
            _safe_store_write(store, {
                "session_id": diagnostic_id,
                "agent_name": "cluster_node",
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
            initial_context = (
                "Analyze this Kubernetes cluster for node and capacity issues. "
                "Start by examining nodes, pods, deployments, and HPAs for resource pressure, "
                "scheduling failures, and workload health.\n\n"
                f"Platform: {platform} {platform_version}"
            )
            analysis = await asyncio.wait_for(
                _tool_calling_loop(system, initial_context, client,
                                   budget=budget, telemetry=telemetry,
                                   store=store, session_id=diagnostic_id),
                timeout=TOOL_CALL_TIMEOUT,
            )
        except Exception as e:
            logger.warning("Tool-calling failed for node, falling back to heuristic: %s", e)

        if not analysis:
            if budget and not budget.can_call():
                analysis = await _heuristic_analyze(data_payload, "node")
                if telemetry:
                    telemetry.record_call(LLMCallRecord(
                        agent_name="cluster_node", call_type="heuristic",
                        fallback_used=True, success=True,
                    ))
                if store is not None and diagnostic_id:
                    _safe_store_write(store, {
                        "session_id": diagnostic_id,
                        "agent_name": "cluster_node",
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
        domain="node",
        status=DomainStatus.PARTIAL if rbac_denied else DomainStatus.SUCCESS,
        failure_reason=FailureReason.RBAC_DENIED if rbac_denied else None,
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
