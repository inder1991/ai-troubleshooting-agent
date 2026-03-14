"""3-stage synthesis pipeline: Merge -> Causal Reasoning -> Verdict."""

from __future__ import annotations

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


async def _llm_causal_reasoning(
    anomalies: list[DomainAnomaly],
    reports: list[DomainReport],
    search_space: dict | None = None,
    root_candidates: list[dict] | None = None,
    budget=None,
    telemetry=None,
    **kwargs,
) -> dict:
    """Stage 2: LLM identifies cross-domain causal chains."""
    # Downgrade model when budget is low
    model = None
    if budget and budget.remaining_budget_pct() < 0.3:
        model = "claude-haiku-4-5-20251001"
        logger.info("Budget low (%.0f%% remaining), using Haiku for causal reasoning", budget.remaining_budget_pct() * 100)
    client = AnthropicClient(agent_name="cluster_synthesizer", model=model) if model else AnthropicClient(agent_name="cluster_synthesizer")

    anomaly_data = [a.model_dump(mode="json") for a in anomalies]
    report_summaries = [
        {"domain": r.domain, "status": r.status.value, "confidence": r.confidence, "anomaly_count": len(r.anomalies)}
        for r in reports
    ]

    # Build cluster-aware sections
    issue_clusters_summary = search_space.get("issue_clusters_summary", []) if search_space else []
    annotated_links = search_space.get("annotated_links", []) if search_space else []
    blocked_count = search_space.get("total_blocked", 0) if search_space else 0
    root_cands = root_candidates or []

    cluster_section = ""
    if root_cands or annotated_links or blocked_count:
        cluster_section = f"""
## Pre-Correlated Issue Clusters
{json.dumps(issue_clusters_summary, indent=2)}

## Root Cause Hypothesis Seeds (from deterministic correlator)
{json.dumps(root_cands, indent=2)}
Use these as starting anchors. Refine or adjust confidence, but do NOT invent new root causes unless evidence strongly supports it.

## Annotated Links (low confidence — investigate carefully)
{json.dumps(annotated_links, indent=2)}
These links passed structural validation but have low confidence based on observed evidence. Weight them accordingly.

## Blocked Links (excluded — do NOT propose these)
{blocked_count} causal links were blocked by structural invariants and excluded from your input.
"""

    # Include pre-ranked hypotheses if available
    hypotheses = kwargs.get("hypotheses", [])
    selection = kwargs.get("hypothesis_selection", {})
    hypotheses_section = ""
    if hypotheses:
        hypotheses_section = f"""
## Pre-Ranked Root Cause Hypotheses (from deterministic engine)
{json.dumps(hypotheses[:10], indent=2)}

## Hypothesis Selection
{json.dumps(selection, indent=2)}

The deterministic analysis engine has identified and ranked these root cause hypotheses.
Your job is to:
1. Explain the top hypothesis in clear natural language for an SRE
2. If selection_method is 'ambiguous_needs_llm', choose between the close candidates
3. Generate remediation for the top 3 root causes
4. Flag anything the engine may have missed (low confidence addendum)
"""

    prompt = f"""Analyze these cross-domain anomalies and identify causal chains.

## Anomalies Found
{json.dumps(anomaly_data, indent=2)}

## Domain Report Summaries
{json.dumps(report_summaries, indent=2)}
{cluster_section}
{hypotheses_section}
## Allowed Link Types
{json.dumps(CONSTRAINED_LINK_TYPES)}

{CAUSAL_RULES}

## Required JSON Response
{{
  "causal_chains": [
    {{
      "chain_id": "cc-NNN",
      "confidence": 0.0-1.0,
      "root_cause": {{"domain": "...", "anomaly_id": "...", "description": "...", "evidence_ref": "..."}},
      "cascading_effects": [
        {{"order": 1, "domain": "...", "anomaly_id": "...", "description": "...", "link_type": "...", "evidence_ref": "..."}}
      ]
    }}
  ],
  "uncorrelated_findings": [
    {{"domain": "...", "anomaly_id": "...", "description": "...", "evidence_ref": "...", "severity": "..."}}
  ]
}}"""

    call_start = time.monotonic()
    response = await client.chat(
        prompt=prompt,
        system="You are a causal reasoning engine for cluster diagnostics. Be precise and evidence-based.",
        max_tokens=3000,
        temperature=0.1,
    )
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

    text = response.text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_synthesizer", call_type="synthesis_causal",
                error="parse_error", success=False,
            ))
        return {"causal_chains": [], "uncorrelated_findings": []}


async def _llm_verdict(
    causal_chains: list[dict],
    reports: list[DomainReport],
    data_completeness: float,
    budget=None,
    telemetry=None,
) -> dict:
    """Stage 3: LLM produces verdict and remediation."""
    model = None
    if budget and budget.remaining_budget_pct() < 0.3:
        model = "claude-haiku-4-5-20251001"
        logger.info("Budget low (%.0f%% remaining), using Haiku for verdict", budget.remaining_budget_pct() * 100)
    client = AnthropicClient(agent_name="cluster_synthesizer", model=model) if model else AnthropicClient(agent_name="cluster_synthesizer")

    report_summaries = json.dumps([
        {"domain": r.domain, "status": r.status.value, "confidence": r.confidence}
        for r in reports
    ], indent=2)

    prompt = f"""Based on the causal analysis, produce a cluster health verdict.

## Causal Chains
{json.dumps(causal_chains, indent=2)}

## Data Completeness: {data_completeness:.0%}

## Domain Report Statuses
{report_summaries}

## Required JSON Response
{{
  "platform_health": "HEALTHY|DEGRADED|CRITICAL",
  "blast_radius": {{
    "summary": "...",
    "affected_namespaces": 0,
    "affected_pods": 0,
    "affected_nodes": 0
  }},
  "remediation": {{
    "immediate": [{{
      "command": "kubectl ...",
      "description": "...",
      "risk_level": "low|medium|high",
      "rollback": "kubectl ... (command to undo this action)",
      "pre_check": "kubectl ... (command to run before executing)",
      "verify": "kubectl ... (command to confirm fix worked)",
      "expected_output": "description of what verify should show"
    }}],
    "long_term": [{{"description": "...", "effort_estimate": "..."}}]
  }},
  "re_dispatch_needed": false
}}"""

    call_start = time.monotonic()
    response = await client.chat(
        prompt=prompt,
        system="You are a cluster health verdict engine. Be actionable and precise. "
               "ALWAYS include -n <namespace> in kubectl commands for namespaced resources. "
               "Never use default namespace implicitly.",
        max_tokens=2000,
        temperature=0.1,
    )
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

    text = response.text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        if telemetry:
            telemetry.record_call(LLMCallRecord(
                agent_name="cluster_synthesizer", call_type="synthesis_verdict",
                error="parse_error", success=False,
            ))
        return {
            "platform_health": "UNKNOWN",
            "blast_radius": {"summary": "Unable to determine", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
            "remediation": {"immediate": [], "long_term": []},
            "re_dispatch_needed": False,
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

    # Extract budget and telemetry from config
    budget = config.get("configurable", {}).get("budget")
    telemetry = config.get("configurable", {}).get("telemetry")

    # Stage 2: Causal Reasoning (skip if no anomalies)
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
        )

    # Stage 3: Verdict
    verdict = await _llm_verdict(
        causal_result.get("causal_chains", []), reports, data_completeness,
        budget=budget, telemetry=telemetry,
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
