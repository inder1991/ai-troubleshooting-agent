"""3-stage synthesis pipeline: Merge -> Causal Reasoning -> Verdict."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import time

from src.agents.cluster.state import (
    DomainReport, DomainStatus, DomainAnomaly, CausalChain, CausalLink,
    BlastRadius, ClusterHealthReport,
)
from src.agents.cluster.command_validator import validate_kubectl_command, add_dry_run, generate_rollback
from src.agents.cluster.traced_node import traced_node
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

_VERDICT_SEVERITY_GUIDE = """
## Platform Health Classification
- CRITICAL: Any of: node NotReady, control plane operator unavailable, >50% pods in CrashLoopBackOff,
  data plane loss (zero service endpoints for critical services), etcd quorum loss
- DEGRADED: Any of: operator degraded, HPA at max with unmet targets, >20% pod restarts,
  PVC >90% capacity, partial scheduling failures, certificate expiring within 7 days
- HEALTHY: All operators available, all nodes Ready, workloads running at desired replicas,
  no high-severity anomalies
- UNKNOWN: Insufficient data to determine (>50% of domains FAILED or SKIPPED)

## Remediation Safety Rules
- ALWAYS include -n <namespace> in kubectl commands
- For destructive commands (delete, drain, scale-down), include --dry-run=client variant
- Mark risk_level: "high" for drain/delete/cordon, "medium" for scale/rollout, "safe" for get/describe
- Include rollback command for every non-read-only remediation step
"""

_VALID_DOMAINS = {"ctrl_plane", "node", "network", "storage", "rbac"}


def _compute_data_completeness(reports: list[DomainReport]) -> float:
    """Fraction of active (non-SKIPPED) domains that returned SUCCESS or PARTIAL."""
    active_reports = [r for r in reports if r.status != DomainStatus.SKIPPED]
    if not active_reports:
        return 0.0
    completed = sum(1 for r in active_reports if r.status in (DomainStatus.SUCCESS, DomainStatus.PARTIAL))
    return completed / len(active_reports)


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


_TOKEN_BUDGET = 60_000  # Conservative estimate; leaves room for system prompt + response


def _build_bounded_causal_prompt(
    anomalies: list,
    reports: list,
    search_space: dict,
    hypotheses: list,
    selection: dict | None = None,
) -> str:
    """Build causal reasoning prompt within token budget. Drops low-priority anomalies if needed."""
    TOKEN_BUDGET_CHARS = _TOKEN_BUDGET * 4  # 1 token ≈ 4 chars

    # Build truncation warning from domain reports
    truncation_warning = ""
    truncated_domains = []
    for r in reports:
        if hasattr(r, "truncation_flags"):
            tf = r.truncation_flags
            dropped = []
            if getattr(tf, "events", False):
                dropped.append(f"events (~{getattr(tf, 'events_dropped', '?')} items dropped)")
            if getattr(tf, "pods", False):
                dropped.append(f"pods (~{getattr(tf, 'pods_dropped', '?')} items dropped)")
            if getattr(tf, "nodes", False):
                dropped.append(f"nodes (~{getattr(tf, 'nodes_dropped', '?')} items dropped)")
            if dropped:
                truncated_domains.append(f"- {r.domain} domain: {', '.join(dropped)}")

    if truncated_domains:
        truncation_warning = (
            "\n⚠️  DATA COMPLETENESS WARNING:\n"
            "The following data sources were truncated before analysis:\n"
            + "\n".join(truncated_domains)
            + "\nRule: Do not assign confidence > 60% to findings that depend solely on "
              "truncated data sources. State the data gap explicitly in your reasoning.\n"
        )

    # Sort anomalies by priority: high → medium → low
    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_anomalies = sorted(
        anomalies,
        key=lambda a: (severity_order.get(a.get("severity", "low") if isinstance(a, dict)
                        else getattr(a, "severity", "low"), 2)),
    )

    # Include anomalies up to budget
    included = []
    omitted = 0
    running_chars = len(truncation_warning)
    for anomaly in sorted_anomalies:
        item_str = json.dumps(anomaly if isinstance(anomaly, dict) else anomaly.model_dump(mode="json"),
                               indent=2)
        if running_chars + len(item_str) > TOKEN_BUDGET_CHARS:
            omitted += 1
        else:
            included.append(anomaly if isinstance(anomaly, dict) else anomaly.model_dump(mode="json"))
            running_chars += len(item_str)

    omitted_note = ""
    if omitted:
        omitted_note = (
            f"\nNOTE: {omitted} lower-priority anomalies omitted (context limit reached). "
            "Do not claim exhaustive analysis.\n"
        )

    report_summaries = [
        {"domain": r.domain if hasattr(r, "domain") else r.get("domain"),
         "status": (r.status.value if hasattr(r.status, "value") else r.get("status"))
                   if hasattr(r, "status") else r.get("status"),
         "confidence": r.confidence if hasattr(r, "confidence") else r.get("confidence"),
         "anomaly_count": len(r.anomalies) if hasattr(r, "anomalies") else r.get("anomaly_count", 0),
         "ruled_out": (r.ruled_out if hasattr(r, "ruled_out") else r.get("ruled_out", []))}
        for r in reports
    ]

    # Build search space sections
    issue_clusters_summary = search_space.get("issue_clusters_summary", []) if search_space else []
    annotated_links = search_space.get("annotated_links", []) if search_space else []
    blocked_count = search_space.get("total_blocked", 0) if search_space else 0
    root_cands = search_space.get("root_candidates", []) if search_space else []

    cluster_section = ""
    if root_cands or annotated_links or blocked_count:
        cluster_section = f"""
## Pre-Correlated Issue Clusters
{json.dumps(issue_clusters_summary, indent=2)}

## Root Cause Hypothesis Seeds
These are pre-identified root cause candidates from cluster correlation. do NOT invent new root causes \
outside this list unless there is strong direct evidence.
{json.dumps(root_cands, indent=2)}

## Annotated Links
Links below have low confidence scores and should be treated as weak hints only.
{json.dumps(annotated_links, indent=2)}

## Blocked Links: {blocked_count} causal links were blocked by the firewall; do NOT propose these \
as causal relationships.
"""

    hyp_section = ""
    if hypotheses:
        hyp_section = f"""
## Pre-Ranked Hypotheses
{json.dumps(hypotheses[:10], indent=2)}
{json.dumps(selection or {}, indent=2)}
"""

    return (
        f"{truncation_warning}"
        f"Analyze these cross-domain anomalies and identify causal chains.\n\n"
        f"## Anomalies Found\n{json.dumps(included, indent=2)}\n"
        f"{omitted_note}"
        f"## Domain Report Summaries\n{json.dumps(report_summaries, indent=2)}\n"
        f"{cluster_section}"
        f"{hyp_section}"
    )


async def _llm_causal_reasoning(
    anomalies: list[DomainAnomaly],
    reports: list[DomainReport],
    search_space: dict | None = None,
    root_candidates: list[dict] | None = None,
    budget=None,
    telemetry=None,
    platform: str = "",
    namespace: str = "",
    cluster_url: str = "",
    store=None,
    session_id: str = "",
    **kwargs,
) -> dict:
    """Stage 2: LLM identifies cross-domain causal chains."""
    from src.agents.cluster.output_schemas import SUBMIT_CAUSAL_ANALYSIS_TOOL

    # Downgrade model when budget is low
    model = None
    if budget and budget.remaining_budget_pct() < 0.3:
        model = "claude-haiku-4-5-20251001"
        logger.info("Budget low (%.0f%% remaining), using Haiku for causal reasoning", budget.remaining_budget_pct() * 100)
    client = AnthropicClient(agent_name="cluster_synthesizer", model=model, session_id=session_id) if model else AnthropicClient(agent_name="cluster_synthesizer", session_id=session_id)

    # Merge root_candidates into search_space so the prompt builder can see them
    effective_search_space = dict(search_space) if search_space else {}
    if root_candidates:
        effective_search_space.setdefault("root_candidates", root_candidates)

    bounded_prompt = _build_bounded_causal_prompt(
        anomalies=[a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in anomalies],
        reports=reports,
        search_space=effective_search_space,
        hypotheses=kwargs.get("hypotheses", []),
        selection=kwargs.get("hypothesis_selection", {}),
    )

    cluster_context = (
        f"Cluster Context:\n"
        f"- Platform: {platform}\n"
        f"- Namespace: {namespace or 'all namespaces'}\n"
        f"- Cluster: {cluster_url or 'unknown'}\n\n"
    )
    system_prompt = (
        cluster_context
        + "You are a causal reasoning engine for cluster diagnostics. Be precise and evidence-based.\n\n"
        + CAUSAL_RULES + "\n"
        + "## Allowed Link Types\n"
        + "Use ONLY these link_type values in causal chains:\n"
        + "\n".join(f"- {lt}" for lt in CONSTRAINED_LINK_TYPES)
        + "\n\nYou MUST call submit_causal_analysis to return your analysis."
    )

    call_start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            client.chat_with_tools(
                system=system_prompt,
                messages=[{"role": "user", "content": bounded_prompt}],
                tools=[SUBMIT_CAUSAL_ANALYSIS_TOOL],
                max_tokens=3000,
                temperature=0.1,
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning("LLM causal reasoning timed out after 30s")
        return {"causal_chains": [], "uncorrelated_findings": [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in anomalies]}

    latency_ms = int((time.monotonic() - call_start) * 1000)
    usage = getattr(response, "usage", None)
    in_tok = usage.input_tokens if usage else 0
    out_tok = usage.output_tokens if usage else 0
    used_model = model or "claude-sonnet-4-20250514"

    if budget:
        budget.record(input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency_ms)
    if telemetry:
        telemetry.record_call(LLMCallRecord(
            agent_name="cluster_synthesizer", model=used_model,
            call_type="synthesis_causal", input_tokens=in_tok, output_tokens=out_tok,
            latency_ms=latency_ms, success=True,
        ))

    # Log to DiagnosticStore (fire-and-forget)
    if store is not None and session_id:
        _safe_store_write(store, {
            "session_id": session_id,
            "agent_name": "cluster_synthesizer",
            "model": used_model,
            "call_type": "synthesis_causal",
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "latency_ms": latency_ms,
            "success": True,
            "error": None,
            "fallback_used": False,
            "response_json": json.dumps([{"type": getattr(b, "type", "unknown"), **({"text": b.text} if hasattr(b, "text") else {"name": b.name, "input": b.input} if hasattr(b, "name") else {})} for b in response.content], default=str)[:2000],
            "created_at": time.time(),
        })

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_causal_analysis":
            return block.input

    logger.warning("Synthesizer causal reasoning: LLM did not call submit_causal_analysis")
    return {"causal_chains": [], "uncorrelated_findings": [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in anomalies]}


async def _llm_verdict(
    causal_chains: list[dict],
    reports: list[DomainReport],
    data_completeness: float,
    budget=None,
    telemetry=None,
    store=None,
    session_id: str = "",
    platform: str = "",
    namespace: str = "",
    cluster_url: str = "",
    **kwargs,
) -> dict:
    """Stage 3: LLM produces verdict and remediation."""
    from src.agents.cluster.output_schemas import SUBMIT_VERDICT_TOOL

    model = None
    if budget and budget.remaining_budget_pct() < 0.3:
        model = "claude-haiku-4-5-20251001"
        logger.info("Budget low (%.0f%% remaining), using Haiku for verdict", budget.remaining_budget_pct() * 100)
    client = AnthropicClient(agent_name="cluster_synthesizer", model=model, session_id=session_id) if model else AnthropicClient(agent_name="cluster_synthesizer", session_id=session_id)

    report_summaries = json.dumps([
        {"domain": r.domain, "status": r.status.value, "confidence": r.confidence}
        for r in reports
    ], indent=2)

    hypothesis_context = ""
    if kwargs.get("ranked_hypotheses"):
        top_hyps = kwargs["ranked_hypotheses"][:5]
        hypothesis_context = f"\n## Pre-Ranked Root Cause Hypotheses\n{json.dumps(top_hyps, indent=2)}\n"

    prompt = f"""Based on the causal analysis, produce a cluster health verdict.

## Causal Chains
{json.dumps(causal_chains, indent=2)}

## Data Completeness: {data_completeness:.0%}

## Domain Report Statuses
{report_summaries}
{hypothesis_context}
Note: re_dispatch_domains valid values are: ctrl_plane, node, network, storage, rbac"""

    system_prompt = (
        f"Platform: {platform}\nNamespace: {namespace or 'all'}\nCluster: {cluster_url or 'unknown'}\n\n"
        + _VERDICT_SEVERITY_GUIDE
        + "\nYou are a cluster health verdict engine. Issue a definitive verdict with remediation.\n"
          "You MUST call submit_verdict to return your verdict."
    )

    call_start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            client.chat_with_tools(
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                tools=[SUBMIT_VERDICT_TOOL],
                max_tokens=3000,
                temperature=0.1,
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning("LLM verdict timed out after 30s")
        return {
            "platform_health": "UNKNOWN",
            "blast_radius": {"summary": "Unable to determine", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
            "remediation": {"immediate": [], "long_term": []},
            "re_dispatch_needed": False,
            "re_dispatch_domains": [],
        }

    latency_ms = int((time.monotonic() - call_start) * 1000)
    usage = getattr(response, "usage", None)
    in_tok = usage.input_tokens if usage else 0
    out_tok = usage.output_tokens if usage else 0
    used_model = model or "claude-sonnet-4-20250514"

    if budget:
        budget.record(input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency_ms)
    if telemetry:
        telemetry.record_call(LLMCallRecord(
            agent_name="cluster_synthesizer", model=used_model,
            call_type="synthesis_verdict", input_tokens=in_tok, output_tokens=out_tok,
            latency_ms=latency_ms, success=True,
        ))

    # Log to DiagnosticStore (fire-and-forget)
    if store is not None and session_id:
        _safe_store_write(store, {
            "session_id": session_id,
            "agent_name": "cluster_synthesizer",
            "model": used_model,
            "call_type": "synthesis_verdict",
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "latency_ms": latency_ms,
            "success": True,
            "error": None,
            "fallback_used": False,
            "response_json": json.dumps([{"type": getattr(b, "type", "unknown"), **({"text": b.text} if hasattr(b, "text") else {"name": b.name, "input": b.input} if hasattr(b, "name") else {})} for b in response.content], default=str)[:2000],
            "created_at": time.time(),
        })

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_verdict":
            parsed = block.input
            raw_domains = parsed.get("re_dispatch_domains", [])
            parsed["re_dispatch_domains"] = [d for d in raw_domains if d in _VALID_DOMAINS]
            return parsed

    logger.warning("Synthesizer verdict: LLM did not call submit_verdict")
    return {
        "platform_health": "UNKNOWN",
        "blast_radius": {"summary": "Unable to determine", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
        "remediation": {"immediate": [], "long_term": []},
        "re_dispatch_needed": False,
        "re_dispatch_domains": [],
    }


@traced_node(timeout_seconds=60)
async def synthesize(state: dict, config: dict) -> dict:
    """LangGraph node: 3-stage synthesis pipeline."""
    diagnostic_id = state.get("diagnostic_id", "")
    platform = state.get("platform", "")
    platform_version = state.get("platform_version", "")

    # Reconstruct DomainReports from state
    reports = [DomainReport(**r) for r in state.get("domain_reports", [])]

    # Read hypothesis and diagnostic intelligence data from state
    ranked_hypotheses = state.get("ranked_hypotheses", [])
    hypothesis_selection = state.get("hypothesis_selection", {})
    diagnostic_issues = state.get("diagnostic_issues", [])

    # Apply critic validation: filter out dropped anomalies, downgrade severity
    critic_result = state.get("critic_result", {})

    # Filter out rejected hypotheses
    dropped = set(critic_result.get("dropped_hypotheses", []))
    valid_hypotheses = [h for h in ranked_hypotheses if h.get("hypothesis_id") not in dropped]

    if critic_result:
        dropped_ids = set(critic_result.get("dropped_anomaly_ids", []))
        downgraded_ids = set(critic_result.get("downgraded_anomaly_ids", []))
        for report in reports:
            report.anomalies = [
                a for a in report.anomalies if a.anomaly_id not in dropped_ids
            ]
            for a in report.anomalies:
                if a.anomaly_id in downgraded_ids:
                    a.severity = "medium"

    # Stage 1: Merge
    merged = _merge_reports(reports)
    data_completeness = _compute_data_completeness(reports)

    # Extract cluster-aware data from state
    issue_clusters = state.get("issue_clusters", [])
    causal_search_space = state.get("causal_search_space", {})
    root_candidates = [
        candidate
        for cluster in issue_clusters
        for candidate in cluster.get("root_candidates", [])
    ]
    annotated_links = causal_search_space.get("annotated_links", []) if causal_search_space else []
    blocked_count = causal_search_space.get("total_blocked", 0) if causal_search_space else 0
    issue_clusters_summary = [
        {
            "cluster_id": c["cluster_id"],
            "affected_resources": c["affected_resources"],
            "correlation_basis": c["correlation_basis"],
            "confidence": c["confidence"],
        }
        for c in issue_clusters
    ]

    # Embed the summary into search_space for the LLM prompt builder
    search_space_for_llm = dict(causal_search_space) if causal_search_space else {}
    if issue_clusters_summary:
        search_space_for_llm["issue_clusters_summary"] = issue_clusters_summary

    # Extract budget, telemetry, store, and session_id from config
    budget = config.get("configurable", {}).get("budget")
    telemetry = config.get("configurable", {}).get("telemetry")
    store = config.get("configurable", {}).get("store")

    # Stage 2: Causal Reasoning (skip if no anomalies)
    _ns_list = state.get("namespaces") or []
    causal_result: dict = {"causal_chains": [], "uncorrelated_findings": []}
    if merged["all_anomalies"]:
        causal_result = await _llm_causal_reasoning(
            merged["all_anomalies"],
            reports,
            search_space=search_space_for_llm or None,
            root_candidates=root_candidates or None,
            budget=budget,
            telemetry=telemetry,
            hypotheses=valid_hypotheses,
            hypothesis_selection=hypothesis_selection,
            platform=state.get("platform", ""),
            namespace=_ns_list[0] if _ns_list else "",
            cluster_url=state.get("cluster_url", ""),
            store=store,
            session_id=diagnostic_id,
        )

    # Stage 3: Verdict
    verdict = await _llm_verdict(
        causal_result.get("causal_chains", []), reports, data_completeness,
        budget=budget, telemetry=telemetry,
        store=store, session_id=diagnostic_id,
        platform=state.get("platform", ""),
        namespace=_ns_list[0] if _ns_list else "",
        cluster_url=state.get("cluster_url", ""),
        ranked_hypotheses=valid_hypotheses,
    )

    # Post-process remediation commands: validate, add dry-run, auto-fix namespace, generate rollback
    for step in verdict.get("remediation", {}).get("immediate", []):
        cmd = step.get("command", "")
        if cmd:
            validation = validate_kubectl_command(cmd)
            if not validation.valid:
                step["validation_errors"] = validation.errors
            if validation.is_destructive:
                step["risk_level"] = "high"
                step["dry_run"] = add_dry_run(cmd)
            if validation.missing_namespace and validation.fixed_command:
                step["command"] = validation.fixed_command
            if not step.get("rollback"):
                rollback = generate_rollback(cmd)
                if rollback:
                    step["rollback"] = rollback

    # Build health report with Pydantic validation safety
    try:
        blast_radius = BlastRadius(**verdict.get("blast_radius", {}))
    except Exception:
        logger.warning("Failed to parse blast_radius from LLM, using defaults")
        blast_radius = BlastRadius()

    causal_chains = []
    for c in causal_result.get("causal_chains", []):
        if isinstance(c, dict) and "chain_id" in c:
            try:
                causal_chains.append(CausalChain(**c))
            except Exception:
                logger.warning("Failed to parse causal chain: %s", c.get("chain_id", "?"))

    uncorrelated = []
    for f in causal_result.get("uncorrelated_findings", []):
        if isinstance(f, dict) and "domain" in f:
            try:
                uncorrelated.append(DomainAnomaly(**f))
            except Exception:
                logger.warning("Failed to parse uncorrelated finding in domain: %s", f.get("domain", "?"))

    health_report = ClusterHealthReport(
        diagnostic_id=diagnostic_id,
        platform=platform,
        platform_version=platform_version,
        platform_health=verdict.get("platform_health", "UNKNOWN"),
        data_completeness=data_completeness,
        blast_radius=blast_radius,
        causal_chains=causal_chains,
        uncorrelated_findings=uncorrelated,
        domain_reports=reports,
        remediation=verdict.get("remediation", {}),
        execution_metadata={
            "re_dispatch_count": state.get("re_dispatch_count", 0),
            "agents_succeeded": sum(1 for r in reports if r.status == DomainStatus.SUCCESS),
            "agents_failed": sum(1 for r in reports if r.status == DomainStatus.FAILED),
            "blocked_count": blocked_count,
            "annotated_count": len(annotated_links),
        },
    )

    # Tiered output from diagnostic_issues
    critical_incidents = []
    other_findings = []
    symptom_map = {}

    for issue in diagnostic_issues:
        issue_state = issue.get("state", "EXISTING")
        if issue.get("is_symptom"):
            symptom_map[issue["issue_id"]] = issue.get("root_cause_id", "")
        elif issue_state in ("ACTIVE_DISRUPTION", "WORSENING", "NEW"):
            if len(critical_incidents) < 3:
                critical_incidents.append(issue)
            else:
                other_findings.append(issue)
        else:
            other_findings.append(issue)

    health_report.critical_incidents = critical_incidents
    health_report.other_findings = other_findings
    health_report.symptom_map = symptom_map
    health_report.ranked_hypotheses = valid_hypotheses[:5]
    health_report.hypothesis_selection = hypothesis_selection
    health_report.signals_count = len(state.get("normalized_signals", []))
    health_report.pattern_matches_count = len(state.get("pattern_matches", []))
    diag_graph = state.get("diagnostic_graph", {})
    health_report.diagnostic_graph_node_count = len(diag_graph.get("nodes", {}))
    health_report.diagnostic_graph_edge_count = len(diag_graph.get("edges", []))
    # Build lifecycle summary
    lifecycle_summary = {}
    for issue in diagnostic_issues:
        s = issue.get("state", "EXISTING")
        lifecycle_summary[s] = lifecycle_summary.get(s, 0) + 1
    health_report.issue_lifecycle_summary = lifecycle_summary

    if not health_report.remediation.get("immediate"):
        logger.warning("No immediate remediations in health report")
    if not health_report.causal_chains:
        logger.warning("No causal chains identified")
    if health_report.data_completeness < 0.5:
        logger.warning("Low data completeness: %.0f%%", health_report.data_completeness * 100)

    re_dispatch_needed = verdict.get("re_dispatch_needed", False)
    re_dispatch_domains = verdict.get("re_dispatch_domains", []) if re_dispatch_needed else []

    result = {
        "health_report": health_report.model_dump(mode="json"),
        "causal_chains": [c.model_dump(mode="json") for c in health_report.causal_chains],
        "uncorrelated_findings": [f.model_dump(mode="json") for f in health_report.uncorrelated_findings],
        "data_completeness": data_completeness,
        "phase": "complete",
        "re_dispatch_domains": re_dispatch_domains,
    }

    # 1.1: Increment re_dispatch_count when re-dispatch is triggered
    if re_dispatch_domains:
        result["re_dispatch_count"] = state.get("re_dispatch_count", 0) + 1

    return result
