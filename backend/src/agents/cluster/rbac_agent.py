"""RBAC & Security diagnostic agent node."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import TYPE_CHECKING, Any

from anthropic import RateLimitError, APITimeoutError

from src.agents.cluster.state import DomainReport, DomainStatus, DomainAnomaly, TruncationFlags, FailureReason
from src.agents.cluster.traced_node import traced_node
from src.agents.cluster.tools import get_tools_for_agent, get_version_context
from src.agents.cluster.tool_executor import execute_tool_call
from src.agents.cluster_client.base import QueryResult, OBJECT_CAPS
from src.utils.llm_client import AnthropicClient
from src.utils.llm_telemetry import LLMCallRecord
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

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
_MAX_RBAC_ITEMS = 100

_SYSTEM_PROMPT = """You are the RBAC & Security diagnostic agent for DebugDuck.
You analyze: ServiceAccount misconfigs, role binding issues, pods running as default ServiceAccount,
excessive permissions, orphaned roles.

Platform: {platform} {platform_version}
{platform_capabilities}
{version_context}

Analyze the provided RBAC and security data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this RBAC and security data and produce a JSON response:

## Data Collected
{data_json}
{truncation_note}

## Required JSON Response Format
{{
  "anomalies": [
    {{"domain": "rbac", "anomaly_id": "rbac-NNN", "description": "...", "evidence_ref": "ev-rbac-NNN", "severity": "high|medium|low"}}
  ],
  "ruled_out": ["list of things checked and found healthy"],
  "confidence": 0-100
}}

Rules:
- Only report anomalies you have evidence for
- ServiceAccounts with no bound roles = low severity (potential orphan)
- RoleBindings referencing non-existent roles = high severity (broken binding)
- Pods running as default ServiceAccount = medium severity (security risk, no least-privilege)
- ClusterRoleBindings granting cluster-admin to non-system ServiceAccounts = high severity (excessive permissions)
- Orphaned roles (roles with no bindings referencing them) = low severity
- ServiceAccounts with automountServiceAccountToken=true when not needed = low severity
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage
- ruled_out is important -- shows thoroughness"""


async def _llm_analyze(system: str, prompt: str, session_id: str = "") -> dict:
    """Single-pass LLM call using structured tool output. Returns findings dict."""
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    try:
        client = AnthropicClient(agent_name="cluster_rbac", session_id=session_id)
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
    except Exception as e:
        logger.error("_llm_analyze failed: %s", e, extra={"action": "llm_analyze_error", "extra": str(e)})
    return {"anomalies": [], "ruled_out": [], "confidence": 0}


async def _heuristic_analyze(data_payload: dict, domain: str = "rbac") -> dict:
    """Deterministic rule-based analysis for RBAC. No LLM calls."""
    anomalies = []
    ruled_out = []

    # Build a set of bound role names for orphan detection
    bound_roles = set()
    for rb in data_payload.get("role_bindings", []):
        role_ref = rb.get("role_ref", rb.get("roleRef", {}))
        if isinstance(role_ref, dict):
            bound_roles.add(role_ref.get("name", ""))
        elif isinstance(role_ref, str):
            bound_roles.add(role_ref)

    # Check for default ServiceAccount usage in pods (via service_accounts data)
    for sa in data_payload.get("service_accounts", []):
        sa_name = sa.get("name", "unknown")
        ns = sa.get("namespace", "default")
        if sa_name == "default":
            # Check if any pods are using it (heuristic: just flag it)
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Default ServiceAccount in namespace {ns} may be used by workloads (no least-privilege)",
                "evidence_ref": f"serviceaccount/{ns}/default",
                "severity": "medium",
            })

    # Check role bindings for references to non-existent roles
    existing_roles = {r.get("name", "") for r in data_payload.get("roles", [])}
    existing_cluster_roles = {r.get("name", "") for r in data_payload.get("cluster_roles", [])}
    all_known_roles = existing_roles | existing_cluster_roles

    for rb in data_payload.get("role_bindings", []):
        rb_name = rb.get("name", "unknown")
        ns = rb.get("namespace", "")
        role_ref = rb.get("role_ref", rb.get("roleRef", {}))
        ref_name = role_ref.get("name", "") if isinstance(role_ref, dict) else str(role_ref)
        if ref_name and ref_name not in all_known_roles:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"RoleBinding {ns}/{rb_name} references non-existent role '{ref_name}' (dangling binding)",
                "evidence_ref": f"rolebinding/{ns}/{rb_name}",
                "severity": "high",
            })

        # Check for cluster-admin grants to non-system SAs
        subjects = rb.get("subjects", [])
        for subj in subjects:
            if (subj.get("kind") == "ServiceAccount"
                    and ref_name == "cluster-admin"
                    and not subj.get("namespace", "").startswith("kube-")
                    and not subj.get("namespace", "").startswith("openshift-")):
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"ServiceAccount {subj.get('namespace','')}/{subj.get('name','')} has cluster-admin (excessive permissions)",
                    "evidence_ref": f"rolebinding/{ns}/{rb_name}",
                    "severity": "high",
                })

    # Check for orphaned roles
    for role in data_payload.get("roles", []):
        role_name = role.get("name", "unknown")
        ns = role.get("namespace", "")
        if role_name not in bound_roles and not role_name.startswith("system:"):
            ruled_out.append(f"Role {ns}/{role_name} has no bindings (potential orphan)")

    confidence = 50 if anomalies else 70
    return {"anomalies": anomalies, "ruled_out": ruled_out, "confidence": confidence}


async def _tool_calling_loop(system: str, initial_context: str, cluster_client,
                              budget=None, telemetry=None, store=None, session_id: str = "") -> dict | None:
    """ReAct tool-calling loop for rbac agent. Returns parsed findings dict or None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    llm = AnthropicClient(agent_name="cluster_rbac", model="claude-haiku-4-5-20251001", session_id=session_id)
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL

    base_tools = get_tools_for_agent("rbac")
    # Replace unschema'd submit_findings with SUBMIT_DOMAIN_FINDINGS_TOOL (schema-enforced)
    tools = [t for t in base_tools if t.get("name") != "submit_findings"]
    tools.append(SUBMIT_DOMAIN_FINDINGS_TOOL)

    messages = [{"role": "user", "content": initial_context}]
    tool_call_count = 0
    retry_count = 0

    for iteration in range(MAX_TOOL_CALLS):
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
                    agent_name="cluster_rbac", model="claude-haiku-4-5-20251001",
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
                    agent_name="cluster_rbac", model="claude-haiku-4-5-20251001",
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
                agent_name="cluster_rbac", model="claude-haiku-4-5-20251001",
                call_type="tool_calling", input_tokens=in_tok, output_tokens=out_tok,
                latency_ms=latency_ms, success=True,
            ))

        # Log to DiagnosticStore (fire-and-forget)
        if store is not None and session_id:
            _safe_store_write(store, {
                "session_id": session_id,
                "agent_name": "cluster_rbac",
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
                {"type": "tool_result", "tool_use_id": tu.id,
                 "content": "Tool budget exhausted. Please submit your findings now using submit_domain_findings."}
                for tu in tool_uses
            ]})
            continue

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_uses:
            try:
                result_str = await execute_tool_call(tu.name, tu.input, cluster_client, tool_call_count)
            except Exception as e:
                logger.error("Tool call %s failed: %s", tu.name, e,
                             extra={"action": "tool_call_error", "extra": str(e)})
                result_str = json.dumps({"error": f"Tool execution failed: {e}"})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
            })
            tool_call_count += 1

        messages.append({"role": "user", "content": tool_results})

    return None


@traced_node(timeout_seconds=60)
async def rbac_agent(state: dict, config: RunnableConfig) -> dict:
    """LangGraph node: RBAC & Security diagnostics."""
    start_ms = time.monotonic()
    client = config.get("configurable", {}).get("cluster_client")
    if not client:
        return {"domain_reports": [DomainReport(
            domain="rbac", status=DomainStatus.FAILED,
            failure_reason=FailureReason.EXCEPTION,
        ).model_dump(mode="json")]}

    platform = state.get("platform", "kubernetes")
    platform_version = state.get("platform_version", "")

    # Gather data
    roles = await client.list_roles()
    role_bindings = await client.list_role_bindings()
    cluster_roles = await client.list_cluster_roles()
    service_accounts = await client.list_service_accounts()

    # Check for RBAC permission denials
    rbac_anomalies = []
    rbac_denied = False
    rbac_counter = 0
    for result, resource_name in [
        (roles, "roles"), (role_bindings, "rolebindings"),
        (cluster_roles, "clusterroles"), (service_accounts, "serviceaccounts"),
    ]:
        if result.permission_denied:
            rbac_denied = True
            rbac_counter += 1
            rbac_anomalies.append(DomainAnomaly(
                domain="rbac",
                anomaly_id=f"rbac-perm-{rbac_counter:03d}",
                description=f"Insufficient RBAC permissions to access {resource_name}. Required ClusterRole: view",
                evidence_ref=f"rbac/{resource_name}",
                severity="high",
            ))

    platform_caps = (
        "Full access: SecurityContextConstraints, plus standard K8s RBAC."
        if platform == "openshift"
        else "Standard K8s RBAC only."
    )

    data_payload = {
        "roles": roles.data[:_MAX_RBAC_ITEMS],
        "role_bindings": role_bindings.data[:_MAX_RBAC_ITEMS],
        "cluster_roles": cluster_roles.data[:_MAX_RBAC_ITEMS],
        "service_accounts": service_accounts.data[:_MAX_RBAC_ITEMS],
    }

    truncation_note = ""
    capped_sources = []
    if len(roles.data) > _MAX_RBAC_ITEMS:
        capped_sources.append(f"roles ({len(roles.data)} \u2192 {_MAX_RBAC_ITEMS})")
    if len(role_bindings.data) > _MAX_RBAC_ITEMS:
        capped_sources.append(f"role_bindings ({len(role_bindings.data)} \u2192 {_MAX_RBAC_ITEMS})")
    if len(cluster_roles.data) > _MAX_RBAC_ITEMS:
        capped_sources.append(f"cluster_roles ({len(cluster_roles.data)} \u2192 {_MAX_RBAC_ITEMS})")
    if len(service_accounts.data) > _MAX_RBAC_ITEMS:
        capped_sources.append(f"service_accounts ({len(service_accounts.data)} \u2192 {_MAX_RBAC_ITEMS})")
    if capped_sources:
        truncation_note = "\u26a0\ufe0f Data truncation: " + "; ".join(capped_sources)

    version_context = get_version_context(platform_version)

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
        logger.info("Budget exhausted for rbac, using heuristic")
        analysis = await _heuristic_analyze(data_payload, "rbac")
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_rbac", call_type="heuristic",
                fallback_used=True, success=True,
            ))
        if store is not None and diagnostic_id:
            _safe_store_write(store, {
                "session_id": diagnostic_id,
                "agent_name": "cluster_rbac",
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
                f"- Roles: {len(roles.data)} found\n"
                f"- RoleBindings: {len(role_bindings.data)} found\n"
                f"- ClusterRoles: {len(cluster_roles.data)} found\n"
                f"- ServiceAccounts: {len(service_accounts.data)} found\n"
                f"{truncation_note}\n\n"
                f"Use tools to investigate specific anomalies in depth. "
                f"Do NOT re-fetch data that is already provided above.\n"
                f"Start by examining the most critical anomalies and call submit_domain_findings when done."
            )
            initial_context = (
                f"Analyze this Kubernetes cluster for RBAC and security issues.\n\n"
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
            logger.warning("Tool-calling failed for rbac, falling back to heuristic: %s", e)

        if not analysis:
            if budget and not budget.can_call():
                analysis = await _heuristic_analyze(data_payload, "rbac")
                if telemetry:
                    telemetry.record_call(LLMCallRecord(
                        agent_name="cluster_rbac", call_type="heuristic",
                        fallback_used=True, success=True,
                    ))
                if store is not None and diagnostic_id:
                    _safe_store_write(store, {
                        "session_id": diagnostic_id,
                        "agent_name": "cluster_rbac",
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
        domain="rbac",
        status=DomainStatus.PARTIAL if rbac_denied else DomainStatus.SUCCESS,
        failure_reason=FailureReason.RBAC_DENIED if rbac_denied else None,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
