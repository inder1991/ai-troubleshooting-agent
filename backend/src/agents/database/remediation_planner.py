"""AI Remediation Planner — maps diagnostic findings to actionable remediation plans.

Graph: analyze_findings → generate_plans → END (plans returned for human approval).
"""
from __future__ import annotations

import logging
import re
from typing import TypedDict

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class RemediationPlannerState(TypedDict, total=False):
    profile_id: str
    findings: list[dict]
    plans: list[dict]
    _engine: object  # RemediationEngine instance


# ── Finding-to-action mapping logic ──

def _extract_table_from_evidence(evidence: list[str], detail: str) -> str | None:
    """Try to extract a table name from evidence or detail text."""
    for e in (evidence or []):
        # Pattern: "tablename: NN% bloat" or "tablename has bloat"
        match = re.match(r"(\w+)[:,\s]", e)
        if match:
            return match.group(1)
    # Try detail
    words = detail.split()
    for i, w in enumerate(words):
        if w.lower() in ("table", "on") and i + 1 < len(words):
            return words[i + 1].strip(".,;:'\"")
    return None


def _extract_column_from_evidence(evidence: list[str], detail: str) -> str | None:
    """Try to extract a column name from evidence about slow queries."""
    for e in (evidence or []):
        match = re.search(r"filtering\s+(\w+)", e, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"\.(\w+)", e)
        if match:
            return match.group(1)
    match = re.search(r"\.(\w+)", detail)
    if match:
        return match.group(1)
    return None


def _extract_pid(evidence: list[str], detail: str) -> int | None:
    """Extract a PID from evidence about deadlocks/blocking."""
    for e in (evidence or []):
        match = re.search(r"(?:pid|PID)[:\s]+(\d+)", e)
        if match:
            return int(match.group(1))
        match = re.search(r"blocking_pid[:\s]+(\d+)", e)
        if match:
            return int(match.group(1))
    match = re.search(r"PID\s+(\d+)", detail)
    if match:
        return int(match.group(1))
    return None


def generate_plans_from_findings(engine, profile_id: str,
                                  findings: list[dict]) -> list[dict]:
    """Map findings to remediation plans. Returns list of created plans."""
    plans = []
    for f in findings:
        if not f.get("remediation_available", False):
            continue

        category = f.get("category", "")
        evidence = f.get("evidence", [])
        detail = f.get("detail", "")
        finding_id = f.get("finding_id")

        try:
            if category in ("table_bloat",):
                table = _extract_table_from_evidence(evidence, detail)
                if table:
                    # Check if bloat > 30% for FULL vacuum
                    bloat_match = re.search(r"(\d+)%", detail)
                    full = bloat_match and int(bloat_match.group(1)) > 30
                    plan = engine.plan(
                        profile_id=profile_id, action="vacuum",
                        params={"table": table, "full": bool(full), "analyze": True},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("index_bloat",):
                table = _extract_table_from_evidence(evidence, detail)
                if table:
                    plan = engine.plan(
                        profile_id=profile_id, action="reindex",
                        params={"table": table},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("slow_queries", "missing_index"):
                table = _extract_table_from_evidence(evidence, detail)
                col = _extract_column_from_evidence(evidence, detail)
                if table and col:
                    plan = engine.plan(
                        profile_id=profile_id, action="create_index",
                        params={"table": table, "columns": [col], "unique": False},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("unused_index",):
                # Extract index name from evidence
                for e in evidence:
                    match = re.search(r"(idx_\w+)", e)
                    if match:
                        plan = engine.plan(
                            profile_id=profile_id, action="drop_index",
                            params={"index_name": match.group(1)},
                            finding_id=finding_id,
                        )
                        plans.append(plan)
                        break

            elif category in ("deadlocks",):
                pid = _extract_pid(evidence, detail)
                if pid:
                    plan = engine.plan(
                        profile_id=profile_id, action="kill_query",
                        params={"pid": pid},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("connection_saturation",):
                plan = engine.plan(
                    profile_id=profile_id, action="alter_config",
                    params={"param": "max_connections", "value": "200"},
                    finding_id=finding_id,
                )
                plans.append(plan)

            elif category in ("replication_lag",):
                plan = engine.plan(
                    profile_id=profile_id, action="failover_runbook",
                    params={},
                    finding_id=finding_id,
                )
                plans.append(plan)

        except Exception as e:
            logger.warning("Failed to generate plan for finding %s: %s",
                           finding_id, e)

    return plans


# ── LangGraph nodes ──

def analyze_findings(state: RemediationPlannerState) -> dict:
    """Filter findings that have remediation available."""
    findings = state.get("findings", [])
    remediable = [f for f in findings if f.get("remediation_available", False)]
    return {"findings": remediable}


def generate_plans(state: RemediationPlannerState) -> dict:
    """Generate remediation plans from findings."""
    engine = state.get("_engine")
    profile_id = state.get("profile_id", "")
    findings = state.get("findings", [])

    if not engine or not findings:
        return {"plans": []}

    plans = generate_plans_from_findings(engine, profile_id, findings)
    return {"plans": plans}


def build_remediation_planner_graph():
    """Build the LangGraph for remediation planning."""
    graph = StateGraph(RemediationPlannerState)
    graph.add_node("analyze_findings", analyze_findings)
    graph.add_node("generate_plans", generate_plans)
    graph.set_entry_point("analyze_findings")
    graph.add_edge("analyze_findings", "generate_plans")
    graph.add_edge("generate_plans", END)
    return graph.compile()
