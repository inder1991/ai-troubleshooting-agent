import asyncio
import json
import logging
import re
from src.utils.llm_client import AnthropicClient
from src.database.models import DBFindingV2
from .prompts import get_synthesizer_prompt

logger = logging.getLogger(__name__)

SYNTHESIZER_MODEL = "claude-sonnet-4-20250514"


async def root_cause_synthesizer(
    state: dict,
    all_findings: list[DBFindingV2],
    emitter=None,
    timeout: float = 60.0,
) -> dict:
    """Use Sonnet to perform root cause analysis across all agent findings.

    Returns dict with: summary, root_cause, dossier, fix_recommendations, needs_human_review
    Falls back to deterministic synthesis if LLM fails.
    """
    engine = state.get("engine", "postgresql")

    if not all_findings:
        return _empty_result()

    try:
        result = await asyncio.wait_for(
            _llm_synthesize(state, all_findings, engine, emitter),
            timeout=timeout,
        )
        return result
    except Exception as e:
        logger.error("LLM synthesis failed, using deterministic fallback: %s", e)
        if emitter:
            await emitter.emit("synthesizer", "warning",
                f"LLM synthesis failed ({e}), using deterministic analysis")
        return _deterministic_synthesize(state, all_findings, engine, emitter)


def _parse_llm_json(raw_text: str) -> dict:
    """Parse LLM output as JSON, handling markdown fences and size limits."""
    MAX_JSON_SIZE = 500_000
    if len(raw_text) > MAX_JSON_SIZE:
        raise ValueError(f"Synthesizer response too large: {len(raw_text)} bytes (max {MAX_JSON_SIZE})")

    # Handle markdown code blocks
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        json_match = re.search(r'\{[\s\S]*\}', raw_text)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("Could not parse synthesizer JSON output")


def _build_dossier(state: dict, analysis: dict, all_findings: list) -> dict:
    """Build the 7-section dossier from LLM analysis and findings."""
    engine = state.get("engine", "postgresql")
    root_cause = analysis.get("root_cause", {})
    summary = analysis.get("executive_summary", root_cause.get("title", "Analysis complete"))

    return {
        "executive_summary": {
            "profile": state.get("profile_name", "unknown"),
            "host": state.get("host", ""),
            "engine": engine,
            "total_findings": len(all_findings),
            "critical_count": sum(1 for f in all_findings if f.severity == "critical"),
            "high_count": sum(1 for f in all_findings if f.severity == "high"),
            "medium_count": sum(1 for f in all_findings if f.severity == "medium"),
            "low_count": sum(1 for f in all_findings if f.severity in ("low", "info")),
            "headline": summary,
            "health_status": root_cause.get("severity", "warning"),
            "needs_human_review": any(f.confidence_calibrated < 0.7 for f in all_findings),
        },
        "root_cause_analysis": {
            "primary_root_cause": root_cause.get("title", ""),
            "causal_chain": root_cause.get("causal_chain", []),
            "confidence": root_cause.get("confidence", 0.0),
            "severity": root_cause.get("severity", "medium"),
            "evidence": root_cause.get("evidence", []),
            "evidence_weight_map": analysis.get("evidence_weight_map",
                root_cause.get("evidence_weight_map", {})),
        },
        "evidence_chain": [
            {
                "step": i + 1,
                "finding_id": f.finding_id,
                "agent": f.agent,
                "title": f.title,
                "severity": f.severity,
                "confidence": f.confidence_calibrated,
                "detail": f.detail,
            }
            for i, f in enumerate(all_findings)
        ],
        "impact_assessment": analysis.get("impact_assessment", {}),
        "remediation_recommendations": analysis.get("remediation_plan", []),
        "prevention_measures": analysis.get("prevention_measures", []),
        "alternative_hypotheses": analysis.get("alternative_hypotheses", []),
        "appendix": {
            "raw_finding_ids": [f.finding_id for f in all_findings],
            "agent_summary": {
                "query_analyst": sum(1 for f in all_findings if f.agent == "query_analyst"),
                "health_analyst": sum(1 for f in all_findings if f.agent == "health_analyst"),
                "schema_analyst": sum(1 for f in all_findings if f.agent == "schema_analyst"),
            },
            "investigation_mode": state.get("investigation_mode", "standalone"),
            "session_id": state.get("session_id", ""),
        },
    }


def _build_fix_recommendations(analysis: dict, all_findings: list) -> list[dict]:
    """Extract fix recommendations from LLM analysis, with finding fallback."""
    fix_recommendations = []
    for i, rem in enumerate(analysis.get("remediation_plan", [])):
        fix_recommendations.append({
            "priority": rem.get("priority", i + 1),
            "finding_id": rem.get("finding_id", ""),
            "title": rem.get("action", rem.get("title", "")),
            "severity": rem.get("severity", "medium"),
            "category": rem.get("category", ""),
            "recommendation": rem.get("action", ""),
            "sql": rem.get("sql", ""),
            "warning": rem.get("warning", "Review carefully before executing."),
            "agent": rem.get("agent", "synthesizer"),
        })

    # If LLM didn't generate fix recs, build from findings
    if not fix_recommendations:
        for i, f in enumerate(all_findings):
            if f.remediation_sql:
                fix_recommendations.append({
                    "priority": i + 1,
                    "finding_id": f.finding_id,
                    "title": f.title,
                    "severity": f.severity,
                    "category": f.category,
                    "recommendation": f.recommendation,
                    "sql": f.remediation_sql,
                    "warning": f.remediation_warning or "Review carefully before executing.",
                    "agent": f.agent,
                })

    return fix_recommendations


async def _llm_synthesize(state, all_findings, engine, emitter):
    """Call Sonnet for root cause analysis."""
    if emitter:
        await emitter.emit("synthesizer", "started", "Synthesizing root cause analysis with AI")

    llm = AnthropicClient(agent_name="synthesizer", model=SYNTHESIZER_MODEL)
    system_prompt = get_synthesizer_prompt(engine)

    # Build context for the LLM
    findings_json = json.dumps(
        [f.model_dump(exclude={"meta", "evidence_sources"}) for f in all_findings],
        indent=2, default=str,
    )

    db_context = {
        "profile_name": state.get("profile_name", "unknown"),
        "host": state.get("host", ""),
        "engine": engine,
        "database": state.get("database", ""),
        "investigation_mode": state.get("investigation_mode", "standalone"),
        "sampling_mode": state.get("sampling_mode", "standard"),
        "focus_areas": state.get("focus", []),
    }

    user_message = f"""Here are the diagnostic findings from 3 specialist agents:

{findings_json}

Database context:
{json.dumps(db_context, indent=2)}

Total findings: {len(all_findings)}
Critical: {sum(1 for f in all_findings if f.severity == 'critical')}
High: {sum(1 for f in all_findings if f.severity == 'high')}

Perform root cause analysis. Identify causal chains. Generate your response as JSON."""

    response = await llm.chat(
        prompt=user_message,
        system=system_prompt,
        max_tokens=4096,
        temperature=0.0,
    )

    # Parse the LLM response as JSON
    raw_text = response.text.strip()
    analysis = _parse_llm_json(raw_text)

    # Extract structured data from LLM response
    root_cause = analysis.get("root_cause", {})
    summary = analysis.get("executive_summary", root_cause.get("title", "Analysis complete"))

    if emitter:
        await emitter.emit("synthesizer", "reasoning", summary)
        causal_chain = root_cause.get("causal_chain", [])
        if causal_chain:
            await emitter.emit("synthesizer", "reasoning",
                f"Causal chain: {' → '.join(causal_chain)}")

    # Build dossier and fix recommendations via helpers
    dossier = _build_dossier(state, analysis, all_findings)
    fix_recommendations = _build_fix_recommendations(analysis, all_findings)

    if emitter:
        top_severity = root_cause.get("severity", "medium")
        await emitter.emit("synthesizer", "success", summary, details={
            "severity": top_severity,
            "recommendation": fix_recommendations[0]["recommendation"] if fix_recommendations else "",
            "root_cause": root_cause.get("title", ""),
            "finding_count": len(all_findings),
            "critical_count": sum(1 for f in all_findings if f.severity == "critical"),
        })

    return {
        "findings": [f.model_dump() for f in all_findings],
        "summary": summary,
        "root_cause": root_cause.get("title", ""),
        "needs_human_review": any(f.confidence_calibrated < 0.7 for f in all_findings),
        "status": "completed",
        "dossier": dossier,
        "fix_recommendations": fix_recommendations,
    }


def _deterministic_synthesize(state, all_findings, engine, emitter):
    """Fallback: deterministic synthesis (current logic from graph_v2.py synthesizer)."""
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    sorted_findings = sorted(
        all_findings,
        key=lambda f: severity_order.get(f.severity, 0) * f.confidence_raw,
        reverse=True,
    )

    top = sorted_findings[0] if sorted_findings else None
    root_cause = top.title if top else "No issues detected"
    finding_count = len(sorted_findings)
    critical_count = sum(1 for f in sorted_findings if f.severity == "critical")

    summary = (
        f"Investigated {state.get('profile_name', 'unknown')} database. "
        f"Found {finding_count} issue(s), {critical_count} critical. "
        f"Primary concern: {root_cause}."
    )

    # Build minimal dossier
    dossier = {
        "executive_summary": {
            "profile": state.get("profile_name", "unknown"),
            "host": state.get("host", ""),
            "engine": engine,
            "total_findings": finding_count,
            "critical_count": critical_count,
            "headline": summary,
            "health_status": "critical" if critical_count > 0 else "degraded",
        },
        "root_cause_analysis": {
            "primary_root_cause": root_cause,
            "confidence": top.confidence_calibrated if top else 0,
            "severity": top.severity if top else "info",
        },
        "evidence_chain": [
            {"step": i+1, "title": f.title, "severity": f.severity, "detail": f.detail}
            for i, f in enumerate(sorted_findings)
        ],
        "impact_assessment": {},
        "remediation_recommendations": [],
        "prevention_measures": [],
        "appendix": {},
    }

    # Build fix recs from findings
    fix_recommendations = []
    for i, f in enumerate(sorted_findings):
        if f.remediation_sql or f.recommendation:
            fix_recommendations.append({
                "priority": i + 1,
                "finding_id": f.finding_id,
                "title": f.title,
                "severity": f.severity,
                "category": f.category,
                "recommendation": f.recommendation,
                "sql": f.remediation_sql,
                "warning": f.remediation_warning or "Review carefully before executing.",
                "agent": f.agent,
            })

    return {
        "findings": [f.model_dump() for f in sorted_findings],
        "summary": summary,
        "root_cause": root_cause,
        "needs_human_review": any(f.confidence_calibrated < 0.7 for f in sorted_findings),
        "status": "completed",
        "dossier": dossier,
        "fix_recommendations": fix_recommendations,
    }


def _empty_result():
    return {
        "findings": [],
        "summary": "No issues detected.",
        "root_cause": "No issues detected",
        "needs_human_review": False,
        "status": "completed",
        "dossier": {"executive_summary": {"total_findings": 0, "headline": "No issues detected"}},
        "fix_recommendations": [],
    }
